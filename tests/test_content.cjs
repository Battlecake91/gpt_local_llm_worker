const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const core=require('../extension/bridge-core.js');
const source=fs.readFileSync(require('node:path').join(__dirname,'../extension/content.js'),'utf8');
function setup({conversation='abc',empty=true,sendEnabled=true,modernOnly=false}={}){
  const outbound=[],sent={count:0},listeners={};
  const editor={isContentEditable:true,innerText:empty?'':'Existing text',textContent:'',focus(){},dispatchEvent(){}};
  const send={disabled:!sendEnabled,click(){sent.count++}};
  const doc={documentElement:{},querySelector(sel){
    if(modernOnly){if(sel.includes('form[data-chatgpt-composer] [contenteditable="true"][role="textbox"]'))return editor;}
    else if(sel.includes('#prompt-textarea'))return editor;
    if(sel.includes('[data-testid="send-button"]'))return send;
    return null;
  },querySelectorAll:()=>[],addEventListener(){},execCommand:(action,unused,text)=>{editor.innerText=text;return true}};
  const chrome={runtime:{sendMessage:async obj=>outbound.push(obj),onMessage:{addListener:fn=>listeners.message=fn}}};
  const MutationObserver=class{observe(){}};
  const loc={href:`https://chatgpt.com/c/${conversation}`};
  const context={globalThis:null,BridgeCore:core,BridgeExtractor:{inspectStructure:()=>null},BridgeStopProbe:{StopProbe:class{reset(){}observe(){}snapshot(){return {controlStates:[]}}}},chrome,document:doc,location:loc,MutationObserver,window:{addEventListener(){}},queueMicrotask,crypto:globalThis.crypto,TextEncoder,Date,InputEvent:class{},Event:class{},setTimeout,clearTimeout};context.globalThis=context;
  vm.runInNewContext(source,context);
  const deliver=msg=>new Promise(resolve=>{listeners.message(msg,{},result=>resolve(result))});
  return {deliver,editor,sent,loc,outbound};
}
test('staging preserves multiple lines without sending',async()=>{const h=setup();const text='One\n```\ncode\n```';const r=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text,auto_send:false});assert.equal(r.status,'STAGED');assert.equal(h.editor.innerText,text);assert.equal(h.sent.count,0)});
test('auto-send requires one-time claim marker',async()=>{const h=setup();const r=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text:'test',auto_send:true});assert.equal(r.ok,false);assert.equal(h.sent.count,0)});
test('auto-send with claim clicks once and reports only click',async()=>{const h=setup();const r=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text:'test',auto_send:true,claim_id:'approved'});assert.equal(r.status,'SUBMIT_CLICKED');assert.equal(h.sent.count,1)});
test('wrong chat cannot stage',async()=>{const h=setup();const r=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'different',text:'test'});assert.equal(r.ok,false);assert.equal(h.sent.count,0)});
test('nonempty composer is not overwritten',async()=>{const h=setup({empty:false});const r=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text:'test'});assert.equal(r.ok,false);assert.equal(h.editor.innerText,'Existing text')});
test('send unavailable remains safe',async()=>{const h=setup({sendEnabled:false});const r=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text:'test',auto_send:true,claim_id:'approved'});assert.equal(r.ok,false);assert.equal(h.sent.count,0)});

test('read-only preview never triggers capture, backend delivery or send',async()=>{
  const h=setup();
  const prior=h.outbound.length;
  const reply=await h.deliver({type:'PREVIEW_CURRENT_REPLY'});
  assert.equal(reply.ok,false);
  assert.equal(h.outbound.length,prior);
  assert.equal(h.sent.count,0);
});

test('modern ChatGPT ProseMirror composer stages multiline text without submit',async()=>{
  const h=setup({modernOnly:true});
  const text='Ergebnis:\n\n```sh\nprintf "test"\n```\n\nNur bereitstellen.';
  const result=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text,auto_send:false});
  assert.equal(result.status,'STAGED');
  assert.equal(h.editor.innerText,text);
  assert.equal(h.sent.count,0);
});
test('stage-only rejects blank text before editing',async()=>{
  const h=setup({modernOnly:true});
  const result=await h.deliver({type:'STAGE_MESSAGE',conversation_id:'abc',text:'',auto_send:false});
  assert.equal(result.ok,false);
  assert.equal(h.editor.innerText,'');
  assert.equal(h.sent.count,0);
});
