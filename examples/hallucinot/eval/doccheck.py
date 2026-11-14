import sys,os,json
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as s
for ws,path in [("company","kb/company"),("classroom","kb/classroom")]:
    s.LOADING_WS[0]=ws; s.load_folder(os.path.join(s.ROOT,path))
s.LOADING_WS[0]="company"; s.load_pr_file(os.path.join(s.ROOT,"kb/github/flask_prs.jsonl"),"pallets/flask"); s.build_index()
poster="""THE CELL
By Jamie, Bio 101
• Mitochondria produce most of the cell's ATP.
• Mitochondria are only found in plant cells.
• DNA is shaped like a triple helix.
• Humans have 48 chromosomes in each body cell.
• Plant cells have a cell wall made of cellulose.
• Ribosomes build proteins.
• Cells are super cool!"""
bot="""Thanks for reaching out! The Growth plan is $48,000 per year. It includes single sign-on for all your users and a 99.99% uptime guarantee. If we miss the guarantee you get a 10% service credit. Your data is retained for 13 months. Let me know if you have other questions!"""
for ws,txt in [("classroom",poster),("company",bot)]:
    r=s.check_document(txt,ws); print(f"\n== {ws}: {dict(r['counts'])} | {r['drex_calls']} Drex calls | {r['total_ms']} ms")
    for x in r["results"]:
        icon={"agree":"🟢","contradict":"🔴","no_source":"🟡","not_claim":"·"}[x["status"]]
        print(f" {icon} {x['sentence'][:62]:62} {x.get('doc',{}).get('title','')[:45]}")
