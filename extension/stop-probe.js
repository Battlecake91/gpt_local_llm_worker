/* Metadata-only, mutation-driven probe for changing ChatGPT composer controls. */
(function (root) {
  'use strict';
  const MAX_STATES=12;
  const safe=value=>String(value||'').slice(0,72);
  function metadata(button){
    const svg=button.querySelector('svg');
    return {
      tag:safe(button.tagName).toLowerCase(),
      testid:safe(button.getAttribute('data-testid') || button.getAttribute('data-test-id')),
      aria:safe(button.getAttribute('aria-label')),
      title:safe(button.getAttribute('title')),
      state:safe(button.getAttribute('data-state')),
      disabled:button.disabled===true || button.getAttribute('aria-disabled')==='true',
      svgRects:svg?svg.querySelectorAll('rect').length:0,
      svgPaths:svg?svg.querySelectorAll('path').length:0
    };
  }
  function controls(document){
    const form=document.querySelector('form[data-chatgpt-composer]') ||
      document.querySelector('#prompt-textarea')?.closest('form');
    if(!form)return [];
    return [...form.querySelectorAll('button,[role="button"]')]
      .slice(0,16).map(metadata);
  }
  class StopProbe{
    constructor(){this.reset();}
    reset(){this.states=[];this.lastSignature='';this.changes=0;this.lastAnswerLength=0;}
    observe(document,answerLength=0){
      const list=controls(document);
      const signature=JSON.stringify(list);
      this.lastAnswerLength=answerLength;
      if(signature===this.lastSignature)return;
      this.lastSignature=signature;
      this.changes++;
      this.states.push({change:this.changes,answerLength,controls:list});
      if(this.states.length>MAX_STATES)this.states.shift();
    }
    snapshot(){
      return {controlChanges:this.changes,lastAnswerLength:this.lastAnswerLength,
        controlStates:this.states.map(item=>({...item,controls:item.controls.map(x=>({...x}))}))};
    }
  }
  root.BridgeStopProbe={StopProbe,metadata,controls};
  if(typeof module!=='undefined')module.exports=root.BridgeStopProbe;
})(typeof globalThis!=='undefined'?globalThis:this);
