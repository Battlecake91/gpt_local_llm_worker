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

function sshNode(tag,text){
  const node=document.createElement(tag);
  if(text!==undefined)node.textContent=String(text);
  return node;
}
async function refreshSSH(){
  const status=byId('ssh-status'),container=byId('ssh-proposals');
  status.textContent='Lade Vorschläge ...';
  container.replaceChildren();
  try{
    const response=await chrome.runtime.sendMessage({type:'LIST_SSH_PROPOSALS'});
    if(!response?.ok)throw Error(response?.error||'unbekannt');
    const items=Array.isArray(response.items)?response.items:[];
    status.textContent=items.length+' offene SSH-Aufträge';
    for(const item of items){
      if(!item || !Array.isArray(item.commands) || !item.commands.length ||
         !/^[a-f0-9]{64}$/.test(item.command_sha256||''))continue;
      const section=sshNode('section');section.className='ssh-proposal';
      section.append(sshNode('h3','Auftrag '+item.request_id));
      section.append(sshNode('p','Host: '+item.host_id+' | Chat: '+item.conversation_id+' | Tab: '+item.tab_id));
      section.append(sshNode('p','Arbeitsverzeichnis: '+item.working_directory));
      section.append(sshNode('p','Beschreibung (unverifizierter Modelltext): '+item.description));
      section.append(sshNode('p','Befehlsblock SHA-256: '+item.command_sha256));
      const listing=item.commands.map((cmd,index)=>
        (index+1)+'. ['+cmd.id+'] Timeout '+cmd.timeout_seconds+'s\n'+cmd.command
      ).join('\n\n');
      section.append(sshNode('pre',listing));
      const checkbox=sshNode('input');checkbox.type='checkbox';
      const label=sshNode('label');
      label.append(checkbox,document.createTextNode(' Ich habe alle Befehle und das Ziel geprüft und bestätige den gesamten Block.'));
      section.append(label);
      const approve=sshNode('button','Gesamten Block freigeben');
      approve.type='button';approve.disabled=true;
      const reject=sshNode('button','Ablehnen');reject.type='button';
      checkbox.addEventListener('change',()=>{approve.disabled=!checkbox.checked;});
      async function decide(action){
        approve.disabled=true;reject.disabled=true;checkbox.disabled=true;
        const decision={
          action,request_id:item.request_id,command_sha256:item.command_sha256,
          tab_id:item.tab_id,conversation_id:item.conversation_id,confirmed:true
        };
        try{
          const answer=await chrome.runtime.sendMessage({type:'DECIDE_SSH_PROPOSAL',decision});
          if(!answer?.ok)throw Error(answer?.error||'unbekannt');
          status.textContent='Auftrag '+item.request_id+': '+answer.status;
          await refreshSSH();
        }catch(err){
          status.textContent='Freigabe fehlgeschlagen: '+String(err);
          checkbox.disabled=false;reject.disabled=false;
          approve.disabled=!checkbox.checked;
        }
      }
      approve.addEventListener('click',()=>{
        if(!checkbox.checked)return;
        decide('approve');
      });
      reject.addEventListener('click',()=>decide('reject'));
      section.append(approve,reject);
      container.append(section);
    }
  }catch(err){status.textContent='Fehler: '+String(err);}
}
byId('ssh-refresh').addEventListener('click',refreshSSH);
byId('ssh-review').addEventListener('toggle',()=>{
  if(byId('ssh-review').open)refreshSSH();
});
