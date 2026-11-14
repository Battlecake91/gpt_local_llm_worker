const byId=id=>document.getElementById(id);
const fmt=value=>value?JSON.stringify(value,null,2):'keine';
function display(s){
  byId('enabled').checked=!!s.captureEnabled;
  byId('worker').textContent=s.connected?'verbunden':'nicht verbunden';
  byId('token-status').textContent=s.tokenSaved?'Token gespeichert':'Kein Token gespeichert';
  byId('chat').textContent=Object.entries(s.tabs||{}).map(([id,x])=>`Tab ${id}: ${x.state} (${x.conversation_id||'ohne Chat-ID'})`).join('\n')||'kein Tab';
  byId('diagnostics').textContent=Object.entries(s.tabs||{}).map(([id,x])=>`Tab ${id}: ${fmt(x.diagnostics)}`).join('\n')||'keine';
  byId('capture').textContent=s.lastCapture?.preview||'keine';
  byId('transfer').textContent=fmt(s.lastTransfer);
  byId('outbound').textContent=fmt(s.lastOutbound);
  byId('pending').textContent=s.pending;
  byId('error').textContent=s.error||'keiner';
}
chrome.runtime.sendMessage({type:'GET_STATUS'}).then(display);
chrome.runtime.onMessage.addListener(msg=>{if(msg.type==='STATUS')display(msg.state);});
byId('enabled').addEventListener('change',e=>chrome.runtime.sendMessage({type:'SET_ENABLED',enabled:e.target.checked}));
byId('save').addEventListener('click',async()=>{
  const input=byId('token'),value=input.value;
  if(!value){byId('token-status').textContent='Bitte Token eingeben';return;}
  try{
    const result=await chrome.runtime.sendMessage({type:'SET_TOKEN',token:value});
    byId('token-status').textContent=result?.ok?'Token gespeichert':'Fehler: '+(result?.error||'unbekannt');
    if(result?.ok)input.value='';
  }catch(err){byId('token-status').textContent='Fehler: '+String(err);}
});
byId('clear-token').addEventListener('click',async()=>{
  try{
    const result=await chrome.runtime.sendMessage({type:'CLEAR_TOKEN'});
    byId('token-status').textContent=result?.ok?'Token gelöscht':'Fehler: '+(result?.error||'unbekannt');
  }catch(err){byId('token-status').textContent='Fehler: '+String(err);}
});
byId('sync').addEventListener('click',()=>chrome.runtime.sendMessage({type:'SYNC_NOW'}));

byId('diagnose').addEventListener('click',()=>chrome.runtime.sendMessage({type:'REFRESH_DIAGNOSTICS'}));

byId('preview-current').addEventListener('click',async()=>{
  const output=byId('preview-result');
  output.textContent='Lese vorhandene Antwort ...';
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.id || !tab.url?.startsWith('https://chatgpt.com/c/')){
      output.textContent='Kein aktiver ChatGPT-Konversationstab';return;
    }
    const result=await chrome.tabs.sendMessage(tab.id,{type:'PREVIEW_CURRENT_REPLY'});
    if(!result?.ok){output.textContent='Fehler: '+(result?.error||'unbekannt');return;}
    output.textContent='Zeichen: '+result.length+' | Zeilenumbrüche: '+result.newlineCount+
      ' | Codeblöcke: '+result.codeBlocks+
      (result.truncated?' | Vorschau abgeschnitten':'')+'\n\n'+result.text;
  }catch(err){output.textContent='Fehler: '+String(err);}
});

byId('copy-diagnostics').addEventListener('click',async()=>{
  const report=byId('diagnostics').textContent;
  try{
    await navigator.clipboard.writeText(report);
    byId('copy-result').textContent='Kopiert';
  }catch(err){
    byId('copy-result').textContent='Kopieren fehlgeschlagen: '+String(err);
  }
});
