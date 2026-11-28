const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");

const source=fs.readFileSync(path.join(__dirname,"../extension-active/bridge.js"),"utf8");

function build({generating=false,conversation="abc-123"}={}) {
  const user={
    getAttribute:k=>k==="data-content-search-unit-key"?"turn-1:user":null,
    querySelector:()=>({innerText:"Prüfe mein NAS",textContent:"Prüfe mein NAS"}),
    innerText:"Prüfe mein NAS"
  };
  const assistant={
    getAttribute:k=>k==="data-content-search-unit-key"?"turn-2:assistant":null,
    querySelector:()=>null,
    innerText:"Rendered"
  };
  const stop={
    disabled:false,hidden:false,closest:()=>null,
    getClientRects:()=>[{}]
  };
  const listeners=[];
  const sent=[];
  const intervals=[];
  const document={
    documentElement:{},title:"Test: ChatGPT",
    querySelectorAll:selector=>{
      if(selector.includes("stop-button"))return generating?[stop]:[];
      if(selector.includes("data-content-search-unit-key") && selector.includes("assistant"))
        return [user,assistant];
      return [];
    }
  };
  const chrome={runtime:{
    onMessage:{addListener:fn=>listeners.push(fn)},
    sendMessage:async msg=>{sent.push(msg);return {ok:true};}
  }};
  const ctx={
    document,location:{href:"https://chatgpt.com/c/"+conversation},chrome,
    BridgeExtractor:{extract:()=>"```bash\nzpool status\n```"},
    MutationObserver:class{observe(){}},
    getComputedStyle:()=>({visibility:"visible"}),
    setTimeout:()=>0,setInterval:fn=>intervals.push(fn),
    window:{addEventListener(){}},URL
  };
  ctx.globalThis=ctx;
  vm.runInNewContext(source,ctx);
  function getSnapshot(){
    let value;
    listeners[0]({type:"ACTIVE_REQUEST_SNAPSHOT"},{},response=>value=response.snapshot);
    return value;
  }
  return {getSnapshot,sent,intervals,ctx};
}

test("opt-in bridge snapshot includes nearest visible user and assistant messages",()=>{
  const h=build();
  let current=h.getSnapshot();
  assert.equal(current.conversation_id,"abc-123");
  assert.equal(current.messages.length,2);
  assert.equal(current.messages[0].role,"user");
  assert.equal(current.messages[0].text,"Prüfe mein NAS");
  assert.equal(current.messages[1].role,"assistant");
  assert.equal(current.messages[1].text,"```bash\nzpool status\n```");
  assert.equal(current.messages[1].complete,false);
  h.getSnapshot();current=h.getSnapshot();
  assert.equal(current.messages[1].complete,true);
});

test("a visible stop control prevents completed status",()=>{
  const h=build({generating:true});
  for(let i=0;i<5;i++){
    const result=h.getSnapshot();
    assert.equal(result.generating,true);
    assert.equal(result.messages[1].complete,false);
  }
});

test("background tab can answer explicit snapshot request without sending a chat message",()=>{
  const h=build();
  assert.equal(h.intervals.length,1);
  const snap=h.getSnapshot();
  assert.equal(snap.messages.length,2);
  assert.equal(h.sent.length,0);
});

test("unsupported or unbound URLs return no snapshot",()=>{
  const h=build();
  h.ctx.location.href="https://chatgpt.com/";
  assert.equal(h.getSnapshot(),null);
});
