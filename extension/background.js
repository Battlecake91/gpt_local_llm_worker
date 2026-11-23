/* The extension transports data. The authenticated worker alone authorizes auto-send. */
const BASE='http://127.0.0.1:8765/api/bridge/v1';
const pending=new Map(), busy=new Set();
let sessionToken=''; // Cached after protected extension-local storage has been loaded.
let authRejected=false; // Stop replay storms until the operator replaces the token.
let credentialsReady=null;
let startupReady; // Capture queue restoration must finish before any network cycle.
const TOKEN_KEY='workerBearerToken';
// Do not expose persisted tokens to content scripts. Fail closed if Chromium
// cannot restrict storage to trusted extension contexts.
const storageProtected=chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
async function credentials(){
  await storageProtected;
  if(!credentialsReady)credentialsReady=chrome.storage.local.get([TOKEN_KEY]).then(data=>{
    sessionToken=typeof data[TOKEN_KEY]==='string'?data[TOKEN_KEY]:'';
  });
  await credentialsReady;
  return sessionToken;
}
let state={connected:false,captureEnabled:true,tabs:{},lastCapture:null,lastTransfer:null,lastOutbound:null,error:null,pending:0,tokenSaved:false};
const broadcast=()=>chrome.runtime.sendMessage({type:'STATUS',state}).catch(()=>{});
async function config(){
  const token=await credentials();
  const {captureEnabled=true}=await chrome.storage.local.get(['captureEnabled']);
  state.captureEnabled=captureEnabled;
  state.tokenSaved=!!token;
  return token;
}
async function api(path,options={}){
  const token=await config();if(!token)throw Error('worker_token_not_configured');
  if(authRejected)throw Error('worker_http_401_token_rejected');
  const response=await fetch(BASE+path,{...options,headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json',...(options.headers||{})},signal:AbortSignal.timeout(7500)});
  if(response.status===401){authRejected=true;throw Error('worker_http_401_token_rejected');}
  if(!response.ok)throw Error(`worker_http_${response.status}`);
  state.connected=true;
  return response.json();
}
// A claim is usable only when it attests to this exact, immutable SSH result.
// The server must additionally verify the user-approved command batch and job.
const HEX_SHA=/^[a-f0-9]{64}$/;
const SAFE_ID=/^[A-Za-z0-9._:-]{1,160}$/;
async function sha256(text){
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
async function validateGrant(item,grant){
  const approval=item.approval;
  if(!approval || !grant || grant.allowed!==true ||
     grant.kind!=='approved_ssh_result' ||
     typeof grant.claim_id!=='string' || !SAFE_ID.test(grant.claim_id) ||
     typeof item.text!=='string' || !item.text.length)throw Error('invalid_backend_grant');
  for(const key of ['job_id','approval_id','host_id']){
    if(typeof approval[key]!=='string' || !SAFE_ID.test(approval[key]) ||
       approval[key]!==grant[key])throw Error('approval_binding_mismatch');
  }
  for(const key of ['command_sha256','result_sha256']){
    if(typeof approval[key]!=='string' || !HEX_SHA.test(approval[key]) ||
       approval[key]!==grant[key])throw Error('approval_binding_mismatch');
  }
  if((await sha256(item.text))!==approval.result_sha256)throw Error('result_digest_mismatch');
  if(item.conversation_id!==grant.conversation_id ||
     item.tab_id!==grant.tab_id ||
     item.id!==grant.outbound_id)throw Error('origin_binding_mismatch');
  return grant.claim_id;
}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function submitCapture(payload,tabId){
  await startupReady;
  if(pending.has(payload.message_id))return;
  pending.set(payload.message_id,{payload:{...payload,tab_id:tabId},attempt:0});state.pending=pending.size;broadcast();
  await flushCaptures();
}
async function flushCaptures(){
  if(authRejected){
    await chrome.storage.local.set({pendingCaptures:[...pending.values()]});
    return;
  }
  for(const [id,item] of pending){
    if(busy.has(id))continue;busy.add(id);
    try{const ack=await api('/captures',{method:'POST',body:JSON.stringify(item.payload)});
      if(ack.message_id!==id || !['accepted','duplicate'].includes(ack.status))throw Error('capture_ack_invalid');
      pending.delete(id);state.lastTransfer={id,status:ack.status,at:new Date().toISOString()};state.error=null;
    }catch(e){item.attempt++;state.connected=false;state.error=String(e);}
    finally{busy.delete(id);state.pending=pending.size;broadcast();}
    if(authRejected)break;
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
      // Reject malformed or unbound messages BEFORE attempting a one-time claim.
      if(!item.approval || typeof item.text!=='string' || !item.text ||
         !['job_id','approval_id','host_id'].every(k=>typeof item.approval[k]==='string' && SAFE_ID.test(item.approval[k])) ||
         !['command_sha256','result_sha256'].every(k=>typeof item.approval[k]==='string' && HEX_SHA.test(item.approval[k])) ||
         await sha256(item.text)!==item.approval.result_sha256){
        await chrome.storage.local.set({[key]:{status:'BLOCKED_INVALID_PAYLOAD',at:new Date().toISOString()}});
        throw Error('unbound_auto_send_result');
      }
      const grant=await api(`/outbound/${encodeURIComponent(item.id)}/claim`,{method:'POST',body:JSON.stringify({
        conversation_id:item.conversation_id,tab_id:item.tab_id,
        job_id:item.approval.job_id,approval_id:item.approval.approval_id,
        result_sha256:item.approval.result_sha256
      })});
      try{claimId=await validateGrant(item,grant);}
      catch(e){
        // Invalid/replayed claims are terminal until explicit operator reconciliation.
        await chrome.storage.local.set({[key]:{status:'BLOCKED_INVALID_CLAIM',at:new Date().toISOString()}});
        throw e;
      }
      automatic=true;
    }else if(item.mode!=='STAGE_ONLY'){throw Error('unknown_outbound_mode');}
    // Persist before click: fail closed on crash. Manual reconcile needed on ambiguous outcome.
    if(automatic)await chrome.storage.local.set({[key]:{status:'ATTEMPTING',at:new Date().toISOString()}});
    const r=await chrome.tabs.sendMessage(item.tab_id,{type:'STAGE_MESSAGE',conversation_id:item.conversation_id,text:item.text,auto_send:automatic,claim_id:claimId}).catch(e=>({ok:false,error:String(e)}));
    if(automatic || r?.ok)await chrome.storage.local.set({[key]:{status:r?.status||'UNKNOWN',at:new Date().toISOString()}});
    state.lastOutbound={id:item.id,status:r?.status||'ERROR',error:r?.error||null,verification:r?.verification||null};broadcast();
    await api(`/outbound/${encodeURIComponent(item.id)}/ack`,{method:'POST',body:JSON.stringify({status:r?.status||'ERROR',error:r?.error||null,claim_id:claimId})});
  }
}
let cycleRunning=false;
async function cycle(){
  if(cycleRunning)return;
  cycleRunning=true;
  try{await startupReady;await flushCaptures();await outbound();state.connected=true;state.error=null;}
  catch(e){state.connected=false;state.error=String(e);}
  finally{cycleRunning=false;broadcast();}
}
// Only our own extension page may request user approval decisions.
// A ChatGPT content script never receives approval authority.
function trustedPanel(sender){
  return !sender.tab && sender.url===chrome.runtime.getURL('panel.html');
}
chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
  if(msg.type==='CAPTURE'){
    if(!state.captureEnabled || sender.tab?.id==null)return;
    state.lastCapture={
      id:msg.payload.message_id,
      preview:msg.payload.text.slice(0,8000),
      length:msg.payload.text.length,
      truncated:msg.payload.text.length>8000,
      at:new Date().toISOString()
    };broadcast();
    submitCapture(msg.payload,sender.tab.id).catch(e=>{state.error=String(e);broadcast();});
    reply({ok:true,status:'queued'});return;
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
  if(msg.type==='CAPTURE_CURRENT_FROM_PANEL'){
    if(!trustedPanel(sender)){reply({ok:false,error:'untrusted_capture_sender'});return;}
    (async()=>{
      if(!state.captureEnabled)throw Error('capture_disabled');
      const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
      if(!tab?.id || !tab.url?.startsWith('https://chatgpt.com/c/'))
        throw Error('active_chatgpt_conversation_required');
      const result=await chrome.tabs.sendMessage(tab.id,{type:'CAPTURE_CURRENT_REPLY'});
      reply(result?.ok?result:{ok:false,error:result?.error||'content_script_unavailable'});
    })().catch(e=>reply({ok:false,error:String(e.message||e)}));
    return true;
  }
  if(msg.type==='LIST_SSH_PROPOSALS' || msg.type==='LIST_MOCK_RESULTS' || msg.type==='DECIDE_SSH_PROPOSAL'){
    if(!trustedPanel(sender)){reply({ok:false,error:'untrusted_review_sender'});return;}
    (async()=>{
      if(msg.type==='LIST_SSH_PROPOSALS'){
        const result=await api('/ssh/proposals');
        reply({ok:true,items:Array.isArray(result.items)?result.items:[]});
        return;
      }
      if(msg.type==='LIST_MOCK_RESULTS'){
        const result=await api('/ssh/mock-results');
        reply({ok:true,items:Array.isArray(result.items)?result.items:[]});
        return;
      }
      const decision=msg.decision;
      if(!decision || !['approve','reject'].includes(decision.action) ||
         typeof decision.request_id!=='string' ||
         !SAFE_ID.test(decision.request_id) ||
         typeof decision.command_sha256!=='string' ||
         !HEX_SHA.test(decision.command_sha256) ||
         !Number.isInteger(decision.tab_id) ||
         typeof decision.conversation_id!=='string' ||
         decision.confirmed!==true)throw Error('invalid_review_decision');
      const currentTab=await chrome.tabs.get(decision.tab_id).catch(()=>null);
      if(!currentTab || new URL(currentTab.url).hostname!=='chatgpt.com')throw Error('review_tab_not_found');
      const current=await chrome.tabs.sendMessage(decision.tab_id,{type:'GET_TAB_STATE'});
      if(current?.conversation_id!==decision.conversation_id)throw Error('review_conversation_changed');
      const result=await api('/ssh/proposals/'+encodeURIComponent(decision.request_id)+'/'+decision.action,{
        method:'POST',body:JSON.stringify({
          command_sha256:decision.command_sha256,confirmed:true,
          conversation_id:decision.conversation_id,tab_id:decision.tab_id
        })
      });
      reply({ok:true,status:result.status});
    })().catch(e=>reply({ok:false,error:String(e.message||e)}));
    return true;
  }
  if(msg.type==='SET_TOKEN'){
    (async()=>{
      await credentials();
      const token=String(msg.token||'');
      if(!token || token.length>4096)throw Error('invalid_worker_token');
      await chrome.storage.local.set({[TOKEN_KEY]:token});
      sessionToken=token;authRejected=false;state.tokenSaved=true;broadcast();
      await cycle();
      reply({ok:true});
    })().catch(e=>reply({ok:false,error:String(e)}));
    return true;
  }
  if(msg.type==='CLEAR_TOKEN'){
    (async()=>{
      await credentials();
      await chrome.storage.local.remove(TOKEN_KEY);
      sessionToken='';authRejected=false;state.tokenSaved=false;state.connected=false;broadcast();
      reply({ok:true});
    })().catch(e=>reply({ok:false,error:String(e)}));
    return true;
  }
  if(msg.type==='SYNC_NOW'){cycle().then(()=>reply({ok:true}));return true;}
});
chrome.tabs.onRemoved.addListener(id=>{delete state.tabs[id];broadcast();});
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true}).catch(()=>{});
startupReady=Promise.all([credentials(),chrome.storage.local.get(['pendingCaptures','captureEnabled'])]).then(([,data])=>{
  state.captureEnabled=data.captureEnabled!==false;
  for(const item of data.pendingCaptures||[])pending.set(item.payload.message_id,item);
  state.pending=pending.size;state.tokenSaved=!!sessionToken;broadcast();
});
startupReady.then(()=>cycle()).catch(e=>{state.error='storage_security_failed: '+String(e);broadcast();});
// MV3 worker can be suspended. Alarm wakes it and drives bounded reconciliation.
chrome.alarms?.create('bridge-sync',{periodInMinutes:0.5});
chrome.alarms?.onAlarm.addListener(alarm=>{if(alarm.name==='bridge-sync')cycle();});
