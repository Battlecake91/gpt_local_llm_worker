const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const {webcrypto,createHash}=require('node:crypto');
const digest=text=>createHash('sha256').update(text,'utf8').digest('hex');
const approval=text=>({job_id:'job-1',approval_id:'approved-1',host_id:'lab-host',command_sha256:digest('host=lab-host;commands=uptime'),result_sha256:digest(text)});
const approvalGrant=(item)=>({allowed:true,claim_id:'claim123',kind:'approved_ssh_result',outbound_id:item.id,conversation_id:item.conversation_id,tab_id:item.tab_id,...item.approval});
const source=fs.readFileSync(require('node:path').join(__dirname,'../extension/background.js'),'utf8');
function harness({items=[],grant={allowed:false},tabConv='abc',failCapture=false,rejectToken=null,initialStore={}}={}){
  const store=new Map(Object.entries(initialStore)),calls=[],sent=[];const listeners={},s={};
  const runtime={onMessage:{addListener:fn=>listeners.message=fn},sendMessage:async()=>{},getURL:path=>'chrome-extension://testid/'+path};
  const chrome={runtime,storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,store.get(k)])),set:async data=>{Object.entries(data).forEach(([k,v])=>store.set(k,v));},remove:async key=>store.delete(key),setAccessLevel:async()=>{}}},tabs:{onRemoved:{addListener:()=>{}},get:async id=>({id,url:'https://chatgpt.com/c/abc'}),sendMessage:async(id,msg)=>{sent.push(msg);if(msg.type==='GET_TAB_STATE')return {conversation_id:tabConv};return {ok:true,status:msg.auto_send?'SUBMIT_CLICKED':'STAGED'}},query:async()=>[]},sidePanel:{setPanelBehavior:async()=>{}},alarms:{create:()=>{},onAlarm:{addListener:()=>{}}}};
  const fetch=async(url,opt={})=>{calls.push({url,opt});if(rejectToken && opt.headers?.Authorization===`Bearer ${rejectToken}`)return {ok:false,status:401};if(url.endsWith('/captures')&&failCapture)throw Error('offline');let data;if(url.endsWith('/outbound'))data={items};else if(url.endsWith('/claim'))data=grant;else if(url.endsWith('/captures')){const o=JSON.parse(opt.body);data={message_id:o.message_id,status:'accepted'}}else data={status:'accepted'};return {ok:true,json:async()=>data}};
  const context={chrome,fetch,AbortSignal:{timeout:()=>undefined},URL,Date,Promise,Map,Set,JSON,encodeURIComponent,console,crypto:webcrypto,TextEncoder};
  vm.runInNewContext(source,context);
  async function event(msg,sender={tab:{id:1}}){let replyValue;listeners.message(msg,sender,v=>replyValue=v);await new Promise(resolve=>setTimeout(resolve,20));return replyValue;}
  return {event,store,calls,sent};
}
test('stage-only never clicks send and acknowledges staging',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'STAGE_ONLY',text:'hello'}]});await h.event({type:'SET_TOKEN',token:'test'});assert.ok(h.sent.some(x=>x.type==='STAGE_MESSAGE'&&x.auto_send===false));assert.ok(h.calls.some(x=>x.url.endsWith('/ack')));});
test('auto-send denied without verified claim',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'hello'}]});await h.event({type:'SET_TOKEN',token:'test'});assert.ok(!h.sent.some(x=>x.type==='STAGE_MESSAGE'));});
test('approved bound result clicks once; persisted receipt blocks replay',async()=>{const item={id:'x',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'hello',approval:approval('hello')};const h=harness({items:[item],grant:approvalGrant(item)});await h.event({type:'SET_TOKEN',token:'test'});await h.event({type:'SYNC_NOW'});assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,1);assert.equal(h.store.get('receipt_x').status,'SUBMIT_CLICKED')});
test('wrong conversation prevents staging and auto sending',async()=>{const h=harness({items:[{id:'x',tab_id:1,conversation_id:'abc',mode:'STAGE_ONLY',text:'hello'}],tabConv:'wrong'});await h.event({type:'SET_TOKEN',token:'test'});assert.ok(!h.sent.some(x=>x.type==='STAGE_MESSAGE'))});
test('failed capture remains queued and is retried',async()=>{const h=harness({failCapture:true});await h.event({type:'SET_TOKEN',token:'test'});await h.event({type:'CAPTURE',payload:{message_id:'abc',text:'hello',conversation_id:'abc'}});assert.equal(h.store.get('pendingCaptures').length,1)});

test('bearer token is persisted without leaking via GET_STATUS',async()=>{
  const h=harness();
  const reply=await h.event({type:'SET_TOKEN',token:'test-permanent-secret'});
  assert.equal(reply.ok,true);
  assert.equal(h.store.get('workerBearerToken'),'test-permanent-secret');
  const status=await h.event({type:'GET_STATUS'});
  assert.equal(status.tokenSaved,true);
  assert.ok(!JSON.stringify(status).includes('test-permanent-secret'));
});
test('stored bearer token authenticates after service worker startup',async()=>{
  const h=harness({initialStore:{workerBearerToken:'restored-secret'}});
  await h.event({type:'SYNC_NOW'});
  const get=h.calls.find(call=>call.url.endsWith('/outbound'));
  assert.equal(get.opt.headers.Authorization,'Bearer restored-secret');
});
test('clear-token removes stored credential and prevents network use',async()=>{
  const h=harness({initialStore:{workerBearerToken:'restored-secret'}});
  const removed=await h.event({type:'CLEAR_TOKEN'});
  assert.equal(removed.ok,true);
  assert.equal(h.store.has('workerBearerToken'),false);
  const callsBefore=h.calls.length;
  await h.event({type:'SYNC_NOW'});
  assert.equal(h.calls.length,callsBefore);
  const status=await h.event({type:'GET_STATUS'});
  assert.equal(status.tokenSaved,false);
});

test('persisted ATTEMPTING receipt blocks auto-send replay after MV3 restart',async()=>{
  const item={id:'restart-job',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'output'};
  const h=harness({items:[item],grant:{allowed:true,claim_id:'claim',kind:'approved_ssh_result'},
    initialStore:{workerBearerToken:'persisted',receipt_restart_job:{status:'ATTEMPTING'}}});
  await h.event({type:'SYNC_NOW'});
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
  assert.equal(h.calls.filter(x=>x.url.endsWith('/claim')).length,0);
});
test('concurrent sync requests cannot duplicate an auto-send',async()=>{
  const item={id:'one-time',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'output',approval:approval('output')};
  const h=harness({items:[item],grant:approvalGrant(item)});
  await h.event({type:'SET_TOKEN',token:'test'});
  await Promise.all([h.event({type:'SYNC_NOW'}),h.event({type:'SYNC_NOW'})]);
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,1);
});

test('auto-send without immutable job attestation is rejected before claim',async()=>{
  const item={id:'unbound',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'output'};
  const h=harness({items:[item],grant:{allowed:true,claim_id:'claim',kind:'approved_ssh_result'}});
  await h.event({type:'SET_TOKEN',token:'test'});
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
  assert.equal(h.calls.filter(x=>x.url.endsWith('/claim')).length,0);
});
test('auto-send fails closed when outbound result digest differs from text',async()=>{
  const item={id:'tampered',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'tampered',approval:approval('original')};
  const h=harness({items:[item],grant:approvalGrant(item)});
  await h.event({type:'SET_TOKEN',token:'test'});
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
  assert.equal(h.calls.filter(x=>x.url.endsWith('/claim')).length,0);
});
test('auto-send fails closed when claim binds a different approval or conversation',async()=>{
  const item={id:'mismatch',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'output',approval:approval('output')};
  const grant=approvalGrant(item);grant.approval_id='different';
  const h=harness({items:[item],grant});
  await h.event({type:'SET_TOKEN',token:'test'});
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
});
test('legacy allow-and-claim alone cannot authorize automatic sending',async()=>{
  const item={id:'old',tab_id:1,conversation_id:'abc',mode:'AUTO_SEND_APPROVED_RESULT',text:'output',approval:approval('output')};
  const h=harness({items:[item],grant:{allowed:true,claim_id:'claim123',kind:'approved_ssh_result'}});
  await h.event({type:'SET_TOKEN',token:'test'});
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
});

test('web tab cannot list or approve SSH proposals',async()=>{
  const h=harness();
  await h.event({type:'SET_TOKEN',token:'test'});
  const callsBefore=h.calls.length;
  const untrusted={tab:{id:1},url:'https://chatgpt.com/c/abc'};
  const result=await h.event({type:'DECIDE_SSH_PROPOSAL',decision:{action:'approve'}},untrusted);
  assert.equal(result.ok,false);
  assert.equal(result.error,'untrusted_review_sender');
  assert.equal(h.calls.length,callsBefore);
  const listing=await h.event({type:'LIST_SSH_PROPOSALS'},untrusted);
  assert.equal(listing.ok,false);
});
test('trusted sidepanel cannot approve malformed or altered decision',async()=>{
  const h=harness();
  await h.event({type:'SET_TOKEN',token:'test'});
  const sender={url:'chrome-extension://testid/panel.html'};
  const baseline=h.calls.length;
  const result=await h.event({type:'DECIDE_SSH_PROPOSAL',decision:{
    action:'approve',request_id:'abc',command_sha256:'bad',tab_id:1,
    conversation_id:'abc',confirmed:true
  }},sender);
  assert.equal(result.ok,false);
  assert.equal(h.calls.length,baseline);
});
test('trusted sidepanel verifies original chat before posting review decision',async()=>{
  const h=harness({tabConv:'other'});
  await h.event({type:'SET_TOKEN',token:'test'});
  const baseline=h.calls.length;
  const result=await h.event({type:'DECIDE_SSH_PROPOSAL',decision:{
    action:'approve',request_id:'req-1',command_sha256:'a'.repeat(64),
    tab_id:1,conversation_id:'abc',confirmed:true
  }},{url:'chrome-extension://testid/panel.html'});
  assert.equal(result.ok,false);
  assert.equal(h.calls.length,baseline);
});

test('trusted sidepanel records verified mock approval without triggering browser send',async()=>{
  const h=harness({initialStore:{workerBearerToken:'test'}});
  const sender={url:'chrome-extension://testid/panel.html'};
  const proposal={
    action:'approve',request_id:'req-1',command_sha256:'a'.repeat(64),
    tab_id:1,conversation_id:'abc',confirmed:true
  };
  const result=await h.event({type:'DECIDE_SSH_PROPOSAL',decision:proposal},sender);
  assert.equal(result.ok,true);
  const calls=h.calls.filter(x=>x.url.endsWith('/ssh/proposals/req-1/approve'));
  assert.equal(calls.length,1);
  assert.equal(JSON.parse(calls[0].opt.body).command_sha256,proposal.command_sha256);
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
});

test('mock history retrieval is restricted to the extension sidepanel',async()=>{
  const h=harness({initialStore:{workerBearerToken:'test'}});
  // The MV3 worker may run its startup /outbound sync concurrently.
  // Only requests to the protected history endpoint are relevant here.
  const historyCalls=()=>h.calls.filter(x=>x.url.endsWith('/ssh/mock-results')).length;
  const baseline=historyCalls();
  const rejected=await h.event({type:'LIST_MOCK_RESULTS'},{
    url:'https://chatgpt.com/c/abc',tab:{id:1}});
  assert.equal(rejected.ok,false);
  assert.equal(rejected.error,'untrusted_review_sender');
  assert.equal(historyCalls(),baseline);
  const accepted=await h.event({type:'LIST_MOCK_RESULTS'},{
    url:'chrome-extension://testid/panel.html'});
  assert.equal(accepted.ok,true);
  assert.ok(Array.isArray(accepted.items));
  assert.equal(h.calls.filter(x=>x.url.endsWith('/ssh/mock-results')).length,1);
  assert.equal(h.sent.filter(x=>x.type==='STAGE_MESSAGE').length,0);
});

test('401 rejection stops capture storm, persists queue and resumes after new token',async()=>{
  const payload={message_id:'capture-one',text:'example',conversation_id:'abc'};
  const initialStore={
    workerBearerToken:'expired-token',
    pendingCaptures:[
      {payload,attempt:0},
      {payload:{...payload,message_id:'capture-two'},attempt:0},
    ],
  };
  const h=harness({rejectToken:'expired-token',initialStore});
  await h.event({type:'SYNC_NOW'});
  assert.equal(h.calls.filter(x=>x.url.endsWith('/captures')).length,1);
  assert.equal(h.store.get('pendingCaptures').length,2);
  await h.event({type:'SET_TOKEN',token:'valid-new-token'});
  assert.equal(h.store.get('pendingCaptures').length,0);
  assert.equal(h.calls.filter(x=>x.url.endsWith('/captures')).length,3);
});
