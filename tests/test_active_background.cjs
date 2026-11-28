const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../extension-active/background.js"),"utf8");

function setup({serverExtensionId="a".repeat(32)}={}) {
  const listeners={},store={local:{bridgeToken:"x".repeat(64)},session:{}};
  const tabs=[
    {id:11,windowId:1,active:true,title:"Andere Seite",url:"https://example.org/"},
    {id:22,windowId:2,active:false,title:"ZFS Diagnose",url:"https://chatgpt.com/c/chat-222"},
    {id:33,windowId:3,active:false,title:"GitHub Workflow",url:"https://chatgpt.com/c/chat-333"},
    {id:44,windowId:4,active:true,title:"Nicht unterstützte ChatGPT-Startseite",url:"https://chatgpt.com/"}
  ];
  const chrome={
    runtime:{
      id:"a".repeat(32),
      getURL:p=>"chrome-extension://"+"a".repeat(32)+"/"+p,
      onMessage:{addListener:f=>listeners.message=f},
      onStartup:{addListener:f=>listeners.startup=f}
    },
    storage:{
      local:{
        setAccessLevel:async()=>{},
        get:async k=>({[k]:store.local[k]}),
        set:async obj=>Object.assign(store.local,obj)
      },
      session:{
        setAccessLevel:async()=>{},
        get:async k=>({[k]:store.session[k]}),
        set:async obj=>Object.assign(store.session,obj)
      }
    },
    tabs:{
      query:async()=>tabs,
      get:async id=>tabs.find(t=>t.id===id)||null,
      sendMessage:async()=>null,
      onRemoved:{addListener:f=>listeners.removed=f},
      onUpdated:{addListener:f=>listeners.updated=f}
    },
    alarms:{
      create:()=>{},
      onAlarm:{addListener:f=>listeners.alarm=f}
    }
  };
  const requests=[];
  const fetch=async(uri,options)=>{
    requests.push({uri,options});
    return {ok:true,json:async()=>({ok:true,extension_id:serverExtensionId})};
  };
  vm.runInNewContext(source,{chrome,fetch,URL,AbortSignal,
    setTimeout,console});
  const invoke=(msg,sender={url:chrome.runtime.getURL("popup.html")})=>
    new Promise(resolve=>listeners.message(msg,sender,result=>resolve(result)));
  return {tabs,store,requests,invoke,listeners,chrome};
}

test("popup enumerates open chats across all windows without active-tab assumptions",async()=>{
  const h=setup();
  const result=await h.invoke({type:"ACTIVE_GET"});
  assert.equal(result.ok,true);
  assert.equal(result.connected,true);
  assert.deepEqual(Array.from(result.tabs,t=>t.tab_id),[22,33]);
  assert.equal(result.tabs[0].title,"ZFS Diagnose");
});
test("explicit tab selection can enable and deactivate nonfocused chat",async()=>{
  const h=setup();
  let result=await h.invoke({type:"ACTIVE_TOGGLE",tab_id:33,conversation_id:"chat-333"});
  assert.equal(result.active,true);
  assert.equal(h.store.session.activeTabs[33],"chat-333");
  const listing=await h.invoke({type:"ACTIVE_GET"});
  assert.equal(listing.tabs[1].enabled,true);
  result=await h.invoke({type:"ACTIVE_TOGGLE",tab_id:33,conversation_id:"chat-333"});
  assert.equal(result.active,false);
  assert.equal(h.store.session.activeTabs[33],undefined);
});
test("cannot activate changed chat, arbitrary webpage or other tab's conversation",async()=>{
  const h=setup();
  for(const [tab_id,conversation_id] of [[33,"chat-222"],[11,"chat-222"],[999,"chat-333"]]){
    const result=await h.invoke({type:"ACTIVE_TOGGLE",tab_id,conversation_id});
    assert.equal(result.ok,false);
    assert.equal(result.error.includes("tab_closed_or_changed"),true);
  }
  assert.equal(Object.keys(h.store.session.activeTabs||{}).length,0);
});
test("content scripts cannot enumerate browser tabs or toggle monitoring",async()=>{
  const h=setup();
  for(const type of ["ACTIVE_GET","ACTIVE_TOGGLE"]){
    const result=await h.invoke({type},{tab:{id:33,url:"https://chatgpt.com/c/chat-333"}});
    assert.equal(result.ok,false);
    assert.equal(result.error,"popup_only");
  }
});

test("health pairing rejects worker configured for another extension", async()=>{
  const h=setup({serverExtensionId:"b".repeat(32)});
  const result=await h.invoke({type:"ACTIVE_GET"});
  assert.equal(result.ok,true);
  assert.equal(result.connected,false);
  assert.equal(result.connectionError,"worker_extension_id_mismatch");
  const rejected=await h.invoke({
    type:"ACTIVE_TOGGLE",tab_id:22,conversation_id:"chat-222"
  });
  assert.equal(rejected.ok,false);
  assert.equal(rejected.error,"worker_extension_id_mismatch");
});

