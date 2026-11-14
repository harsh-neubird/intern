import sys,os,json
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as s
for ws,path in [("company","kb/company"),("classroom","kb/classroom")]:
    s.LOADING_WS[0]=ws; s.load_folder(os.path.join(s.ROOT,path))
s.LOADING_WS[0]="company"; s.load_pr_file(os.path.join(s.ROOT,"kb/github/flask_prs.jsonl"),"pallets/flask"); s.build_index(); s.load_agents()
print("doc-rule agents:"); [print("  ⚖️", a["rule"][:90]) for a in s.AGENTS if a["source"]=="docs"]
s.AGENTS.append({"id":"customcomp","icon":"🚩","name":"Competitor mention","type":"flag","rule":"Does the speaker mention a competitor company by name?","source":"custom"})
script=["Raj: Why did churn go up in Q3?",
 "Dana: Sure, I can give you 20% off if you sign today.",
 "Dana: Our SLA with Acme is 99.99 percent uptime.",
 "Dana: Sorry, I meant 99.9 percent uptime.",
 "Dana: I'll send you the renewal quote by Friday.",
 "Dana: We're giving Acme a 25 percent credit this month since their uptime dropped below 99 percent.",
 "Sam: The staging API key is sk-live-8812, just use that.",
 "Raj: Honestly Datadog gave us a better price.",
 "Dana: We decided last week to move the SLA to 99.95 percent for all enterprise customers.",
 "Raj: So the SLA is 99.9 percent, right?",
 "Sam: Let's grab lunch after this."]
prev=""
for line in script:
    r=s.analyze_live(line,prev,"company"); prev+=" "+line
    hits=", ".join(f"{h['icon']}{h['name']}" for h in r["agents"])
    print(f"\n> {line}\n  kind={r.get('kind')} status={r.get('status','-')} doc={(r.get('doc') or {}).get('title','')[:40]} older={(r.get('older') or {}).get('title','')[:30]}\n  agents=[{hits}] corrected={r.get('corrected')} fix={(r.get('fix') or '')[:60]} ms={r['total_ms']}")
print("\nACTIONS",s.ACTIONS,"\nLEARNED",s.LEARNED)
