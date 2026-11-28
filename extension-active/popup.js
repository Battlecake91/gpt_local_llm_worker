const el=id=>document.getElementById(id);
async function send(msg) {
  const result=await chrome.runtime.sendMessage(msg);
  if (!result?.ok) throw Error(result?.error||"Fehler");
  return result;
}
async function refresh() {
  try {
    const s=await send({type:"ACTIVE_GET"});
    el("connection").textContent=s.connected?"Worker verbunden":"Worker nicht erreichbar / Token fehlt";
    el("toggle").disabled=!s.conversation_id||!s.connected;
    el("toggle").textContent=s.active?"Deaktivieren":"Aktivieren";
    el("detail").textContent=s.conversation_id
      ? "Chat "+s.conversation_id.slice(0,12)+"… | "+s.count+" aktiviert"
      : "Kein geöffneter ChatGPT-Chat in diesem Tab";
  } catch(e) {el("status").textContent=String(e);}
}
el("save").addEventListener("click",async()=>{
  try {
    await send({type:"ACTIVE_SET_TOKEN",token:el("token").value.trim()});
    el("token").value="";
    el("status").textContent="Token gespeichert";
    await refresh();
  } catch(e) {el("status").textContent=String(e);}
});
el("toggle").addEventListener("click",async()=>{
  try {
    const result=await send({type:"ACTIVE_TOGGLE"});
    el("status").textContent=result.active?"Überwachung aktiv":"Überwachung beendet";
    await refresh();
  } catch(e) {el("status").textContent=String(e);}
});
void refresh();
