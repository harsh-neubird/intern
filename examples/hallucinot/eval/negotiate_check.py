import json, sys, urllib.request
U = sys.argv[1]
H = {"ngrok-skip-browser-warning": "1", "Content-Type": "application/json"}
def post(p, body):
    return json.load(urllib.request.urlopen(urllib.request.Request(U + p, data=json.dumps(body).encode(), headers=H), timeout=60))
post("/api/reset", {})
for line in ["Dana: We're giving Acme a 25 percent credit this month since their uptime dropped below 99 percent.",
             "Dana: Sure, I can give you 20% off if you sign today.",
             "Dana: Our SLA with Acme is 99.99 percent uptime.",
             "Sam: Let's grab lunch after this."]:
    r = post("/api/analyze", {"text": line, "ws": "company"})
    print(line[6:60], "->", r.get("status") or "-", [(h["name"], (h.get("detail") or "")[:70]) for h in r.get("agents", [])], r.get("total_ms"), "ms")
post("/api/reset", {})
