const test=require('node:test');
const assert=require('node:assert/strict');
const {Lifecycle,STATES,conversation,readable,messageIdentity}=require('../extension/bridge-core.js');
function fixture(text='Line one\n  code();\nLine three'){
  return {id:'assistant-42',getAttribute:k=>k==='data-message-id'?'assistant-42':null,
    querySelector:()=>({innerText:text})};
}
function clock(){let now=0, q=[];return {schedule:(fn,ms)=>{const a={at:now+ms,fn};q.push(a);return a},clear:h=>{q=q.filter(x=>x!==h)},advance:ms=>{now+=ms;const due=q.filter(x=>x.at<=now);q=q.filter(x=>x.at>now);due.forEach(x=>x.fn())}};}
const conv='abc-123';
function setup(){const t=clock(),out=[],states=[];const life=new Lifecycle({...t,stableMs:100,onCompleted:x=>out.push(x),onState:x=>states.push(x)});return {t,out,states,life};}
function observe(life,stop,text='Hello',node=fixture(text),role='assistant',c=conv){life.observe({stop,text,node,role,conv:c});}
test('stop present then absent produces exactly one stabilized result',()=>{const {t,out,life,states}=setup();observe(life,true);observe(life,false);t.advance(99);assert.equal(out.length,0);t.advance(1);assert.equal(out.length,1);assert.equal(life.state,STATES.COMPLETED);assert.deepEqual(states,[STATES.GENERATING,STATES.FINALIZING,STATES.COMPLETED]);observe(life,false);assert.equal(out.length,1)});
test('streaming waits until final text stabilizes',()=>{const {t,out,life}=setup();observe(life,true,'one');observe(life,true,'one two');observe(life,false,'one two');t.advance(50);observe(life,false,'one two three');t.advance(50);assert.equal(out.length,0);t.advance(50);assert.equal(out[0].text,'one two three')});
test('manual cancellation rejects incomplete response',()=>{const {t,out,life}=setup();observe(life,true);life.cancel();observe(life,false);t.advance(999);assert.equal(out.length,0);assert.equal(life.state,STATES.CANCELLED)});
test('reload starts without stop history and never captures old answers',()=>{const {t,out,life}=setup();observe(life,false);t.advance(200);assert.equal(out.length,0)});
test('route transition invalidates previous generation',()=>{const {t,out,life}=setup();observe(life,true);observe(life,false);observe(life,false,'wrong',fixture('wrong'),'assistant','next-chat');t.advance(200);assert.equal(out.length,0)});
test('mutation storms do not duplicate completion',()=>{const {t,out,life}=setup();observe(life,true);for(let i=0;i<20;i++)observe(life,false);t.advance(100);assert.equal(out.length,1)});
test('last user message prevents false finalize',()=>{const {t,out,life}=setup();observe(life,true);observe(life,false,'ignored',fixture(),'user');t.advance(500);assert.equal(out.length,0)});
test('code and multiline extraction keeps newlines',()=>{assert.equal(readable(fixture()),'Line one\n  code();\nLine three')});
test('conversation identification refuses wrong or temporary chats',()=>{assert.equal(conversation('https://chatgpt.com/c/abc-123'),'abc-123');assert.equal(conversation('https://chatgpt.com/'),null);});

test('unrelated DOM mutations do not postpone an unchanged final answer',()=>{
  const {t,out,life}=setup();
  const node=fixture('Stable final answer');
  observe(life,true,'Stable final answer',node);
  observe(life,false,'Stable final answer',node);
  for(let i=0;i<20;i++){t.advance(4);observe(life,false,'Stable final answer',node);}
  t.advance(20);
  assert.equal(out.length,1);
  assert.equal(out[0].text,'Stable final answer');
});
test('changed answer text restarts finalization timer',()=>{
  const {t,out,life}=setup();
  const node=fixture('Changed final answer');
  observe(life,true,'Draft answer',node);
  observe(life,false,'Draft answer',node);
  t.advance(80);
  observe(life,false,'Changed final answer',node);
  t.advance(20);
  assert.equal(out.length,0);
  t.advance(80);
  assert.equal(out.length,1);
  assert.equal(out[0].text,'Changed final answer');
});

test('modern content-search turn markers select final assistant and role in DOM order',()=>{
  const {ASSISTANT,USER,lastAssistant,lastTurnRole,roleOf,readable,messageIdentity}=require('../extension/bridge-core.js');
  const turn=(key,rendered)=>({
    id:'',getAttribute:name=>name==='data-content-search-unit-key'?key:null,
    querySelector:selector=>selector.includes('data-markdown-text-style')?{innerText:rendered}:null,
    textContent:rendered
  });
  const user=turn('conversation:turn-4:user','Frage');
  const answer=turn('conversation:turn-5:assistant','Erste Zeile\n  print(123)\nLetzte Zeile');
  const doc={querySelectorAll:selector=>{
    if(selector===ASSISTANT)return [answer];
    if(selector===`${ASSISTANT},${USER}`)return [user,answer];
    return [];
  }};
  assert.equal(roleOf(user),'user');
  assert.equal(roleOf(answer),'assistant');
  assert.equal(lastAssistant(doc),answer);
  assert.equal(lastTurnRole(doc),'assistant');
  assert.equal(readable(answer),'Erste Zeile\n  print(123)\nLetzte Zeile');
  assert.match(messageIdentity(answer,readable(answer),'abc'),/turn-5:assistant/);
});
test('modern assistant remains inert without observed stop lifecycle',()=>{
  const {t,out,life}=setup();
  const node=fixture('Legacy and modern both require observed stop');
  observe(life,false,'Modern reply',node);
  t.advance(1000);
  assert.equal(out.length,0);
});

test('German Stoppen control from Windows Brave trace drives generation completion',()=>{
  const {STOP}=require('../extension/bridge-core.js');
  assert.ok(STOP.split(',').includes('button[aria-label="Stoppen"]'));
  const {t,out,life}=setup();
  const node=fixture('Codeblock\\nprint(123)\\nMehrzeilige Erklärung');
  const foundStop=aria=>STOP.split(',').includes(`button[aria-label="${aria}"]`);
  observe(life,foundStop('Stoppen'),'Noch im Aufbau',node);
  assert.equal(life.state,STATES.GENERATING);
  observe(life,false,'Codeblock\\nprint(123)\\nMehrzeilige Erklärung',node);
  assert.equal(life.state,STATES.FINALIZING);
  t.advance(100);
  assert.equal(out.length,1);
  assert.equal(life.state,STATES.COMPLETED);
  assert.equal(out[0].text,'Codeblock\\nprint(123)\\nMehrzeilige Erklärung');
});

test('project-scoped ChatGPT conversation URL is recognized',()=>{
  assert.equal(conversation('https://chatgpt.com/g/g-p-workspace-123/c/abc-123'),'abc-123');
  assert.equal(conversation('https://chatgpt.com/g/g-p-workspace-123/c/abc-123?x=1'),'abc-123');
  assert.equal(conversation('https://chatgpt.com/g/g-p-workspace-123'),null);
});
