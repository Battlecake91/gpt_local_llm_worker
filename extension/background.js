/* The extension transports data. The authenticated worker alone authorizes auto-send. */
const BASE='http://127.0.0.1:8765/api/bridge/v1';
const pending=new Map(), busy=new Set();
let sessionToken=''; // Process memory only: never persist service credentials in extension storage.
let state={connected:false,captureEnabled:true,tabs:{},lastCapture:null,lastTransfer:null,lastOutbound:null,error:null,pending:0};
const broadcast=()=>chrome.runtime.sendMessage({type:'STATUS',state}).catch(()=>{});
async function config(){const {captureEnabled=true}=await chrome.storage.local.get(['captureEnabled']);state.captureEnabled=captureEnabled;return sessionToken;}
async function api(path,options={}){
  const token=await config();if(!token)throw Error('worker_token_not_configured');
  const response=await fetch(BASE+path,{...options,headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json',...(options.headers||{})},signal:AbortSignal.timeout(7500)});
  if(!response.ok)throw Error(`worker_http_${response.status}`);
  state.connected=true;
  return response.json();
}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function submitCapture(payload,tabId){
  if(pending.has(payload.message_id))return;
  pending.set(payload.message_id,{payload:{...payload,tab_id:tabId},attempt:0});state.pending=pending.size;broadcast();
  await flushCaptures();
}
async function flushCaptures(){
  for(const [id,item] of pending){
    if(busy.has(id))continue;busy.add(id);
    try{const ack=await api('/captures',{method:'POST',body:JSON.stringify(item.payload)});
      if(ack.message_id!==id || !['accepted','duplicate'].includes(ack.status))throw Error('capture_ack_invalid');
      pending.delete(id);state.lastTransfer={id,status:ack.status,at:new Date().toISOString()};state.error=null;
    }catch(e){item.attempt++;state.connected=false;state.error=String(e);}
    finally{busy.delete(id);state.pending=pending.size;broadcast();}
  }
  await chrome.storage.local.set({pendingCaptures:[...pending.values()]});
}
async function outbound(){
  const jobs=(await api('/outbound')).items||[];
  for(const item of jobs){
    if(!item.id||!item.conversation_id||!Number.isInteger(item.tab_id))continue;
    const key=`receipt_${item.id}`;
    const stored=await chrome.storage.local.get(key);
    if(stored[key])continue; // Do not risk a second send when ack was lost.
    const tab=await chrome.tabs.get(item.tab_id).catch(()=>null);
    if(!tab?.url || new URL(tab.url).hostname!=='chatgpt.com')continue;
    const result=await chrome.tabs.sendMessage(item.tab_id,{type:'GET_TAB_STATE'}).catch(()=>null);
    if(result?.conversation_id!==item.conversation_id)continue;
    let automatic=false,claimId=null;
    if(item.mode==='AUTO_SEND_APPROVED_RESULT'){
      const grant=await api(`/outbound/${encodeURIComponent(item.id)}/claim`,{method:'POST',body:JSON.stringify({conversation_id:item.conversation_id,tab_id:item.tab_id})});
      if(grant.allowed!==true || !grant.claim_id || grant.kind!=='approved_ssh_result')throw Error('invalid_backend_grant');
      automatic=true;claimId=grant.claim_id;
    }else if(item.mode!=='STAGE_ONLY'){throw Error('unknown_outbound_mode');}
    // Persist before click: fail closed on crash. Manual reconcile needed on ambiguous outcome.
    if(automatic)await chrome.storage.local.set({[key]:{status:'ATTEMPTING',at:new Date().toISOString()}});
    const r=await chrome.tabs.sendMessage(item.tab_id,{type:'STAGE_MESSAGE',conversation_id:item.conversation_id,text:item.text,auto_send:automatic,claim_id:claimId}).catch(e=>({ok:false,error:String(e)}));
    if(automatic || r?.ok)await chrome.storage.local.set({[key]:{status:r?.status||'UNKNOWN',at:new Date().toISOString()}});
    state.lastOutbound={id:item.id,status:r?.status||'ERROR',error:r?.error||null};broadcast();
    await api(`/outbound/${encodeURIComponent(item.id)}/ack`,{method:'POST',body:JSON.stringify({status:r?.status||'ERROR',error:r?.error||null,claim_id:claimId})});
  }
}
let cycleRunning=false;
async function cycle(){
  if(cycleRunning)return;
  cycleRunning=true;
  try{await flushCaptures();await outbound();state.connected=true;state.error=null;}
  catch(e){state.connected=false;state.error=String(e);}
  finally{cycleRunning=false;broadcast();}
}
chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
  if(msg.type==='CAPTURE'){
    if(!state.captureEnabled || sender.tab?.id==null)return;
    state.lastCapture={id:msg.payload.message_id,preview:msg.payload.text.slice(0,300),at:new Date().toISOString()};broadcast();
    submitCapture(msg.payload,sender.tab.id).catch(e=>{state.error=String(e);broadcast();});return;
  }
  if(msg.type==='OBSERVED_STATE'){
    if(sender.tab?.id!=null)state.tabs[sender.tab.id]={
      ...state.tabs[sender.tab.id],
      state:msg.state,conversation_id:msg.conversation_id,
      ...(msg.diagnostics?{diagnostics:msg.diagnostics}:{})
    };
    if(msg.error)state.error=msg.error;broadcast();return;
  }
  if(msg.type==='GET_STATUS'){reply(state);return;}
  if(msg.type==='SET_ENABLED'){
    state.captureEnabled=!!msg.enabled;
    chrome.storage.local.set({captureEnabled:state.captureEnabled});
    chrome.tabs.query({url:'https://chatgpt.com/*'}).then(tabs=>Promise.all(tabs.map(t=>chrome.tabs.sendMessage(t.id,{type:'SET_CAPTURE',enabled:state.captureEnabled}).catch(()=>{}))));
    broadcast();reply({ok:true});return;
  }
  if(msg.type==='REFRESH_DIAGNOSTICS'){
    chrome.tabs.query({url:'https://chatgpt.com/*'}).then(tabs=>
      Promise.all(tabs.map(t=>chrome.tabs.sendMessage(t.id,{type:'REQUEST_DIAGNOSTICS'}).catch(()=>{})))
    ).then(()=>reply({ok:true})).catch(e=>reply({ok:false,error:String(e)}));
    return true;
  }
  if(msg.type==='SET_TOKEN'){
    sessionToken=String(msg.token||'');cycle().then(()=>reply({ok:true}));return true;
  }
  if(msg.type==='SYNC_NOW'){cycle().then(()=>reply({ok:true}));return true;}
});
chrome.tabs.onRemoved.addListener(id=>{delete state.tabs[id];broadcast();});
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true}).catch(()=>{});
chrome.storage.local.get(['pendingCaptures','captureEnabled']).then(data=>{
  state.captureEnabled=data.captureEnabled!==false;
  for(const item of data.pendingCaptures||[])pending.set(item.payload.message_id,item);
  state.pending=pending.size;broadcast();cycle();
});
// MV3 worker can be suspended. Alarm wakes it and drives bounded reconciliation.
chrome.alarms?.create('bridge-sync',{periodInMinutes:0.5});
chrome.alarms?.onAlarm.addListener(alarm=>{if(alarm.name==='bridge-sync')cycle();});
