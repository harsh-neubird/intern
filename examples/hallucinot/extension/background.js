// Opens the side panel on toolbar click, and sends the active tab's text to it
// whenever you switch tabs or a page finishes loading.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

const lastSent = new Map(); // tabId -> text hash, so we don't re-check the same page

function grabText() {
  const sel = String(window.getSelection() || "").trim();
  if (sel.length > 30) return { title: document.title, text: sel, selection: true };
  const main = document.querySelector("main, article, [role=main]") || document.body;
  return { title: document.title, text: (main.innerText || "").replace(/\s+/g, " ").slice(0, 6000) };
}

async function checkTab(tabId, force = false) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab.url || !/^https?:/.test(tab.url) || tab.url.startsWith("http://localhost:8787")) return;
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: grabText });
    const page = res && res.result;
    if (!page || page.text.length < 40) return;
    const key = page.text.slice(0, 500);
    if (!force && lastSent.get(tabId) === key) return;
    lastSent.set(tabId, key);
    chrome.runtime.sendMessage({ type: "hallucinot-page", text: `${page.title}\n${page.text}`, url: tab.url }).catch(() => {});
  } catch (e) { /* tab closed or not scriptable */ }
}

chrome.tabs.onActivated.addListener(({ tabId }) => checkTab(tabId));
chrome.tabs.onUpdated.addListener((tabId, info, tab) => { if (info.status === "complete" && tab.active) checkTab(tabId); });
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "hallucinot-check-now") {
    chrome.tabs.query({ active: true, lastFocusedWindow: true }).then(([t]) => t && checkTab(t.id, true));
  }
});
