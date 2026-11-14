import json, sys, urllib.request
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
H = {"Content-Type": "application/json"}
post = lambda p, b: json.load(urllib.request.urlopen(urllib.request.Request(U + p, data=json.dumps(b).encode(), headers=H), timeout=120))
r = post("/api/judge/teams", {"lines": "Team Requests, https://github.com/psf/requests\nTeam HTTPX, https://github.com/encode/httpx"})
print("imported:", [(t["name"], t["sections"]) for t in r["added"]], r["errors"])
r = post("/api/judge/register", {"name": "Team Quokka", "oneliner": "Hallucinot: live fact-checking of meetings with Drex agents; uses NDI to parse PDFs."})
print("registered:", r.get("team", r))
post("/api/judge/reset", {})
for line in ["Hi, we built HTTPX, a fully featured HTTP client for Python 3.",
             "It supports HTTP/2 and has an async API.",
             "HTTPX is written entirely in Rust.",
             "Thanks! Next up, Requests: HTTP for humans.",
             "Requests supports HTTP/2 out of the box.",
             "Requests is an elegant and simple HTTP library for Python."]:
    r = post("/api/judge/analyze", {"text": line})
    c = r.get("check") or {}
    print(f"{'🔀 ' if r.get('switched') else '   '}{(r.get('team') or '-'):16} {c.get('status','-'):10} | {line[:60]} | {(c.get('doc') or {}).get('title','')[:40]}")
