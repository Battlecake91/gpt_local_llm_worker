(() => {
  'use strict';
  const core=globalThis.BridgeCore;
  let active=true, tabConversation=core.conversation(location.href), observer, route=location.href;
  let sawUserStop=false, baseline=new Set(), lastProcessed='';
  let diagnosticsSignature='', stopEverSeen=false, scanCount=0;
  const stopProbe=new globalThis.BridgeStopProbe.StopProbe();
  function reportDiagnostics(stop,node,role){
    // Only DOM metadata: never expose conversation or message text in diagnostics.
    const candidates=[...document.querySelectorAll('button')].filter(b=>
      /stop|abbrechen|anhalten|beenden/i.test(
        [b.getAttribute('aria-label'),b.getAttribute('data-testid'),b.getAttribute('title'),b.textContent?.trim().slice(0,35)].filter(Boolean).join(' ')
      )).slice(0,5).map(b=>({
        testid:b.getAttribute('data-testid')||'',
        aria:b.getAttribute('aria-label')||'',
        title:b.getAttribute('title')||''
      }));
    const selectors={
      legacyAssistant:'[data-message-author-role="assistant"]',
      legacyTurn:'[data-testid^="conversation-turn-"]',
      modernTurn:'[data-turn-key]',
      modernAssistant:'[data-content-search-unit-key$=":assistant"]',
      modernAssistantAlt:'[data-chatgpt-search-unit-key$=":assistant"]',
      modernUser:'[data-content-search-unit-key$=":user"]',
      appShell:'[data-app-shell-main-content-layout]',
      markdown:'.markdown',
      assistantMarkdown:'[data-markdown-text-style="assistant-message"]',
      userBubble:'[data-user-message-bubble="true"]',
      stopByTestId:'[data-testid="stop-button"]',
      stopByLabel:'button[aria-label*="Stop"],button[aria-label*="stop"],button[aria-label*="Abbrechen"]',
      composer:'form[data-chatgpt-composer] [contenteditable="true"][role="textbox"]'
    };
    const selectorCounts=Object.fromEntries(Object.entries(selectors).map(([key,selector])=>[
      key,document.querySelectorAll(selector).length
    ]));
    const main=document.querySelector('main');
    const attributeHints=[...new Set(
      [...(main?.querySelectorAll('[data-turn-key],[data-content-search-unit-key],[data-chatgpt-search-unit-key],[data-thread-find-target],[data-test-id]')||[])].slice(-80)
        .flatMap(el=>[...el.attributes].map(attr=>attr.name))
        .filter(name=>/^(data-(turn|content-search|chatgpt-search|thread|test|message|app-shell))/.test(name))
    )].slice(0,24);
    const debug={
      stopDetected:!!stop, stopEverSeen, assistantCount:assistantNodes().length,
      lastRole:role||'none', lastAnswerLength:core.readable(node).length,
      hasConversation:!!tabConversation, candidateButtons:candidates, scanCount,
      selectorCounts, attributeHints, stopProbe:stopProbe.snapshot()
    };
    const signature=JSON.stringify({...debug,scanCount:0});
    if(signature!==diagnosticsSignature){
      diagnosticsSignature=signature;
      status(lifecycle.state,{diagnostics:debug});
    }
  }
  const assistantNodes=()=>[...document.querySelectorAll(core.ASSISTANT)];
  const existingId=n=>n?.getAttribute('data-message-id')||n?.getAttribute('data-content-search-unit-key')||n?.id||'';
  const makeBaseline=()=>{ baseline=new Set(assistantNodes().map(n=>`${existingId(n)}\u0000${core.readable(n)}`)); };
  const digest=async raw=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))].map(x=>x.toString(16).padStart(2,'0')).join('');
  const status=(state,extra={})=>chrome.runtime.sendMessage({type:'OBSERVED_STATE',state,conversation_id:tabConversation,...extra}).catch(()=>{});
  const lifecycle=new core.Lifecycle({onState:state=>status(state),onCompleted:async ({conv,node,text})=>{
    if(!active || conv!==tabConversation || core.conversation(location.href)!==conv)return;
    // The UI may still be streaming or may have replaced the final turn during
    // stabilization. Fail closed instead of shipping a partial or stale answer.
    const current=core.lastAssistant(document);
    if(document.querySelector(core.STOP) || !current ||
       core.lastTurnRole(document)!=='assistant' ||
       existingId(current)!==existingId(node) || core.readable(current)!==text)return;
    const identity=core.messageIdentity(current,text,conv);
    if(lastProcessed===identity || baseline.has(`${existingId(node)}\u0000${text}`))return;
    lastProcessed=identity;
    const id=await digest(identity);
    chrome.runtime.sendMessage({type:'CAPTURE',payload:{schema_version:1,message_id:id,conversation_id:conv,text,observed_at:new Date().toISOString()}}).catch(err=>status('ERROR',{error:String(err)}));
  }});
  // Capture deliberate Stop button clicks in capture phase, before ChatGPT removes it.
  document.addEventListener('click',e=>{
    if(e.target?.closest?.(core.STOP)){sawUserStop=true;lifecycle.cancel();status('CANCELLED');}
  },true);
  function scan(){
    if(!active)return;
    if(route!==location.href){route=location.href;tabConversation=core.conversation(route);lifecycle.invalidate();stopProbe.reset();makeBaseline();}
    if(sawUserStop){ if(!document.querySelector(core.STOP))sawUserStop=false;return; }
    const node=core.lastAssistant(document);
    const stop=document.querySelector(core.STOP);
    const role=core.lastTurnRole(document);
    scanCount++;
    if(stop)stopEverSeen=true;
    stopProbe.observe(document,core.readable(node).length);
    reportDiagnostics(stop,node,role);
    lifecycle.observe({stop:!!stop,conv:tabConversation,node,text:core.readable(node),role});
  }
  let scanPending=false;
  function queueScan(){if(scanPending)return;scanPending=true;queueMicrotask(()=>{scanPending=false;scan();});}
  makeBaseline();
  observer=new MutationObserver(queueScan);
  observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-label','data-testid','data-message-author-role']});
  window.addEventListener('popstate',queueScan);
  window.addEventListener('hashchange',queueScan);
  document.addEventListener('visibilitychange',queueScan);
  // SPA navigation may replace history without popstate. Observer catches DOM changes.
  chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
    if(msg.type==='SET_CAPTURE'){active=!!msg.enabled;lifecycle.invalidate();makeBaseline();status(active?'IDLE':'DISABLED');reply({ok:true});return;}
    if(msg.type==='GET_TAB_STATE'){reply({ok:true,conversation_id:core.conversation(location.href),state:lifecycle.state});return;}
    if(msg.type==='REQUEST_DIAGNOSTICS'){diagnosticsSignature='';scan();reply({ok:true});return;}
    if(msg.type!=='STAGE_MESSAGE')return;
    (async()=>{
      if(!msg.conversation_id || core.conversation(location.href)!==msg.conversation_id)throw Error('conversation_mismatch');
      if(document.querySelector(core.STOP))throw Error('generation_active');
      const editor=document.querySelector('#prompt-textarea[contenteditable="true"], [data-testid="composer-rich-text-input"][contenteditable="true"], #prompt-textarea textarea, textarea#prompt-textarea');
      if(!editor)throw Error('editor_not_found');
      const old=(editor.isContentEditable?editor.innerText:editor.value)||'';
      if(old.trim())throw Error('composer_not_empty');
      editor.focus();
      if(editor.isContentEditable){
        // execCommand insertText emits browser editing/input semantics expected by React/ProseMirror.
        const inserted=document.execCommand('insertText',false,msg.text);
        if(!inserted){editor.textContent=msg.text;editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:msg.text}));}
      }else{
        const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
        setter.call(editor,msg.text);editor.dispatchEvent(new Event('input',{bubbles:true}));
      }
      const actual=editor.isContentEditable?editor.innerText:editor.value;
      if(actual.replace(/\r\n/g,'\n')!==msg.text.replace(/\r\n/g,'\n'))throw Error('stage_verification_failed');
      if(!msg.auto_send)return {ok:true,status:'STAGED'};
      // Background must only set auto_send after a backend-issued, one-time claim.
      if(!msg.claim_id)throw Error('missing_claim');
      if(core.conversation(location.href)!==msg.conversation_id)throw Error('conversation_changed');
      const send=document.querySelector('[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Nachricht senden"]');
      if(!send || send.disabled)throw Error('send_button_unavailable');
      send.click();
      return {ok:true,status:'SUBMIT_CLICKED'}; // Not a confirmed server-side ChatGPT delivery.
    })().then(reply,e=>reply({ok:false,error:String(e.message||e)}));
    return true;
  });
  status('IDLE');scan();
})();
