import json, sys, urllib.request
U = sys.argv[1]
H = {"ngrok-skip-browser-warning": "1", "Content-Type": "application/json"}
def get(p):
    return json.load(urllib.request.urlopen(urllib.request.Request(U + p, headers=H), timeout=30))
def post(p, body):
    return json.load(urllib.request.urlopen(urllib.request.Request(U + p, data=json.dumps(body).encode(), headers=H), timeout=60))
page = urllib.request.urlopen(urllib.request.Request(U + "/", headers=H), timeout=30)
print("page:", page.status, "| has agents panel:", b"addagent" in page.read())
print("agents:", len(get("/api/agents")["agents"]))
for line in ["Dana: Sure, I can give you 20% off if you sign today.", "Dana: Our SLA with Acme is 99.99 percent uptime.",
             "Dana: I'll send you the renewal quote by Friday.", "Sam: Let's grab lunch after this."]:
    r = post("/api/analyze", {"text": line, "ws": "company"})
    print("live:", line[:45], "->", r.get("status") or "-", [h["name"] for h in r.get("agents", [])], r.get("total_ms"), "ms")
r = post("/api/check", {"text": "DNA is shaped like a triple helix. Ribosomes build proteins.", "ws": "classroom"})
print("doc check:", dict(r["counts"]), r["total_ms"], "ms")
r = post("/api/analyze", {"text": "Inbox\nPer our contract you guarantee 99.99% uptime and we expect the 25% credit.", "mode": "page", "ws": "company"})
print("extension/page mode:", r.get("verdict"), r.get("total_ms"), "ms")
post("/api/reset", {}); print("reset ok")
