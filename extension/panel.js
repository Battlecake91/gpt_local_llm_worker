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

let chatTabChoices=new Map();
async function refreshChatTabs(){
  const select=byId('capture-tab'),status=byId('tab-selection-status');
  const previous=select.value;
  status.textContent='Suche ChatGPT-Konversationen ...';
  try{
    const response=await chrome.runtime.sendMessage({type:'LIST_CHATGPT_TABS'});
    if(!response?.ok)throw Error(response?.error||'tab_lookup_failed');
    const items=Array.isArray(response.items)?response.items:[];
    chatTabChoices=new Map();
    select.replaceChildren();
    const placeholder=document.createElement('option');
    placeholder.value='';placeholder.textContent='ChatGPT-Konversation auswählen';
    select.append(placeholder);
    for(const tab of items){
      if(!Number.isSafeInteger(tab.tab_id)||typeof tab.conversation_id!=='string')continue;
      const key=String(tab.tab_id);
      chatTabChoices.set(key,{tab_id:tab.tab_id,conversation_id:tab.conversation_id});
      const option=document.createElement('option');
      option.value=key;
      option.textContent=(tab.active?'[Aktiv] ':'')+
        String(tab.title||'ChatGPT').slice(0,100)+' (Tab '+key+')';
      select.append(option);
    }
    if(chatTabChoices.has(previous))select.value=previous;
    else if(items.length===1 && chatTabChoices.size===1)select.value=String(items[0].tab_id);
    else select.value='';
    status.textContent=chatTabChoices.size+' Konversationen gefunden';
  }catch(err){
    chatTabChoices.clear();
    select.replaceChildren();
    status.textContent='Tab-Abfrage fehlgeschlagen: '+String(err.message||err);
  }
}
function selectedChat(){
  const key=byId('capture-tab').value;
  const selection=chatTabChoices.get(key);
  if(!selection)throw Error('Bitte zuerst einen ChatGPT-Tab auswaehlen');
  return selection;
}
byId('refresh-tabs').addEventListener('click',refreshChatTabs);
refreshChatTabs();

byId('capture-current').addEventListener('click',async()=>{
  const status=byId('manual-capture-status');
  const button=byId('capture-current');
  button.disabled=true;
  status.textContent='Prüfe stabile letzte Antwort ...';
  try{
    const result=await chrome.runtime.sendMessage({type:'CAPTURE_CURRENT_FROM_PANEL',...selectedChat()});
    if(!result?.ok)throw Error(result?.error||'capture_failed');
    status.textContent=result.status==='already_captured'
      ?'Bereits erfasst'
      :'Antwort zur Übertragung eingereiht (Status unter Letzte Übertragung prüfen)';
  }catch(err){status.textContent='Fehler: '+String(err.message||err);}
  finally{button.disabled=false;}
});
byId('preview-current').addEventListener('click',async()=>{
  const output=byId('preview-result');
  output.textContent='Lese vorhandene Antwort ...';
  try{
    const result=await chrome.runtime.sendMessage({
      type:'PREVIEW_SELECTED_REPLY',...selectedChat()
    });
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
async function refreshSSH(message=''){
  const status=byId('ssh-status'),container=byId('ssh-proposals');
  status.textContent='Lade Vorschläge ...';
  container.replaceChildren();
  try{
    const response=await chrome.runtime.sendMessage({type:'LIST_SSH_PROPOSALS'});
    if(!response?.ok)throw Error(response?.error||'unbekannt');
    const items=Array.isArray(response.items)?response.items:[];
    status.textContent=(message?message+' | ':'')+items.length+' offene SSH-Aufträge';
    for(const item of items){
      if(!item || !Array.isArray(item.commands) || !item.commands.length ||
         !/^[a-f0-9]{64}$/.test(item.command_sha256||''))continue;
      const section=sshNode('section');section.className='ssh-proposal';
      section.append(sshNode('h3','Auftrag '+item.request_id));
      section.append(sshNode('p','Host: '+item.host_id+' | Chat: '+item.conversation_id+' | Tab: '+item.tab_id));
      section.append(sshNode('p','SSH-Benutzer und Hostkey: im Mock nicht konfiguriert (keine Ausführung)'));
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
          await refreshSSH('Auftrag '+item.request_id+': '+answer.status);
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

async function refreshMockResults(){
  const status=byId('mock-results-status'),container=byId('mock-results-list');
  status.textContent='Lade gespeicherte Mock-Ergebnisse ...';
  container.replaceChildren();
  try{
    const reply=await chrome.runtime.sendMessage({type:'LIST_MOCK_RESULTS'});
    if(!reply?.ok)throw Error(reply?.error||'unbekannt');
    const items=Array.isArray(reply.items)?reply.items:[];
    status.textContent=items.length+' gespeicherte Mock-Ergebnisse';
    for(const item of items){
      if(!item || !item.result || item.result.mode!=='MOCK_ONLY' ||
         !Array.isArray(item.result.commands))continue;
      const section=sshNode('section');section.className='ssh-proposal';
      const details=sshNode('details');
      details.append(sshNode('summary',item.request_id+' | '+item.status+' | '+item.host_id));
      details.append(sshNode('p','Originalchat: '+item.conversation_id+' | Tab: '+item.tab_id));
      details.append(sshNode('p','Mock-Benutzer: '+item.result.username));
      details.append(sshNode('p','Simulierter Status: '+item.result.status));
      for(const command of item.result.commands){
        const entry=sshNode('section');
        entry.append(sshNode('strong','Befehl-ID: '+command.id+
          ' | Exitcode: '+String(command.exit_code)+
          ' | Timeout: '+String(command.timed_out)+
          ' | Ausgabe gekürzt: '+String(command.truncated)));
        entry.append(sshNode('pre','STDOUT:\n'+String(command.stdout||'')+
          '\nSTDERR:\n'+String(command.stderr||'')));
        details.append(entry);
      }
      section.append(details);
      container.append(section);
    }
  }catch(err){status.textContent='Fehler: '+String(err);}
}
byId('mock-results-refresh').addEventListener('click',refreshMockResults);
byId('mock-results-details').addEventListener('toggle',()=>{
  if(byId('mock-results-details').open)refreshMockResults();
});
