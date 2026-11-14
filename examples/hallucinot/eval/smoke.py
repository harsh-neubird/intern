import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as s
s.load_folder(os.path.join(s.ROOT,"kb/company")); s.load_pr_file(os.path.join(s.ROOT,"kb/github/flask_prs.jsonl"),"pallets/flask"); s.build_index()
prev=""
for t in ["Why did churn go up in Q3?","Our SLA with Acme is 99.99 percent uptime.","Do we owe Acme a credit for October?",
          "Yeah we switched redirects to 301.","We use JWTs for dashboard login.","Can everyone see my screen?",
          "Let's grab lunch after this.","Did we move to a managed database after the outage?"]:
  r=s.analyze(t,"speech",prev); prev+=" "+t; d=r.get("doc",{})
  print(f"{t[:48]:48} kind={r.get('kind'):8} show={str(r['show']):5} verdict={str(r.get('verdict')):10} doc={d.get('title','-')[:50]:50} ms={r.get('drex_ms')}")
