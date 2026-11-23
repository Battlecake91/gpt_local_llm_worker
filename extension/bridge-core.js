/* Shared, dependency-free lifecycle and delivery rules. Loaded before content.js. */
(function (root) {
  'use strict';
  const STATES = Object.freeze({ IDLE:'IDLE', GENERATING:'GENERATING', FINALIZING:'FINALIZING', COMPLETED:'COMPLETED', CANCELLED:'CANCELLED', ERROR:'ERROR' });
  const STOP = '[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="Stop streaming"],button[aria-label="Stop"],button[aria-label="Generierung stoppen"],button[aria-label="Stoppen"],button[aria-label="Antwortgenerierung stoppen"],button[aria-label="Antwort abbrechen"]';
  // Legacy and modern ChatGPT use different turn metadata. Do not select nested message
  // decorations: each modern content-search unit represents one message.
  const ASSISTANT = '[data-message-author-role="assistant"],[data-content-search-unit-key$=":assistant"]';
  const USER = '[data-message-author-role="user"],[data-content-search-unit-key$=":user"]';
  function activeStop(doc) {
    // A hidden duplicate stop control must not permanently block capture.
    // Never infer completion from a mere timeout: an observed, visible stop
    // lifecycle plus stable assistant answer are still mandatory.
    for (const button of doc.querySelectorAll(STOP)) {
      if (button.hidden || button.disabled ||
          button.getAttribute?.('aria-hidden')==='true' ||
          button.getAttribute?.('aria-disabled')==='true' ||
          button.closest?.('[hidden],[inert],[aria-hidden="true"]')) continue;
      if (typeof button.getClientRects==='function' &&
          button.getClientRects().length===0) continue;
      const view=doc.defaultView;
      if (typeof view?.getComputedStyle==='function') {
        const css=view.getComputedStyle(button);
        if (css.display==='none' || css.visibility==='hidden' ||
            css.visibility==='collapse') continue;
      }
      return button;
    }
    return null;
  }
  function roleOf(node) {
    if (!node) return null;
    const legacy=node.getAttribute('data-message-author-role');
    if (legacy==='assistant' || legacy==='user') return legacy;
    const key=node.getAttribute('data-content-search-unit-key')||'';
    if (key.endsWith(':assistant')) return 'assistant';
    if (key.endsWith(':user')) return 'user';
    return null;
  }
  function conversation(url) {
    try { const u = new URL(url); if (u.hostname !== 'chatgpt.com') return null;
      const match = u.pathname.match(/^(?:\/c|\/g\/g-p-[a-zA-Z0-9-]+\/c)\/([a-zA-Z0-9-]+)\/?$/);
      return match ? match[1] : null;
    } catch { return null; }
  }
  function readable(node) {
    if (!node) return '';
    const structured = root.BridgeExtractor?.extract(node);
    if (structured) return structured;
    const body = node.querySelector('[data-markdown-text-style="assistant-message"],.markdown,[data-message-text]') || node;
    // innerText preserves rendered line breaks and fenced/preformatted code in Chromium.
    return (body.innerText ?? body.textContent ?? '').replace(/\r\n/g, '\n');
  }
  function lastAssistant(doc) { return [...doc.querySelectorAll(ASSISTANT)].at(-1) || null; }
  function lastTurnRole(doc) {
    const all = [...doc.querySelectorAll(`${ASSISTANT},${USER}`)];
    return roleOf(all.at(-1));
  }
  function messageIdentity(node, text, conv) {
    // No cryptographic claim: final SHA-256 id is generated asynchronously in content.js.
    const domId = node?.getAttribute('data-message-id') || node?.getAttribute('data-content-search-unit-key') || node?.id || '';
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
      const changed = this.state !== STATES.FINALIZING || this.session.text !== text || this.session.node !== node;
      if (!changed) return; // Unrelated DOM mutations must not postpone completion forever.
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
  root.BridgeCore={STATES, STOP, activeStop, ASSISTANT, USER, roleOf, conversation, readable, lastAssistant, lastTurnRole, messageIdentity, Lifecycle};
  if(typeof module!=='undefined')module.exports=root.BridgeCore;
})(typeof globalThis!=='undefined'?globalThis:this);
