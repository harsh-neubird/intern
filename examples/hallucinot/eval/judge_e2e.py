"""Full judging run: upload -> Drex review -> import -> live demos (auto team switch) -> score -> board data."""
import json, sys, time, urllib.request
U = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
H = {"ngrok-skip-browser-warning": "1"}
def req(p, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(U + p, data=data, headers={**H, "Content-Type": ctype})
    return json.load(urllib.request.urlopen(r, timeout=300))
ok = lambda c, msg: print(("  PASS " if c else "  FAIL ") + msg)
csv = ("Team name,Project name,Brief explanation,Repository / code link\n"
       "Team Butterfly,HTTPX,\"A fully featured async HTTP client for Python 3 with HTTP/2 support.\",https://github.com/encode/httpx\n"
       "\"NOTE: late submissions below\",,,\n"
       "Team Quokka,RefundBot,\"Support copilot: Drex decides if a refund is allowed. Refunds are only available within 30 days of purchase. Annual plans cannot be cancelled mid-term.\",\n")
print("1) Upload + Drex review")
t = time.time(); r = req("/api/judge/ingest?preview=1&name=subs.csv", raw=csv.encode(), ctype="text/csv")
rows = r["rows"]; flags = {x["team"]: x["is_team"] for x in rows}
ok(len(rows) == 3, f"3 rows found ({r['how']}, {time.time()-t:.1f}s)")
ok(flags.get("Team Butterfly", 0) >= 0.5 and flags.get("Team Quokka", 0) >= 0.5, "real teams accepted by Drex")
ok(min(v for k, v in flags.items() if k.startswith("NOTE")) < 0.5, "junk NOTE row flagged by Drex")
print("2) Import reviewed rows")
r = req("/api/judge/import_rows", {"rows": [x for x in rows if x["is_team"] >= 0.5]})
ok(len(r["imported"]) == 2 and not r["errors"], f"imported {[x['team'] for x in r['imported']]}")
print("3) Live demos (Drex detects who is presenting)")
script = [("Hi everyone, we are Team Butterfly and we built HTTPX.", "team:team-butterfly", None),
          ("HTTPX supports HTTP/2 and has an async API.", "team:team-butterfly", "agree"),
          ("HTTPX is written entirely in Rust.", "team:team-butterfly", "contradict"),
          ("Thanks! Next up is Team Quokka with RefundBot.", "team:team-quokka", None),
          ("Customers can get a refund within 90 days of purchase.", "team:team-quokka", "contradict"),
          ("Refunds are available within 30 days of purchase.", "team:team-quokka", "agree")]
for line, team, want in script:
    t = time.time(); x = req("/api/judge/analyze", {"text": line}); st = (x.get("check") or {}).get("status")
    good = x.get("team") == team and (want is None or st == want)
    ok(good, f"{line[:52]:52} -> {x.get('team')} {st or '-'} ({time.time()-t:.1f}s){'  [switched]' if x.get('switched') else ''}")
print("4) Drex scores every team")
s = req("/api/judge/score", {})
for i, tm in enumerate(s["ranking"]):
    print(f"     {i+1}. {tm['team']:15} {tm['total']:5}/100  " + " ".join(f"{c['label'].split()[0]}={'-' if c['score'] is None else round(c['score'],1)}" for c in tm["criteria"].values()))
ok(len(s["ranking"]) == 2, "both teams ranked")
print("5) Board / team pages data")
j = json.load(urllib.request.urlopen(urllib.request.Request(U + "/api/judge", headers=H), timeout=30))
ok(j["phase"] in ("results", "live", "between"), f"phase = {j['phase']}")
ok(sum(v["claims"] for v in j["scores"].values()) >= 4, f"claims recorded = {sum(v['claims'] for v in j['scores'].values())}")
for page in ["/", "/app", "/judge.html"]:
    code = urllib.request.urlopen(urllib.request.Request(U + page, headers=H), timeout=30).status
    ok(code == 200, f"page {page} -> {code}")
