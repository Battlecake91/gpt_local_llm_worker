const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../extension/background.js'),'utf8');
function harness({items=[],grant={allowed:false},tabConv='abc',failCapture=false}={}){
  const store=new Map(),calls=[],sent=[];const listeners={},s={};
  const runtime={onMessage:{addListener:fn=>listeners.message=fn},sendMessage:async()=>{}};
  const chrome={runtime,storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,store.get(k)])),set:async data=>{Object.entries(data).forEach(([k,v])=>store.set(k,v));}}},tabs:{onRemoved:{addListener:()=>{}},get:async id=>({id,url:'https://chatgpt.com/c/abc'}),sendMessage:async(id,msg)=>{sent.push(msg);if(msg.type==='GET_TAB_STATE')return {conversation_id:tabConv};return {ok:true,status:msg.auto_send?'SUBMIT_CLICKED':'STAGED'}},query:async()=>[]},sidePanel:{setPanelBehavior:async()=>{}},alarms:{create:()=>{},onAlarm:{addListener:()=>{}}}};
  const fetch=async(url,opt={})=>{calls.push({url,opt});if(url.endsWith('/captures')&&failCapture)throw Error('offline');let data;if(url.endsWith('/outbound'))data={items};else if(url.endsWith('/claim'))data=grant;else if(url.endsWith('/captures')){const o=JSON.parse(opt.body);data={message_id:o.message_id,status:'accepted'}}else data={status:'accepted'};return {ok:true,json:async()=>data}};
  const context={chrome,fetch,AbortSignal:{timeout:()=>undefined},URL,Date,Promise,Map,Set,JSON,encodeURIComponent,console};
  vm.runInNewContext(source,context);
  async function event(msg,sender={tab:{id:1}}){let replyValue;listeners.message(msg,sender,v=>replyValue=v);await new Promise(resolve=>setTimeout(resolve,20));return replyValue;}
  return {event,store,calls,sent};
}
test('stage-only never clicks send and acknowledges staging',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'STAGE_ONLY',text:'hello'}]});await h.event({type:'SET_TOKEN',token:'test'});assert.ok(h.sent.some(x=>x.type==='STAGE_MESSAGE'&&x.auto_send===false));assert.ok(h.calls.some(x=>x.url.endsWith('/ack')));});
test('auto-send denied without verified claim',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'hello'}]});await h.event({type:'SET_TOKEN',token:'test'});assert.ok(!h.sent.some(x=>x.type==='STAGE_MESSAGE'));});
test('approved result clicks once; persisted receipt blocks replay',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'hello'}],grant:{allowed:true,claim_id:'claim123',kind:'approved_ssh_result'}});await h.event({type:'SET_TOKEN',token:'test'});await h.event({type:'SYNC_NOW'});assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,1);assert.equal(h.store.get('receipt_x').status,'SUBMIT_CLICKED')});
test('wrong conversation prevents staging and auto sending',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'STAGE_ONLY',text:'hello'}],tabConv:'wrong'});await h.event({type:'SET_TOKEN',token:'test'});assert.ok(!h.sent.some(x=>x.type==='STAGE_MESSAGE'))});
test('failed capture remains queued and is retried',async()=>{const h=harness({failCapture:true});await h.event({type:'SET_TOKEN',token:'test'});await h.event({type:'CAPTURE',payload:{message_id:'abc',text:'hello',conversation_id:'abc'}});assert.equal(h.store.get('pendingCaptures').length,1)});
