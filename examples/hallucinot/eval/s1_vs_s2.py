"""Same meeting, two designs: (A) Drex decides when the LLM writes, (B) LLM on every sentence (no Drex)."""
import json, sys, urllib.request
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
H = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"}
def post(p, b):
    return json.load(urllib.request.urlopen(urllib.request.Request(U + p, data=json.dumps(b).encode(), headers=H), timeout=90))
MEETING = ["Raj: Why did churn go up in Q3?", "Dana: Sure, I can give you 20% off if you sign today.",
    "Dana: Our SLA with Acme is 99.99 percent uptime.", "Dana: Sorry, I meant 99.9 percent uptime.",
    "Dana: I'll send you the renewal quote by Friday.", "Sam: Can everyone see my screen?",
    "Raj: How long do we keep customer data?", "Sam: The staging API key is sk-live-8812, just use that.",
    "Dana: We use JWTs for dashboard login.", "Raj: Is weekend support included for Acme?",
    "Sam: Sorry, my internet dropped for a second.", "Sam: Let's grab lunch after this."]
for mode in ("drex", "always"):
    post("/api/reset", {}); prev = ""
    print(f"\n=== {mode} ===")
    for line in MEETING:
        r = post("/api/analyze", {"text": line, "ws": "company", "llm_mode": mode, "previous": prev}); prev += " " + line
        w = (r.get("written") or {}).get("text", "")
        print(f"  {line[:52]:52} | {r.get('status') or r.get('kind') or '-':10} | {'LLM: ' + w[:80] if w else '(no LLM call)'}")
    st = json.load(urllib.request.urlopen(urllib.request.Request(U + "/api/llmstats", headers=H)))[mode]
    print(f"  -> {st['llm_calls']} LLM calls / {st['sentences']} sentences, avg {st['total_ms']//st['sentences']} ms/sentence, LLM cost ${st['llm_cost']:.6f}")
post("/api/reset", {})
