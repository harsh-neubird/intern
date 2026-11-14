// Relays page text from the background worker into the Hallucinot app (iframe on localhost:8787).
const app = document.getElementById("app");
const st = document.getElementById("st");

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "hallucinot-page") {
    st.textContent = "Checked: " + new URL(msg.url).hostname;
    app.contentWindow.postMessage({ type: "hallucinot-page", text: msg.text }, "http://localhost:8787");
  }
});

document.getElementById("now").addEventListener("click", () => {
  st.textContent = "Checking…";
  chrome.runtime.sendMessage({ type: "hallucinot-check-now" });
});

// check the current tab as soon as the panel opens
app.addEventListener("load", () => chrome.runtime.sendMessage({ type: "hallucinot-check-now" }));
