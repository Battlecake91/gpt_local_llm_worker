/* Opt-in transport only. No LLM or SSH logic in browser. */
const BASE = "http://127.0.0.1:8766";
const ACTIVE = "activeTabs";
const TOKEN = "bridgeToken";
let inFlight = new Set();

const ready = Promise.all([
  chrome.storage.local.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"}),
  chrome.storage.session.setAccessLevel({accessLevel:"TRUSTED_CONTEXTS"})
]);

async function enabled() {
  await ready;
  const value = await chrome.storage.session.get(ACTIVE);
  return value[ACTIVE] || {};
}
async function getToken() {
  await ready;
  return (await chrome.storage.local.get(TOKEN))[TOKEN] || "";
}
async function api(path, method="GET", body=null) {
  const token = await getToken();
  if (!token) throw Error("token_missing");
  const response = await fetch(BASE+path,{
    method,
    headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},
    ...(body ? {body:JSON.stringify(body)} : {}),
    signal:AbortSignal.timeout(4500)
  });
  if (!response.ok) throw Error("worker_http_"+response.status);
  return response.json();
}
function parseChat(url) {
  try {
    const u = new URL(url);
    const match = u.hostname==="chatgpt.com" &&
      u.pathname.match(/^(?:\/c|\/g\/g-p-[a-zA-Z0-9-]+\/c)\/([a-zA-Z0-9-]+)\/?$/);
    return match ? match[1] : null;
  } catch { return null; }
}
async function listChatTabs() {
  // Query all normal browser windows. Popup and service worker contexts must
  // never assume that "currentWindow" is the ChatGPT window.
  const tabs = await chrome.tabs.query({});
  return tabs.filter(t => t.id > 0 && parseChat(t.url || "") &&
    (!t.incognito) && (t.windowId >= 0)).map(t => ({
      tab_id: t.id, conversation_id: parseChat(t.url),
      title: (t.title || "ChatGPT").slice(0, 120),
      active: !!t.active, window_id: t.windowId
    }));
}
async function selectedChatTab(tabId, conversationId) {
  if (!Number.isSafeInteger(tabId) || tabId <= 0 ||
      typeof conversationId !== "string" || !conversationId)
    throw Error("invalid_tab_selection");
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || tab.incognito || parseChat(tab.url || "") !== conversationId)
    throw Error("tab_closed_or_changed");
  return tab;
}
async function deactivate(tabId) {
  const active=await enabled();
  if (!active[tabId]) return;
  delete active[tabId];
  await chrome.storage.session.set({[ACTIVE]:active});
  await api("/v2/tabs/"+tabId,"DELETE").catch(()=>{});
}
async function reconcileTab(tabId, conversationId) {
  if (inFlight.has(Number(tabId))) return;
  const tab=await chrome.tabs.get(Number(tabId)).catch(()=>null);
  if (!tab || parseChat(tab.url||"")!==conversationId) {
    await deactivate(Number(tabId));
    return;
  }
  const result=await chrome.tabs.sendMessage(Number(tabId),
    {type:"ACTIVE_REQUEST_SNAPSHOT"}).catch(()=>null);
  if (!result?.snapshot || result.snapshot.conversation_id!==conversationId) return;
  inFlight.add(Number(tabId));
  try {
    await api("/v2/snapshot","POST",{...result.snapshot,tab_id:Number(tabId)});
  } catch {
    // Keep activation and retry on the next alarm. Never silently switch chat.
  } finally { inFlight.delete(Number(tabId)); }
}
async function reconcileAll() {
  const active=await enabled();
  await Promise.all(Object.entries(active).map(
    ([tab,conv])=>reconcileTab(tab,conv)));
}
chrome.alarms.create("active-chat-sync",{periodInMinutes:0.5});
chrome.alarms.onAlarm.addListener(a=>{
  if(a.name==="active-chat-sync")void reconcileAll();
});
chrome.runtime.onStartup.addListener(()=>chrome.alarms.create(
  "active-chat-sync",{periodInMinutes:0.5}));
chrome.tabs.onRemoved.addListener(tabId => { void deactivate(tabId); });
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.url && !parseChat(change.url)) void deactivate(tabId);
  else if (change.url) {
    void enabled().then(a=>{if(a[tabId] && a[tabId]!==parseChat(change.url))return deactivate(tabId);});
  }
});
chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
  (async()=>{
    if (msg.type === "ACTIVE_CHAT_SNAPSHOT") {
      if (!sender.tab?.id || !sender.tab.url ||
          !parseChat(sender.tab.url)) return {ok:false,error:"unauthorized_tab"};
      const tabId=sender.tab.id, active=await enabled();
      if (active[tabId]!==msg.snapshot?.conversation_id ||
          active[tabId]!==parseChat(sender.tab.url)) return {ok:false,error:"disabled"};
      if (inFlight.has(tabId)) return {ok:true,status:"busy"};
      inFlight.add(tabId);
      try {
        const data=msg.snapshot;
        if (!Array.isArray(data.messages)) return {ok:false,error:"invalid_snapshot"};
        await api("/v2/snapshot","POST",{...data,tab_id:tabId});
        return {ok:true};
      } finally {inFlight.delete(tabId);}
    }
    if (!sender.url?.startsWith(chrome.runtime.getURL("popup.html")))
      return {ok:false,error:"popup_only"};
    if (msg.type==="ACTIVE_GET") {
      const active=await enabled();
      const tabs=await listChatTabs();
      let connected=false, connectionError=null;
      try { await api("/v2/health"); connected=true; }
      catch(e) { connectionError=String(e.message||e); }
      return {ok:true, connected, connectionError, tokenSaved:!!(await getToken()),
        tabs:tabs.map(t=>({...t,enabled:active[t.tab_id]===t.conversation_id})),
        count:Object.keys(active).length};
    }
    if (msg.type==="ACTIVE_SET_TOKEN") {
      if (typeof msg.token!=="string" || msg.token.length<32 || msg.token.length>256)
        return {ok:false,error:"invalid_token"};
      await chrome.storage.local.set({[TOKEN]:msg.token});
      return {ok:true};
    }
    if (msg.type==="ACTIVE_TOGGLE") {
      const tab=await selectedChatTab(msg.tab_id,msg.conversation_id);
      const active=await enabled();
      if (active[tab.id]===msg.conversation_id) {
        await deactivate(tab.id);
        return {ok:true,active:false};
      }
      // Activation is always explicit, scoped to the selected tab + chat ID.
      await api("/v2/health");
      active[tab.id]=msg.conversation_id;
      await chrome.storage.session.set({[ACTIVE]:active});
      void reconcileTab(tab.id,msg.conversation_id);
      return {ok:true,active:true};
    }
    return {ok:false,error:"unknown_message"};
  })().then(reply,e=>reply({ok:false,error:String(e.message||e)}));
  return true;
});
