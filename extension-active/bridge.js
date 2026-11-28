(() => {
  "use strict";
  const ASSISTANT = '[data-message-author-role="assistant"],[data-content-search-unit-key$=":assistant"]';
  const USER = '[data-message-author-role="user"],[data-content-search-unit-key$=":user"]';
  const STOP = '[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="Stop streaming"],button[aria-label="Stoppen"],button[aria-label="Antwort abbrechen"]';
  const MAX_MESSAGES = 500;
  const MAX_TEXT = 256000;
  let lastSignature = "";
  let lastContent = "";
  let stability = 0;
  let lastRoute = location.href;
  let pending = false;

  function conversation() {
    try {
      const url = new URL(location.href);
      const match = url.hostname === "chatgpt.com" &&
        url.pathname.match(/^(?:\/c|\/g\/g-p-[a-zA-Z0-9-]+\/c)\/([a-zA-Z0-9-]+)\/?$/);
      return match ? match[1] : null;
    } catch { return null; }
  }

  function role(node) {
    const legacy = node.getAttribute("data-message-author-role");
    if (legacy === "user" || legacy === "assistant") return legacy;
    const key = node.getAttribute("data-content-search-unit-key") || "";
    return key.endsWith(":assistant") ? "assistant" :
      key.endsWith(":user") ? "user" : null;
  }

  function stopVisible() {
    return [...document.querySelectorAll(STOP)].some(b =>
      !b.disabled && !b.hidden && !b.closest('[hidden],[inert],[aria-hidden="true"]') &&
      b.getClientRects().length > 0 &&
      getComputedStyle(b).visibility !== "hidden");
  }

  function snapshot() {
    const id = conversation();
    if (!id) return null;
    const turns = [...document.querySelectorAll(ASSISTANT + "," + USER)].slice(-MAX_MESSAGES);
    const messages = turns.map((node, i) => {
      const r = role(node);
      const bubble = r === "user" ?
        (node.querySelector('[data-user-message-bubble="true"]') || node) : node;
      const text = r === "assistant"
        ? globalThis.BridgeExtractor.extract(bubble)
        : (bubble.innerText ?? bubble.textContent ?? "").replace(/\r\n?/g, "\n");
      const sourceId = node.getAttribute("data-message-id") ||
        node.getAttribute("data-content-search-unit-key") ||
        node.getAttribute("data-chatgpt-search-unit-key") || "";
      return {role: r, message_id: (sourceId || r + ":" + i).slice(0,512),
        text: text.slice(0,MAX_TEXT), complete: r === "user"};
    }).filter(m => m.role && m.text.trim().length);
    const generating = stopVisible();
    // Two consecutive unchanged observations are necessary for the latest
    // assistant turn. Timer alone does NOT authorize actions; phase 1 is view-only.
    const finalAssistant = messages.at(-1)?.role === "assistant";
    const signature = finalAssistant ? messages.at(-1).message_id + "\0" + messages.at(-1).text : "";
    stability = !generating && finalAssistant && signature === lastContent
      ? Math.min(stability + 1, 10) : 0;
    lastContent = signature;
    if (finalAssistant && !generating && stability >= 2) messages.at(-1).complete = true;
    for (const m of messages.slice(0, -1)) if (m.role === "assistant") m.complete = true;
    return {conversation_id:id,title:document.title.slice(0,200),
      generating,messages};
  }

  async function sync() {
    if (location.href !== lastRoute) {
      lastRoute = location.href; lastSignature = ""; lastContent = ""; stability = 0;
    }
    const data = snapshot();
    if (!data) return;
    const signature = JSON.stringify(data);
    if (signature === lastSignature) {
      // Heartbeat required to prove the tab is STILL open.
      await chrome.runtime.sendMessage({type:"ACTIVE_CHAT_SNAPSHOT",snapshot:data}).catch(()=>{});
      return;
    }
    lastSignature = signature;
    await chrome.runtime.sendMessage({type:"ACTIVE_CHAT_SNAPSHOT",snapshot:data}).catch(()=>{
      lastSignature = "";
    });
  }

  function queueSync() {
    if (pending) return;
    pending = true;
    setTimeout(() => { pending = false; void sync(); }, 450);
  }
  new MutationObserver(queueSync).observe(document.documentElement, {
    subtree:true, childList:true, characterData:true,
    attributes:true, attributeFilter:["data-message-author-role","data-content-search-unit-key",
      "aria-label","data-testid","class","hidden","style"]
  });
  window.addEventListener("popstate",queueSync);
  window.addEventListener("hashchange",queueSync);
  // Periodic snapshot also works if the DOM mutates before the extension starts.
  setInterval(() => { void sync(); }, 3000);
  queueSync();
})();
