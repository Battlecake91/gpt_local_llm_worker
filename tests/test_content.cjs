const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const core=require('../extension/bridge-core.js');
const source=fs.readFileSync(require('node:path').join(__dirname,'../extension/content.js'),'utf8');
function setup({conversation='abc',empty=true,sendEnabled=true}={}){
  const outbound=[],sent={count:0},listeners={};
  const editor={isContentEditable:true,innerText:empty?'':'Existing text',textContent:'',focus(){},dispatchEvent(){}};
  const send={disabled:!sendEnabled,click(){sent.count++}};
  const doc={documentElement:{},querySelector(sel){
    if(sel.includes('#prompt-textarea'))return editor;
    if(sel.includes('[data-testid="send-button"]'))return send;
    return null;
  },querySelectorAll:()=>[],addEventListener(){},execCommand:(action,unused,text)=>{editor.innerText=text;return true}};
  const chrome={runtime:{sendMessage:async obj=>outbound.push(obj),onMessage:{addListener:fn=>listeners.message=fn}}};
  const MutationObserver=class{observe(){}};
  const loc={href:`https://chatgpt.com/c/${conversation}`};
  const context={globalThis:null,BridgeCore:core,chrome,document:doc,location:loc,MutationObserver,window:{addEventListener(){}},queueMicrotask,crypto:globalThis.crypto,TextEncoder,Date,InputEvent:class{},Event:class{},setTimeout,clearTimeout};context.globalThis=context;
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
