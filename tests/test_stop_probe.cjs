const test=require('node:test');
const assert=require('node:assert/strict');
const {StopProbe}=require('../extension/stop-probe.js');
function button({testid='',aria='',title='',disabled=false,rects=0,paths=1}={}){
  return {
    tagName:'BUTTON',disabled,
    getAttribute:name=>({'data-testid':testid,'aria-label':aria,title}[name]||null),
    querySelector:name=>name==='svg'?{querySelectorAll:tag=>Array.from({length:tag==='rect'?rects:paths})}:null
  };
}
function fixture(list){
  const form={querySelectorAll:()=>list};
  return {querySelector:selector=>selector==='form[data-chatgpt-composer]'?form:null};
}
test('captures composer button transitions without message text',()=>{
  const probe=new StopProbe();
  const idle=fixture([button({testid:'send',aria:'Senden'})]);
  const streaming=fixture([button({testid:'custom-control',aria:'Anhalten',rects:1,paths:0})]);
  probe.observe(idle,0);
  probe.observe(streaming,20);
  probe.observe(streaming,78);
  probe.observe(idle,100);
  const trace=probe.snapshot();
  assert.equal(trace.controlChanges,3);
  assert.equal(trace.controlStates.length,3);
  assert.equal(trace.controlStates[1].controls[0].svgRects,1);
  assert.equal(trace.controlStates[1].answerLength,20);
  assert.equal(trace.lastAnswerLength,100);
  assert.equal(JSON.stringify(trace).includes('actual response content'),false);
});
test('bounds transition history and preserves newest controls',()=>{
  const probe=new StopProbe();
  for(let i=0;i<20;i++)probe.observe(fixture([button({testid:'button-'+i})]),i);
  const trace=probe.snapshot();
  assert.equal(trace.controlChanges,20);
  assert.equal(trace.controlStates.length,12);
  assert.equal(trace.controlStates.at(-1).controls[0].testid,'button-19');
});
test('reset discards previous chat control history',()=>{
  const probe=new StopProbe();
  probe.observe(fixture([button({aria:'Stop'})]),5);
  probe.reset();
  assert.equal(probe.snapshot().controlStates.length,0);
  assert.equal(probe.snapshot().controlChanges,0);
});
