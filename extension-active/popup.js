const el=id=>document.getElementById(id);
let tabs=new Map(), workerOnline=false;
async function send(msg) {
  const result=await chrome.runtime.sendMessage(msg);
  if (!result?.ok) throw Error(result?.error||"Fehler");
  return result;
}
function selected() {
  return tabs.get(el("chat-tabs").value) || null;
}
function updateSelection() {
  const tab=selected();
  el("toggle").disabled=!tab || (!workerOnline && !tab.enabled);
  el("toggle").textContent=tab?.enabled?"Deaktivieren":"Aktivieren";
  el("detail").textContent=tab
    ? "Chat "+tab.conversation_id.slice(0,12)+"… | Tab "+tab.tab_id
    : "Bitte einen offenen ChatGPT-Tab auswählen";
}
async function refresh() {
  try {
    const response=await send({type:"ACTIVE_GET"});
    workerOnline=response.connected===true;
    const problem=response.connectionError;
    el("connection").textContent=workerOnline?"Worker verbunden":
      !response.tokenSaved?"Token fehlt. Bitte aus PySide6 kopieren.":
      problem==="worker_http_401"?"Token ungültig oder GUI neu gestartet.":
      problem==="worker_extension_id_mismatch"?"Erweiterungs-ID stimmt nicht mit GUI überein.":
      problem==="worker_http_403"?"HTTP 403: Anfrage durch Origin-Prüfung abgelehnt. GUI-ID und laufenden Prozess auf Port 8766 prüfen.":
      "Worker nicht erreichbar: "+(problem||"Unbekannter Fehler");
    el("extension-id").textContent="Erweiterungs-ID: "+String(response.extensionId||chrome.runtime.id);
    const previous=el("chat-tabs").value;
    tabs=new Map();
    const select=el("chat-tabs");
    select.replaceChildren();
    const placeholder=document.createElement("option");
    placeholder.value="";
    placeholder.textContent="ChatGPT-Chat auswählen";
    select.append(placeholder);
    for(const tab of response.tabs||[]) {
      const key=String(tab.tab_id);
      tabs.set(key,tab);
      const item=document.createElement("option");
      item.value=key;
      item.textContent=(tab.enabled?"[Überwacht] ":"")+
        tab.title+" (Tab "+key+")";
      select.append(item);
    }
    if(tabs.has(previous)) select.value=previous;
    else if(tabs.size===1) select.value=[...tabs.keys()][0];
    else select.value="";
    if(!tabs.size) {
      el("detail").textContent="Keine offenen ChatGPT-Konversationen gefunden. "+
        "Ein Chat muss eine /c/...-Adresse haben.";
    } else updateSelection();
    el("toggle").disabled=!selected() || (!workerOnline && !selected().enabled);
    if(!tabs.size) el("toggle").disabled=true;
    el("status").textContent=(response.tabs||[]).length+" geöffnete ChatGPT-Chats";
  } catch(e) {
    workerOnline=false;
    el("toggle").disabled=true;
    el("status").textContent="Fehler bei der Tab-Abfrage: "+String(e.message||e);
  }
}
el("chat-tabs").addEventListener("change",updateSelection);
el("reload-tabs").addEventListener("click",refresh);
el("save").addEventListener("click",async()=>{
  try {
    await send({type:"ACTIVE_SET_TOKEN",token:el("token").value.trim()});
    el("token").value="";
    await refresh();
  } catch(e) {el("status").textContent=String(e.message||e);}
});
el("toggle").addEventListener("click",async()=>{
  try {
    const tab=selected();
    if(!tab) throw Error("Bitte Chat auswählen");
    const result=await send({type:"ACTIVE_TOGGLE",
      tab_id:tab.tab_id,conversation_id:tab.conversation_id});
    await refresh();
    el("status").textContent=result.active?"Chatüberwachung aktiviert":"Chatüberwachung beendet";
  } catch(e) {el("status").textContent=String(e.message||e);}
});
void refresh();
