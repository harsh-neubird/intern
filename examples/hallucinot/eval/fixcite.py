import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as s
for ws,path in [("company","kb/company"),("classroom","kb/classroom")]:
    s.LOADING_WS[0]=ws; s.load_folder(os.path.join(s.ROOT,path))
s.LOADING_WS[0]="company"; s.load_pr_file(os.path.join(s.ROOT,"kb/github/flask_prs.jsonl"),"pallets/flask"); s.build_index()
poster="Mitochondria produce most of the cell's ATP.\nMitochondria are only found in plant cells.\nDNA is shaped like a triple helix.\nHumans have 48 chromosomes in each body cell.\nRibosomes build proteins."
bot="It includes single sign-on for all your users and a 99.99% uptime guarantee. Your data is retained for 13 months."
for ws,t in [("classroom",poster),("company",bot)]:
    r=s.check_document(t,ws); print(f"== {ws} {r['total_ms']} ms")
    for x in r["results"]:
        print(f" {x['status']:10} {x['sentence'][:50]:50} | fix: {(x.get('fix') or '-')[:70]} | cite: {x.get('cite','-')[:50]}")
for t in ["Our SLA with Acme is 99.99 percent uptime.","We switched redirects to 301."]:
    r=s.analyze(t,"speech","", "company"); print("live:",t[:40],"|",r.get("verdict"),"| fix:",(r.get("fix") or "-")[:70],"|",r.get("drex_ms"))
