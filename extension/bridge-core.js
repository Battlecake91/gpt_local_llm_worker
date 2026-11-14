/* Shared, dependency-free lifecycle and delivery rules. Loaded before content.js. */
(function (root) {
  'use strict';
  const STATES = Object.freeze({ IDLE:'IDLE', GENERATING:'GENERATING', FINALIZING:'FINALIZING', COMPLETED:'COMPLETED', CANCELLED:'CANCELLED', ERROR:'ERROR' });
  const STOP = '[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="Stop"],button[aria-label="Generierung stoppen"]';
  const ASSISTANT = '[data-message-author-role="assistant"]';
  const USER = '[data-message-author-role="user"]';
  function conversation(url) {
    try { const u = new URL(url); if (u.hostname !== 'chatgpt.com') return null;
      const match = u.pathname.match(/^\/c\/([a-zA-Z0-9-]+)\/?$/);
      return match ? match[1] : null;
    } catch { return null; }
  }
  function readable(node) {
    if (!node) return '';
    const body = node.querySelector('.markdown, [class*="markdown"], [data-message-text]') || node;
    // innerText preserves rendered line breaks and fenced/preformatted code in Chromium.
    return (body.innerText ?? body.textContent ?? '').replace(/\r\n/g, '\n');
  }
  function lastAssistant(doc) { return [...doc.querySelectorAll(ASSISTANT)].at(-1) || null; }
  function lastTurnRole(doc) {
    const all = [...doc.querySelectorAll(`${ASSISTANT},${USER}`)];
    return all.at(-1)?.getAttribute('data-message-author-role') || null;
  }
  function messageIdentity(node, text, conv) {
    // No cryptographic claim: final SHA-256 id is generated asynchronously in content.js.
    const domId = node?.getAttribute('data-message-id') || node?.id || '';
    return `${conv}\u0000${domId}\u0000${text}`;
  }
  class Lifecycle {
    constructor({onCompleted, onState, stableMs=650, now=()=>Date.now(), schedule=(f,t)=>setTimeout(f,t), clear=(h)=>clearTimeout(h)}) {
      Object.assign(this,{onCompleted,onState,stableMs,now,schedule,clear});
      this.state=STATES.IDLE; this.session=null; this.timer=null; this.generation=0;
    }
    setState(state) { if(this.state!==state){this.state=state;this.onState?.(state);} }
    invalidate() { this.generation++; if(this.timer!==null)this.clear(this.timer); this.timer=null; this.session=null; this.setState(STATES.IDLE); }
    cancel() { if(!this.session)return; this.generation++; if(this.timer!==null)this.clear(this.timer); this.timer=null; this.session=null; this.setState(STATES.CANCELLED); }
    observe({stop, conv, node, text, role, cancelled=false}) {
      if(cancelled){this.cancel();return;}
      if(!conv) {this.invalidate();return;}
      if(this.session && this.session.conv!==conv){this.invalidate();}
      if(stop){
        if(!this.session){ this.session={conv, node, text, sawStop:true}; this.setState(STATES.GENERATING); }
        else { this.session.node=node || this.session.node; this.session.text=text; this.setState(STATES.GENERATING); }
        if(this.timer!==null){this.clear(this.timer);this.timer=null;this.generation++;}
        return;
      }
      if(!this.session || !this.session.sawStop || role!=='assistant')return;
      if(!node || !text.trim()){this.setState(STATES.ERROR);return;}
      this.session.node=node; this.session.text=text;
      this.setState(STATES.FINALIZING);
      if(this.timer!==null)this.clear(this.timer);
      const token=++this.generation;
      this.timer=this.schedule(()=>{
        if(token!==this.generation || !this.session || this.state!==STATES.FINALIZING)return;
        const s=this.session;this.session=null;this.timer=null;this.setState(STATES.COMPLETED);
        this.onCompleted?.({conv:s.conv,node:s.node,text:s.text});
      },this.stableMs);
    }
  }
  root.BridgeCore={STATES, STOP, ASSISTANT, USER, conversation, readable, lastAssistant, lastTurnRole, messageIdentity, Lifecycle};
  if(typeof module!=='undefined')module.exports=root.BridgeCore;
})(typeof globalThis!=='undefined'?globalThis:this);
