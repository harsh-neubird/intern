"""Populate judge mode with sample teams, a few live claims and Drex scores (for trying the board)."""
import json, csv, io, sys, urllib.request
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
H = {"Content-Type": "application/json"}
post = lambda p, b: json.load(urllib.request.urlopen(urllib.request.Request(U + p, data=json.dumps(b).encode(), headers=H), timeout=300))
sub = open("SUBMISSION.md").read()
expl = sub[sub.index("**What it does:**"):sub.index("**Honest limits:**")]
buf = io.StringIO(); w = csv.writer(buf)
w.writerow(["Team name", "Project name", "Track", "Brief explanation", "Presentation link", "Repository / code link"])
w.writerow(["Team Hallucinot", "Hallucinot", "Swarm Intelligence", expl, "", ""])
w.writerow(["Team Butterfly", "HTTPX", "Apex Predator", "HTTPX is a fully featured HTTP client for Python 3 with sync and async APIs and HTTP/2 support.", "", "https://github.com/encode/httpx"])
print("imported", [x["team"] for x in post("/api/judge/import", {"raw": buf.getvalue()})["imported"]])
for line in ["Hi, we are Team Butterfly and we built HTTPX.", "It supports HTTP/2 and has an async API.", "HTTPX is written entirely in Rust.",
             "Thanks! Next up is Team Hallucinot.", "Hallucinot checks every sentence of a meeting with a team of Drex agents.",
             "We use NDI to parse uploaded PDFs and images.", "Drex matched Claude Opus at 47 out of 50 while being about 500 times cheaper."]:
    r = post("/api/judge/analyze", {"text": line}); print(" ", (r.get("check") or {}).get("status", "-"), "|", line)
for t in post("/api/judge/score", {})["ranking"]:
    print(t["total"], t["team"])
