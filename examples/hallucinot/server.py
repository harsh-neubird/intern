"""Hallucinot: live knowledge cards + fact-checking, decided by Drex.

Run:  python3 server.py [--folder PATH ...] [--repo owner/name ...] [--port 8787]
Open: http://localhost:8787
"""
import argparse, collections, concurrent.futures, json, math, os, re, shutil, subprocess, sys, time, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
DREX_URL = "https://console.nace.ai/v1/systemone"
TEXT_EXT = {".md", ".txt", ".csv", ".json", ".rst", ".py", ".js", ".ts", ".go", ".yaml", ".yml", ".html"}

# ---------------------------------------------------------------- knowledge base
CHUNKS = []  # {id, source, title, text, url, date, kind, ws}
LOADING_WS = ["company"]  # workspace that new chunks belong to


def add_chunk(source, title, text, url="", date="", kind="doc"):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 20:
        return
    CHUNKS.append({"id": f"c{len(CHUNKS)}", "source": source, "title": title.strip()[:120],
                   "text": text[:1200], "url": url, "date": date, "kind": kind, "ws": LOADING_WS[0]})


NACE = "https://console.nace.ai"


def ndi_parse(data, name):
    """NDI (Nace Document Intelligence, 'Perception'): upload a file, parse it to markdown (OCR when needed).
    Handles PDF, images, Word, PowerPoint, Excel, email. Same key and balance as Drex."""
    import uuid
    key = os.environ.get("NACE_API_KEY") or open(os.path.join(ROOT, ".nace_key")).read().strip()
    auth = {"Authorization": "Bearer " + key}
    def jpost(url, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={**auth, "Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=120))
    t = time.time()
    g = jpost(NACE + "/v1/documents/upload-grants", {"path": name, "ttl_seconds": 600})
    bnd = uuid.uuid4().hex
    body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n{json.dumps({'path': name})}\r\n"
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{bnd}--\r\n".encode()
    up = urllib.request.Request(g["upload_url"], data=body, method="POST",
                                headers={"X-Upload-Token": g["token"], "Content-Type": f"multipart/form-data; boundary={bnd}"})
    fid = json.load(urllib.request.urlopen(up, timeout=120))["result"]["file"]["file_id"]
    j = jpost(NACE + "/v1/documents/parse?wait_seconds=90",
              {"source": {"type": "workspace_file", "workspace_id": g["workspace_id"], "file_id": fid},
               "output": {"formats": ["markdown"]}})
    if j.get("status") != "succeeded":
        raise RuntimeError(f"NDI parse {j.get('status')}: {str(j.get('error'))[:200]}")
    doc = j["result"]["document"]
    md = doc.get("markdown") or doc.get("text") or ""
    if not md and doc.get("content_url"):
        md = urllib.request.urlopen(doc["content_url"], timeout=60).read().decode(errors="ignore")
    md = re.sub(r"^-{3}\s*Page \d+\s*-{3}\s*$", "", md, flags=re.M).strip()
    return {"text": md, "pages": doc.get("page_count"), "ocr": j["result"].get("ocr_applied"),
            "cost_usd": (j.get("cost") or {}).get("total_usd"), "ms": round((time.time() - t) * 1000)}


def parse_pdf(path):
    """PDF/scans/office files -> text via NDI; falls back to pdftotext."""
    try:
        return ndi_parse(open(path, "rb").read(), os.path.basename(path))["text"]
    except Exception as e:
        print(f"  NDI parse failed for {path}: {e}")
    if shutil.which("pdftotext"):
        return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    return ""


def add_document(text, name, ws):
    """Add a parsed document to a workspace's knowledge base, then re-derive policy agents from its rules."""
    n0 = len(CHUNKS)
    LOADING_WS[0] = ws
    title = (re.search(r"^#\s+(.+)$", text, re.M) or [None, name])[1]
    parts = re.split(r"\n(?=#{2,3}\s)", text)
    if len(parts) == 1:
        paras, buf, parts = re.split(r"\n\s*\n", text), "", []
        for p in paras:
            if len(buf) + len(p) > 800 and buf:
                parts.append(buf); buf = ""
            buf += "\n" + p
        if buf: parts.append(buf)
    for p in parts:
        h = re.match(r"#{1,3}\s+(.+)", p.strip())
        body = re.sub(r"^#{1,3}\s+.+\n?", "", p.strip())
        add_chunk(name, f"{title} — {h.group(1)}" if h and h.group(1) != title else title, body, kind="file")
    LOADING_WS[0] = "company"
    return len(CHUNKS) - n0


def load_folder(folder):
    n0 = len(CHUNKS)
    for dirpath, _, files in os.walk(folder):
        for f in sorted(files):
            path = os.path.join(dirpath, f)
            ext = os.path.splitext(f)[1].lower()
            rel = os.path.relpath(path, folder)
            if ext == ".pdf":
                text = parse_pdf(path)
            elif ext in TEXT_EXT:
                text = open(path, errors="ignore").read()
            else:
                continue
            if not text.strip():
                continue
            doc_title = (re.search(r"^#\s+(.+)$", text, re.M) or [None, rel])[1]
            # split markdown by headings, else by blank-line paragraphs ~800 chars
            parts = re.split(r"\n(?=#{2,3}\s)", text)
            if len(parts) == 1:
                paras, buf, parts = re.split(r"\n\s*\n", text), "", []
                for p in paras:
                    if len(buf) + len(p) > 800 and buf:
                        parts.append(buf); buf = ""
                    buf += "\n" + p
                if buf: parts.append(buf)
            for p in parts:
                h = re.match(r"#{1,3}\s+(.+)", p.strip())
                section = h.group(1) if h else ""
                body = re.sub(r"^#{1,3}\s+.+\n?", "", p.strip())
                title = f"{doc_title} — {section}" if section and section != doc_title else doc_title
                add_chunk(rel, title, body, url="file://" + path, kind="file")
    print(f"  folder {folder}: {len(CHUNKS)-n0} chunks")


def load_repo(repo, limit=300):
    cache = os.path.join(ROOT, "kb", "github", repo.replace("/", "__") + ".jsonl")
    if not os.path.exists(cache):
        print(f"  fetching merged PRs for {repo} via gh ...")
        out = subprocess.run(["gh", "api", "-X", "GET", f"repos/{repo}/pulls", "-f", "state=closed",
                              "-f", "per_page=100", "--paginate", "--jq",
                              '.[] | select(.merged_at!=null) | {n:.number,t:.title,b:((.body//"")[:600]),m:.merged_at[:10],u:.user.login}'],
                             capture_output=True, text=True)
        lines = out.stdout.strip().splitlines()[:limit]
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        open(cache, "w").write("\n".join(lines) + "\n")
    load_pr_file(cache, repo)


def load_pr_file(path, repo):
    n0 = len(CHUNKS)
    for line in open(path):
        if not line.strip():
            continue
        p = json.loads(line)
        if p["t"].lower().startswith(("bump", "[pre-commit", "merge branch", "release", "build(deps")):
            continue
        add_chunk(f"{repo} PR #{p['n']}", f"PR #{p['n']}: {p['t']}", f"{p['t']}. {p['b']}",
                  url=f"https://github.com/{repo}/pull/{p['n']}", date=p.get("m", ""), kind="pr")
    print(f"  repo {repo}: {len(CHUNKS)-n0} PRs")


# ---------------------------------------------------------------- search (BM25)
STOP = set("the and for this that with now did was still does are can why what someone anyone instead hey our "
           "we thing like right didnt where when there any yet get you your have has had they them their its "
           "it's from but not about into just been will would could should how who which then than also".split())
STOP |= set("yeah yes okay ok um uh so well actually really guys everyone".split())


def _stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf) and not w.endswith("ss"):
            return w[: -len(suf)]
    return w


tok = lambda s: [_stem(w.strip(".")) for w in re.findall(r"[a-z0-9_.%$]+", s.lower())
                 if len(w.strip(".")) > 1 and w.strip(".") not in STOP]
INDEXES = {}  # ws -> index


def build_index():
    for ws in sorted({c["ws"] for c in CHUNKS}):
        chunks = [c for c in CHUNKS if c["ws"] == ws]
        docs = [tok(c["title"] + " " + c["title"] + " " + c["text"]) for c in chunks]
        df = collections.Counter(w for d in docs for w in set(d))
        INDEXES[ws] = dict(chunks=chunks, docs=[collections.Counter(d) for d in docs], lens=[len(d) for d in docs],
                           df=df, N=len(docs), avg=sum(map(len, docs)) / max(1, len(docs)))


def search(q, k=12, ws="company"):
    I = INDEXES.get(ws) or next(iter(INDEXES.values())); qs = set(tok(q)); scored = []
    for i, c in enumerate(I["docs"]):
        s = 0.0
        for w in qs:
            if w in c:
                idf = math.log(1 + (I["N"] - I["df"][w] + .5) / (I["df"][w] + .5))
                s += idf * c[w] * 2.2 / (c[w] + 1.2 * (.25 + .75 * I["lens"][i] / I["avg"]))
        if s > 0:
            scored.append((s, i))
    return [I["chunks"][i] for s, i in sorted(scored, reverse=True)[:k]]


# ---------------------------------------------------------------- Drex
KEY = os.environ.get("NACE_API_KEY") or (open(os.path.join(ROOT, ".nace_key")).read().strip() if os.path.exists(os.path.join(ROOT, ".nace_key")) else "")


def drex(state, questions):
    body = json.dumps({"model": "drex-latest", "state": state, "questions": questions}).encode()
    req = urllib.request.Request(DREX_URL, data=body, headers={"Authorization": "Bearer " + KEY,
                                                               "Content-Type": "application/json"})
    t = time.time()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        if e.code == 403 and "Security Checkpoint" in body:
            raise RuntimeError("Nace's Drex API is temporarily unreachable (Vercel security checkpoint on console.nace.ai)")
        raise RuntimeError(f"Drex API error {e.code}: {body[:160]}")
    r["_ms"] = round((time.time() - t) * 1000)
    return r


def cand_label(c):
    d = f" ({c['date']})" if c["date"] else ""
    return f"{c['title']}{d}: {c['text'][:220]}"


VERDICT = {"type": "choice",
           "instructions": "Compare the statement with the source. Does the source support it, contradict it, or not say? If any part of the statement conflicts with the source, answer contradict.",
           "criteria": {"agree": "The source supports the statement",
                        "contradict": "The source says something different from the statement",
                        "unclear": "The source does not say either way"}}


def analyze(text, mode="speech", previous="", ws="company"):
    t0 = time.time()
    text = text.strip()
    if not text:
        return {"show": False}
    query = text if mode == "speech" else text[:4000]
    cands = search(query + " " + previous[-200:] if mode == "speech" else query, ws=ws)
    if not cands:
        return {"show": False, "reason": "no candidates", "total_ms": round((time.time() - t0) * 1000)}
    crit = {c["id"]: cand_label(c) for c in cands}
    crit["none"] = "None of these documents is about it"
    if mode == "speech":
        state = {"earlier_in_conversation": previous[-400:], "speaker_just_said": text}
        qs = {"kind": {"type": "choice",
                       "instructions": "What did the speaker just do?",
                       "criteria": {"question": "Asked a question about the company, customers, numbers, code or past decisions",
                                    "claim": "Stated a fact about the company, customers, numbers, code or past decisions",
                                    "other": "Small talk, logistics, opinions, or anything else"}},
              "doc": {"type": "choice", "instructions": "Which document covers the same topic as what the speaker just said, even if the document disagrees with the speaker? Pick none only if no document is on that topic.",
                      "criteria": crit}}
    else:
        state = {"page_the_user_is_reading": text[:6000]}
        qs = {"useful": {"type": "noul", "instructions": "Would one of the company's internal documents help the user with this page right now?"},
              "doc": {"type": "choice", "instructions": "Which document is most relevant to this page? Pick none if none of them is.",
                      "criteria": crit}}
    r1 = drex(state, qs)
    a = r1["answers"]
    doc_id, doc_conf = a["doc"]["choice"], a["doc"].get("confidence", 0)
    kind = a["kind"]["choice"] if mode == "speech" else ("page" if a["useful"]["noul"] > 0.5 else "other")
    out = {"mode": mode, "text": text[:300], "kind": kind,
           "kind_conf": round(a["kind"].get("confidence", 0), 2) if mode == "speech" else round(a["useful"]["noul"], 2),
           "doc_conf": round(doc_conf, 2), "drex_ms": [r1["_ms"]], "drex_eval_ms": [r1.get("evaluation_time_ms")],
           "candidates": len(cands)}
    show = kind != "other" and doc_id != "none" and doc_conf >= 0.4
    out["show"] = show
    if not show:
        out["total_ms"] = round((time.time() - t0) * 1000)
        return out
    doc = next(c for c in cands if c["id"] == doc_id)
    out["doc"] = doc
    out["verdict"] = None
    if kind in ("claim", "page"):
        statement = text if mode == "speech" else text[:3000]
        r2 = drex({"statement": statement, "source": f"{doc['title']}: {doc['text']}"}, {"v": VERDICT})
        v = r2["answers"]["v"]
        out["verdict"], out["verdict_conf"] = v["choice"], round(v.get("confidence", 0), 2)
        out["drex_ms"].append(r2["_ms"]); out["drex_eval_ms"].append(r2.get("evaluation_time_ms"))
        if v["choice"] == "contradict" and mode == "speech":
            out["fix"], ms = pick_fix(text, doc); out["drex_ms"] += ms
        out["cite"] = citation(doc)
        if mode == "page" and v["choice"] != "contradict":
            out["verdict"] = None  # on pages, only speak up for contradictions; otherwise just show context
    out["total_ms"] = round((time.time() - t0) * 1000)
    return out


def source_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", re.sub(r"#+\s*", "", text)) if len(s.strip()) > 15][:15]


def pick_fix(statement, doc):
    """For a wrong statement, let Drex pick the source sentence that states the correct fact (no text is generated)."""
    if doc.get("kind") == "pr":  # a PR's title is its cleanest statement of fact
        return re.sub(r"^PR #\d+:\s*", "", doc["title"]) + f" (PR #{doc['source'].split('#')[-1]})", []
    sents = source_sentences(doc["text"])
    if not sents:
        return None, []
    crit = {f"s{i}": s[:300] for i, s in enumerate(sents)}
    r = drex({"wrong_statement": statement, "source": doc["text"][:1500]},
             {"fix": {"type": "choice", "criteria": crit,
                      "instructions": "Which sentence from the source gives the correct information about the same thing the wrong statement got wrong?"}})
    a = r["answers"]["fix"]
    return sents[int(a["choice"][1:])], [r["_ms"]]


def citation(doc):
    title = re.sub(r"\s*\((fictional demo data|demo course notes)\)", "", doc["title"])
    return title + (f" ({doc['date']})" if doc.get("date") else "")


def split_claims(text):
    """Break a document into checkable sentences (handles bullets, poster lines, prose)."""
    text = text.replace("•", "\n").replace("•", "\n")
    parts = []
    for line in re.split(r"\n+", text):
        line = line.strip(" -*\t")
        parts += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", line) if s.strip()]
    seen, out = set(), []
    for s in parts:
        if len(s) >= 12 and len(s.split()) >= 3 and s.lower() not in seen:
            seen.add(s.lower()); out.append(s[:400])
    return out[:40]


def check_sentence(sentence, ws):
    t0 = time.time()
    cands = search(sentence, ws=ws)
    if ws.startswith("team:") and ws in INDEXES:
        core = [c for c in INDEXES[ws]["chunks"] if any(k in (c["title"] + " " + c["source"]).lower()
                for k in ("submission", "summary", "description"))][:3]
        intro = [c for c in INDEXES[ws]["chunks"] if c["source"].lower().endswith("readme.md")][:2]
        seen = {c["id"] for c in cands}
        cands = cands[:10] + [c for c in core + intro if c["id"] not in seen]
    res = {"sentence": sentence, "status": "not_claim", "drex_ms": []}
    if not cands:
        res["status"] = "no_source"
        return res
    crit = {c["id"]: cand_label(c) for c in cands}
    crit["none"] = "None of these documents is about it"
    r1 = drex({"sentence": sentence},
              {"claim": {"type": "noul", "instructions": "Does this sentence state a checkable fact (a number, date, name, property or cause), rather than a title, opinion, greeting or instruction?"},
               "doc": {"type": "choice", "instructions": "Which document covers the same topic as the sentence, even if it disagrees with it? Pick none only if no document is on that topic.",
                       "criteria": crit}})
    a = r1["answers"]; res["drex_ms"].append(r1["_ms"])
    if a["claim"]["noul"] < 0.5:
        return res
    if a["doc"]["choice"] == "none" or a["doc"].get("confidence", 0) < 0.25:
        res["status"] = "no_source"
        return res
    # a sentence can make several claims that live in different docs: check the top 2 picks
    probs = a["doc"].get("probabilities") or {a["doc"]["choice"]: 1.0}
    picks = [k for k, p in sorted(probs.items(), key=lambda kv: -kv[1]) if k != "none" and p >= 0.1][:3] or [a["doc"]["choice"]]
    verdicts = []
    for pid in picks:
        doc = next(c for c in cands if c["id"] == pid)
        r2 = drex({"statement": sentence, "source": f"{doc['title']}: {doc['text']}"}, {"v": VERDICT})
        v = r2["answers"]["v"]; res["drex_ms"].append(r2["_ms"])
        verdicts.append((v["choice"], v.get("confidence", 0), doc))
    best = (next((x for x in verdicts if x[0] == "contradict"), None)
            or next((x for x in verdicts if x[0] == "agree"), None) or verdicts[0])
    res.update(status={"agree": "agree", "contradict": "contradict"}.get(best[0], "no_source"),
               conf=round(best[1], 2), doc=best[2], cite=citation(best[2]))
    if res["status"] == "contradict":
        res["fix"], ms = pick_fix(sentence, best[2]); res["drex_ms"] += ms
    res["ms"] = round((time.time() - t0) * 1000)
    return res


def check_document(text, ws="company"):
    t0 = time.time()
    sentences = split_claims(text)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda s: check_sentence(s, ws), sentences))
    counts = collections.Counter(r["status"] for r in results)
    return {"results": results, "counts": counts, "sentences": len(sentences),
            "drex_calls": sum(len(r["drex_ms"]) for r in results), "total_ms": round((time.time() - t0) * 1000)}


# ---------------------------------------------------------------- agents (multi-agent layer)
# Every agent is one plain-English question that Drex answers on each sentence.
# Sources: starter (built in), docs (rules found in your documents), custom (added by users).
import threading
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
CUSTOM_FILE = os.path.join(DATA, "custom_agents.json")
STARTER = [
    {"id": "fact", "icon": "📚", "name": "Fact checker", "type": "fact", "source": "starter",
     "rule": "Does what was said contradict our documents?"},
    {"id": "suggest", "icon": "💡", "name": "Suggest", "type": "suggest", "source": "starter",
     "rule": "Is someone asking something our documents answer? Show the answer."},
    {"id": "action", "icon": "📝", "name": "Action items", "type": "log", "source": "starter",
     "rule": "Is the speaker committing to do a specific task, such as sending, fixing, scheduling or following up on something?"},
    {"id": "leak", "icon": "🔒", "name": "Leak guard", "type": "flag", "source": "starter",
     "rule": "Is the speaker saying a password, API key, secret token, credit card number or someone's private personal data out loud?"},
    {"id": "memory", "icon": "🧠", "name": "Decision recorder", "type": "learn", "source": "starter",
     "rule": "Is the speaker announcing a new decision or a change to how things are, as settled fact (not asking, guessing, or proposing)?"},
]
AGENTS, LEARNED, ACTIONS, SESSION = [], [], [], []
AGENT_STATS = collections.defaultdict(lambda: {"fired": 0, "corrected": 0})
LAST_FLAG = {}
LOCK = threading.Lock()
RULE_RX = re.compile(r"\b(requires?|required|must|only|not included|cannot|can't|may not|never|mandatory|at most|limited to)\b", re.I)


def agent_name(rule):
    r = re.sub(r"^(does|did|is|are|has|have|will)\s+(the\s+)?(speaker|someone|anyone|customer|rep|agent|anybody)\s+", "", rule.strip(), flags=re.I)
    r = re.sub(r"^(does|is|are)\s+", "", r, flags=re.I).rstrip("?.")
    r = r[:1].upper() + r[1:]
    return short_name(r, 5)


def short_name(s, n=7):
    w = s.rstrip(".").split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def rules_from_docs():
    """Agents that create themselves: every rule-like sentence in your documents becomes a checker."""
    out, seen = [], set()
    for c in CHUNKS:
        if c["kind"] != "file":
            continue
        for s in source_sentences(c["text"]):
            if RULE_RX.search(s) and 25 < len(s) < 240 and s not in seen:
                seen.add(s)
                out.append({"id": f"rule{len(out)}", "icon": "⚖️", "name": short_name(s), "type": "rule",
                            "rule": s, "source": "docs", "doc": c["source"], "ws": c["ws"]})
    return out[:40]


def load_agents():
    custom = json.load(open(CUSTOM_FILE)) if os.path.exists(CUSTOM_FILE) else []
    AGENTS[:] = STARTER + rules_from_docs() + custom


def save_custom():
    json.dump([a for a in AGENTS if a["source"] == "custom"], open(CUSTOM_FILE, "w"), indent=1)


def pick_rules(text, ws, k=5):
    """Router step 1: cheap keyword pre-selection of which doc-rule agents could apply."""
    qs = set(tok(text))
    scored = []
    for a in AGENTS:
        if a["type"] == "rule" and a.get("ws", ws) == ws:
            overlap = len(qs & set(tok(a["rule"])))
            if overlap:
                scored.append((overlap, a))
    return [a for _, a in sorted(scored, key=lambda x: -x[0])[:k]]


def verify(sentence, cands, doc_answer):
    """Fact agent: check the statement against the top picked sources (docs and things learned in meetings)."""
    probs = doc_answer.get("probabilities") or {doc_answer["choice"]: 1.0}
    picks = [k for k, p in sorted(probs.items(), key=lambda kv: -kv[1]) if k != "none" and p >= 0.15][:2]
    learned = [c for c in cands if c["kind"] == "learned"]
    if learned and learned[0]["id"] not in picks:
        picks.append(learned[0]["id"])  # always weigh what was decided recently
    ms, verdicts = [], []
    def one(pid):
        doc = next(c for c in cands if c["id"] == pid)
        r = drex({"statement": sentence, "source": f"{doc['title']}: {doc['text']}"}, {"v": VERDICT})
        return r["answers"]["v"]["choice"], r["answers"]["v"].get("confidence", 0), doc, r["_ms"]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        for v, conf, doc, m in ex.map(one, picks):
            ms.append(m); verdicts.append((v, conf, doc))
    newest = [x for x in verdicts if x[2]["kind"] == "learned" and x[0] != "unclear"]
    official = [x for x in verdicts if x[2]["kind"] != "learned" and x[0] != "unclear"]
    if newest and official and newest[0][0] != official[0][0]:
        # meeting decision and official doc disagree: the newer meeting decision wins, doc may be outdated
        status = "outdated" if newest[0][0] == "contradict" else "agree_new"
        return status, newest[0][1], newest[0][2], official[0][2], ms
    best = (next((x for x in verdicts if x[0] == "contradict"), None)
            or next((x for x in verdicts if x[0] == "agree"), None) or (verdicts[0] if verdicts else None))
    if not best:
        return "unclear", 0, None, None, ms
    return best[0], best[1], best[2], None, ms


def negotiate(statement, rule_text, fact_doc):
    """Two agents disagree about the same statement: Policy guard flagged it by a rule's wording,
    while Fact checker independently found it matches the real source. A third Drex call arbitrates
    between the two agents' positions instead of just stacking both cards."""
    r = drex(
        {"statement": statement,
         "policy_guard_position": f"Flagged by matching the wording of this rule: \"{rule_text}\"",
         "fact_checker_position": f"Checked against the source \"{fact_doc['title']}\": \"{fact_doc['text'][:600]}\" — found the statement matches this source, not contradicting it."},
        {"call": {"type": "choice",
                  "instructions": "Our Policy guard and Fact checker disagree about this statement. Policy guard matched it against a rule's wording alone. Fact checker checked the actual source document and found it matches. Read the rule and the source carefully: are they really about the same kind of thing (so the rule's concern still stands on its own), or does the source describe a different, already-authorized mechanism that the rule wasn't written for, making the policy flag a false alarm from keyword matching? Decide the final call.",
                  "criteria": {
                      "stand_down": "The source shows this is a different, already-authorized mechanism than what the rule is about — the policy flag is a false alarm; withdraw it",
                      "uphold": "The rule is about this exact same thing and still applies on its own even though the source doesn't contradict the statement — keep the policy flag",
                      "both": "Both concerns are legitimate on their own terms and should stay visible"}}})
    a = r["answers"]["call"]
    return a["choice"], round(a.get("confidence", 0), 2), r["_ms"]


LLM_NAME = "DeepInfra · Llama 3.3 70B"
LLM_STATS = {}


def llm_stats(mode):
    return LLM_STATS.setdefault(mode, {"sentences": 0, "llm_calls": 0, "llm_ms": 0, "llm_cost": 0.0, "total_ms": 0})


def llm(prompt, max_tokens=120):
    """System 2: DeepInfra-hosted LLM. Returns (text, ms, cost_usd)."""
    key = secret(".deepinfra_key", "DEEPINFRA_API_KEY")
    if not key:
        raise RuntimeError("No DeepInfra key")
    t = time.time()
    req = urllib.request.Request("https://api.deepinfra.com/v1/openai/chat/completions",
                                 data=json.dumps({"model": os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
                                                  "max_tokens": max_tokens, "temperature": 0.1,
                                                  "messages": [{"role": "user", "content": prompt}]}).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=40))
    return d["choices"][0]["message"]["content"].strip(), round((time.time() - t) * 1000), float((d.get("usage") or {}).get("estimated_cost") or 0)


def write_line(text, out):
    """System 2 writes one grounded sentence. Drex already picked the source and the verdict."""
    doc = out.get("doc")
    src = f"{doc['title']}: {doc['text'][:900]}" if doc else "(no source document)"
    task = {"context": "Answer the speaker's question in one short sentence, using only the source.",
            "contradict": "The speaker said something wrong. Rewrite what they said as one short, correct sentence, using only the source.",
            "outdated": "This changed earlier in the meeting. In one short sentence, say what is true now, using only the source.",
            "learned_update": "Summarize this new decision in one short sentence.",
            }.get(out.get("status"), "If the source helps, write one short helpful sentence using only the source. Otherwise reply NONE.")
    return llm(f"{task}\nSpeaker said (speech-to-text, may contain misheard words): \"{text}\"\nSource: {src}\n"
               "Use only names and terms that appear in the source; never repeat a name from the speaker that the source does not contain. "
               "Reply with the sentence only, no preamble.")


def llm_only(text, cands):
    """Baseline: no Drex. The LLM looks at every sentence and decides and writes on its own."""
    docs = "\n".join(f"[{i+1}] {cand_label(c)}" for i, c in enumerate(cands[:6])) or "(none)"
    return llm("You are a live meeting assistant. Read what the speaker just said and the company documents below. "
               "If a document answers, corrects or adds something important about it, reply with ONE short helpful sentence "
               "(an answer or a correction). If nothing is worth saying (small talk, irrelevant), reply exactly NONE.\n\n"
               f"Speaker said: \"{text}\"\n\nDocuments:\n{docs}")


NUMW = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
        "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
        "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
        "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90"}


def normalize_spoken(t):
    """General spoken-form cleanup so speech matches documents: 'quarter three' -> 'Q3', 'ninety nine point nine' -> '99.9'."""
    t = re.sub(r"\bquarter (one|two|three|four|1|2|3|4)\b", lambda m: "Q" + {"one": "1", "two": "2", "three": "3", "four": "4"}.get(m.group(1), m.group(1)), t, flags=re.I)
    def num(m):
        words = m.group(0).lower().split()
        out, i = "", 0
        while i < len(words):
            w = words[i]
            if w == "point":
                out += "."
            elif w in NUMW:
                v = NUMW[w]
                if v.endswith("0") and len(v) == 2 and i + 1 < len(words) and words[i + 1] in NUMW and len(NUMW[words[i + 1]]) == 1:
                    v = v[0] + NUMW[words[i + 1]]; i += 1
                out += v
            i += 1
        return out
    t = re.sub(r"\b(?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|point)\b\s*){2,}",
               lambda m: num(m) + " ", t, flags=re.I)
    t = re.sub(r"\b(" + "|".join(k for k in NUMW if k != "oh") + r")\s+percent\b", lambda m: NUMW[m.group(1).lower()] + "%", t, flags=re.I)
    t = re.sub(r"(\d)\s+percent\b", r"\1%", t)
    t = fix_glossary(t)
    t = re.sub(r"\b(?:[a-zA-Z]\.?\s){1,}[a-zA-Z]\b\.?", lambda m: re.sub(r"[\s.]", "", m.group(0)).upper() if len(re.sub(r"[\s.]", "", m.group(0))) >= 2 else m.group(0), t)  # "h t t p x" -> HTTPX
    return re.sub(r"\s{2,}", " ", t).strip()


# Event product names speech engines don't know. Corrected only in "the model" contexts, so ordinary words survive
# ("two tracks", "the Swarm track" are left alone).
SOUNDALIKE = r"(?:tracks?|t-?rex|treks?|dreks?|drecks?|drax|drakes?|rex)"
MODEL_BEFORE = r"(?:by|with|using|uses|use|used|from|of|called|via|run|runs|powered by|decided by)"
MODEL_AFTER = r"(?:decides?|decided|makes?|made|matched|matches|scores?|scored|picks?|picked|is|was|does|did|answers?|returns?|model|api|calls?|router|agents?|decision)"


def fix_glossary(t):
    t = re.sub(r"\b(" + MODEL_BEFORE + r")\s+(?:the\s+)?" + SOUNDALIKE + r"\b", lambda m: m.group(1) + " Drex", t, flags=re.I)
    t = re.sub(r"\b" + SOUNDALIKE + r"\s+(?=" + MODEL_AFTER + r"\b)", "Drex ", t, flags=re.I)
    t = re.sub(r"\bnice\s+(?:dot\s+)?a\.?\s?i\b", "Nace AI", t, flags=re.I)
    return t


EVENT_TERMS = ["Drex", "Nace", "NDI", "Intern", "DeepInfra", "Adobe", "Firefly", "Keenable", "Perception", "Drexathon"]
_DICT = None


def english(w):
    """Is this an ordinary English word (or a simple inflection of one)?"""
    global _DICT
    if _DICT is None:
        try:
            _DICT = set(x.strip().lower() for x in open("/usr/share/dict/words", errors="ignore"))
        except Exception:
            _DICT = set()
    w = w.lower()
    if w in _DICT:
        return True
    for suf in ("s", "es", "ed", "d", "ing", "er", "ers", "ly"):
        if w.endswith(suf) and w[: -len(suf)] in _DICT:
            return True
    return False


def vocab_for(ws):
    """Important words for a workspace, built automatically: names, product terms, jargon from its own materials."""
    I = INDEXES.get(ws)
    terms = set(EVENT_TERMS)
    for t in JUDGE["teams"]:
        terms.update(re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", t["name"] + " " + (t.get("oneliner") or "").split(":")[0]))
    if I:
        caps = collections.Counter()
        for c in I["chunks"][:500]:
            caps.update(re.findall(r"\b(?:[A-Z][a-z]*[A-Z0-9][A-Za-z0-9]*|[A-Z][a-z]{2,}|[A-Z]{2,6})\b", c["title"] + " " + c["text"]))
        terms.update(w for w, k in caps.items() if k >= 2 and not english(w))
    return sorted(terms)


def fix_terms(text, ws):
    """Snap misheard made-up words ("hallucinote") to the closest important term; real English words are left alone."""
    import difflib
    vocab = vocab_for(ws)
    low = {v.lower(): v for v in vocab}
    def fix(m):
        w = m.group(0)
        if len(w) < 4 or w.lower() in low or english(w):
            return w
        hit = difflib.get_close_matches(w.lower(), list(low), n=1, cutoff=0.8)
        return low[hit[0]] if hit else w
    return re.sub(r"[A-Za-z][A-Za-z0-9]+", fix, text)


def pick_transcript(alternatives, ws):
    """Speech engines mishear jargon. Pick the alternative that best matches this knowledge base's vocabulary."""
    I = INDEXES.get(ws)
    if not I or len(alternatives) < 2:
        return alternatives[0] if alternatives else ""
    def fit(a):
        toks = set(tok(a))
        known = [w for w in toks if w in I["df"]]
        return sum(math.log(1 + I["N"] / (1 + I["df"][w])) for w in known) - 0.5 * (len(toks) - len(known))
    return max(alternatives, key=fit)


def analyze_live(text, previous="", ws="company", llm_mode="drex", alternatives=None):
    """Multi-agent pass over one spoken sentence. Drex makes every call."""
    t0 = time.time()
    text = text.strip()
    m = re.match(r"^([A-Z][a-z]{1,15}):\s*(.+)$", text)
    speaker, text = (m.group(1), m.group(2)) if m else ("", text)
    heard = text
    if alternatives:
        text = pick_transcript([text] + [a for a in alternatives if a and a != text], ws)
    text = fix_terms(normalize_spoken(text), ws)
    out = {"mode": "speech", "text": text[:300], "speaker": speaker, "show": False, "agents": [], "drex_ms": []}
    if text.lower() != heard.lower():
        out["heard"] = heard[:300]
    if not text:
        return out
    cands = search(text + " " + previous[-200:], ws=ws)
    if llm_mode == "always":
        st = llm_stats("always")
        try:
            w, ms, cost = llm_only(text, cands)
        except Exception as e:
            out["written_error"] = str(e); return out
        st["sentences"] += 1; st["llm_calls"] += 1; st["llm_ms"] += ms; st["llm_cost"] += cost
        out.update(kind="llm", show=w.strip().upper() != "NONE",
                   written={"text": w, "ms": ms, "cost": cost, "by": LLM_NAME, "why": "LLM called on every sentence (no Drex)"})
        out["total_ms"] = round((time.time() - t0) * 1000); st["total_ms"] += out["total_ms"]
        return out
    customs = [a for a in AGENTS if a["source"] == "custom"]
    state = {"earlier_in_conversation": previous[-400:], "speaker_just_said": text}
    qs = {"kind": {"type": "choice", "instructions": "What did the speaker just do?", "criteria": {
              "question": "Asked a factual question about the subject being discussed (the business, a course topic, customers, numbers, code or past decisions)",
              "claim": "Stated something as a fact about the subject being discussed (the business, a course topic, customers, numbers, code or past decisions)",
              "promise": "Promised or offered something to someone: a discount, a date, a feature, a guarantee",
              "other": "Small talk, logistics, opinions, or anything else"}}}
    for a in STARTER:
        if a["type"] in ("log", "flag", "learn"):
            qs[a["id"]] = {"type": "noul", "instructions": a["rule"]}
    for a in customs:
        qs[a["id"]] = {"type": "noul", "instructions": a["rule"]}
    qs["draft_request"] = {"type": "noul", "instructions":
        "Is the speaker explicitly asking for something to be written, drafted, summarized or explained in words?"}
    if cands:
        crit = {c["id"]: cand_label(c) for c in cands}
        crit["none"] = "None of these documents is about it"
        qs["doc"] = {"type": "choice", "criteria": crit, "instructions":
                     "Which document covers the same topic as what the speaker just said, even if it disagrees? Pick none only if no document is on that topic."}
    lf = LAST_FLAG.get(ws)
    if lf and time.time() - lf["t"] < 120:
        state["previously_flagged_statement"] = lf["text"]
        state["what_the_source_says"] = lf["source"]
        qs["corrected"] = {"type": "noul", "instructions": "Is the speaker now correcting the previously flagged statement so it matches what the source says?"}
    r1 = drex(state, qs)  # router + light agents, one Drex request
    a = r1["answers"]; out["drex_ms"].append(r1["_ms"])
    kind = a["kind"]["choice"]; out["kind"] = kind
    p = lambda k: a.get(k, {}).get("noul", 0)

    if "corrected" in a and p("corrected") > 0.6:
        with LOCK:
            AGENT_STATS[lf["agent"]]["corrected"] += 1
        out["corrected"] = {"agent": lf["agent"], "count": AGENT_STATS[lf["agent"]]["corrected"]}
        LAST_FLAG.pop(ws, None)

    decision = p("memory") > 0.6 and kind != "question"
    # parallel phase: fact agent + doc-rule agents
    jobs = {}
    ex = concurrent.futures.ThreadPoolExecutor(3)
    doc_ok = "doc" in a and a["doc"]["choice"] != "none" and a["doc"].get("confidence", 0) >= 0.4
    has_learned = any(c["kind"] == "learned" for c in cands[:6])
    if doc_ok and (kind in ("claim", "promise") or (kind == "question" and has_learned)):
        jobs["fact"] = ex.submit(verify, text, cands, a["doc"])
    # router: Drex already classified the sentence; promises and claims go to every doc-rule agent in this workspace
    rules = [r for r in AGENTS if r["type"] == "rule" and r.get("ws", ws) == ws][:30] if kind in ("claim", "promise") else []
    if rules:
        rq = {r["id"]: {"type": "noul", "instructions": f"Company rule: \"{r['rule']}\" Does what the speaker said break this rule, for example by promising, offering or stating something the rule does not allow?"} for r in rules}
        jobs["rules"] = ex.submit(drex, {"speaker_just_said": text}, rq)
    res = {k: f.result() for k, f in jobs.items()}
    ex.shutdown()

    if "fact" in res and kind == "question" and res["fact"][0] not in ("outdated", "agree_new"):
        res.pop("fact")  # a plain question: just show the answer card below
    if "fact" in res and res["fact"][0] == "unclear":
        out["drex_ms"] += res.pop("fact")[4]  # nothing to say: the doc neither confirms nor contradicts
    if "fact" in res:
        status, conf, doc, older, ms = res["fact"]; out["drex_ms"] += ms
        if decision and status in ("contradict", "outdated"):
            status = "learned_update"  # an announced change, not a hallucination
        out.update(status=status, conf=round(conf, 2), doc=doc, older=older, cite=citation(doc) if doc else "")
        if status == "contradict":
            out["fix"], ms = pick_fix(text, doc); out["drex_ms"] += ms
        if status in ("contradict", "outdated") and doc:
            LAST_FLAG[ws] = {"text": text, "source": doc["text"][:600], "agent": "fact", "t": time.time()}
    elif doc_ok and kind == "question":
        doc = next(c for c in cands if c["id"] == a["doc"]["choice"])
        out.update(status="context", doc=doc, conf=round(a["doc"].get("confidence", 0), 2), cite=citation(doc))

    hits = []
    if "rules" in res:
        out["drex_ms"].append(res["rules"]["_ms"])
        for rid, ans in res["rules"]["answers"].items():
            if ans["noul"] > 0.6:
                r = next(x for x in AGENTS if x["id"] == rid)
                hits.append({"id": rid, "icon": "⚖️", "name": "Policy guard", "type": "flag", "prob": round(ans["noul"], 2),
                             "detail": r["rule"], "doc": r.get("doc", "")})
                LAST_FLAG[ws] = {"text": text, "source": r["rule"], "agent": rid, "t": time.time()}
        if hits and out.get("status") in ("agree", "agree_new") and out.get("doc"):
            # Policy guard and Fact checker disagree on the same statement: let Drex arbitrate.
            winner, conf, ms2 = negotiate(text, hits[0]["detail"], out["doc"])
            out["drex_ms"].append(ms2)
            if winner == "stand_down":
                hits.clear()
                note = f"Fact checker matched this against {citation(out['doc'])}, which covers this exact case — Drex sided with the Fact checker and stood the policy flag down."
            elif winner == "uphold":
                note = "The source doesn't contradict the statement, but the policy rule still applies on its own terms — Drex kept the policy flag."
            else:
                note = "Both agents have a legitimate point here — Drex kept both flags visible."
            hits.append({"id": "negotiate", "icon": "🤝", "name": "Agents negotiated", "type": "negotiate",
                         "prob": conf, "detail": note})
    if p("leak") > 0.6:
        hits.append({"id": "leak", "icon": "🔒", "name": "Leak guard", "type": "flag", "prob": round(p("leak"), 2),
                     "detail": "Sensitive information said out loud. Rotate or redact it."})
    if p("action") > 0.6:
        item = {"text": text, "who": speaker or "someone", "t": time.strftime("%H:%M")}
        with LOCK: ACTIONS.append(item)
        hits.append({"id": "action", "icon": "📝", "name": "Action items", "type": "log", "prob": round(p("action"), 2),
                     "detail": f"Added to action items ({item['who']})"})
    for c in customs:
        if p(c["id"]) > 0.6:
            hits.append({"id": c["id"], "icon": c.get("icon", "🚩"), "name": c["name"], "type": c["type"],
                         "prob": round(p(c["id"]), 2), "detail": c["rule"]})
    if decision:
        with LOCK:
            LOADING_WS[0] = ws
            add_chunk(f"Meeting · {time.strftime('%b %d %H:%M')}", f"Decided in meeting{' by ' + speaker if speaker else ''}",
                      text, date=time.strftime("%Y-%m-%d"), kind="learned")
            LOADING_WS[0] = "company"
            LEARNED.append({"text": text, "who": speaker or "someone", "t": time.strftime("%H:%M"),
                            "updates": (out.get("doc") or {}).get("title", "") if out.get("status") == "learned_update" else ""})
            build_index()
        hits.append({"id": "memory", "icon": "🧠", "name": "Decision recorder", "type": "learn", "prob": round(p("memory"), 2),
                     "detail": "Learned. Future statements will be checked against this."})
    with LOCK:
        for h in hits:
            AGENT_STATS[h["id"]]["fired"] += 1
        if out.get("status") in ("contradict", "outdated", "agree", "context", "agree_new"):
            AGENT_STATS["fact" if out["status"] != "context" else "suggest"]["fired"] += 1
    out["agents"] = hits
    st = llm_stats("drex")
    st["sentences"] += 1
    # Drex's own decisions decide whether System 2 is needed: a question it found a source for,
    # a statement it judged wrong or outdated, or an explicit request to write something.
    reason = ("Drex found the source for a question" if out.get("status") == "context" else
              "Drex judged the statement wrong" if out.get("status") == "contradict" else
              "Drex saw it changed today" if out.get("status") == "outdated" else
              "Drex heard a request to write something" if p("draft_request") > 0.6 else "")
    out["needs_writing"] = reason
    if reason:
        try:
            w, ms, cost = write_line(text, out)
            if w.strip().upper() != "NONE":
                out["written"] = {"text": w, "ms": ms, "cost": cost, "by": LLM_NAME,
                                  "why": reason}
            st["llm_calls"] += 1; st["llm_ms"] += ms; st["llm_cost"] += cost
        except Exception as e:
            out["written_error"] = str(e)
    with LOCK:
        SESSION.append({"t": time.strftime("%H:%M"), "speaker": speaker, "text": text, "status": out.get("status"),
                        "fix": out.get("fix"), "source": (out.get("doc") or {}).get("title"),
                        "older": (out.get("older") or {}).get("title"),
                        "hits": [{"name": h["name"], "type": h["type"], "detail": h.get("detail")} for h in hits]})
    out["show"] = bool(hits) or out.get("status") in ("contradict", "outdated", "agree", "agree_new", "context", "learned_update")
    out["total_ms"] = round((time.time() - t0) * 1000)
    st["total_ms"] += out["total_ms"]
    return out


def know_view():
    """What each workspace knows, grouped by source, for the 'What I know' box."""
    out = {}
    for ws, I in INDEXES.items():
        groups = collections.OrderedDict()
        for c in I["chunks"]:
            if c["kind"] == "pr":
                key, label, icon = "pr:" + c["source"].split(" PR #")[0], c["source"].split(" PR #")[0] + " pull requests", "🧑‍💻"
            elif c["kind"] == "learned":
                key, label, icon = "learned", "Learned in meetings", "🧠"
            else:
                key, icon = "file:" + c["source"], "📄"
                label = re.sub(r"\s*\((fictional demo data|demo course notes)\)", "", c["title"].split(" — ")[0])
            g = groups.setdefault(key, {"icon": icon, "label": label, "count": 0})
            g["count"] += 1
        out[ws] = list(groups.values())
    return out


def agents_view():
    return {"agents": [{**{k: v for k, v in x.items() if k in ("id", "icon", "name", "type", "rule", "source", "doc")},
                        **AGENT_STATS[x["id"]]} for x in AGENTS],
            "learned": LEARNED[::-1], "actions": ACTIONS[::-1]}


# ---------------------------------------------------------------- meeting recap + Intern handoff
DEEPINFRA_MODEL = os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")


def secret(name, env):
    v = os.environ.get(env)
    if v:
        return v.strip()
    f = os.path.join(ROOT, name)
    return open(f).read().strip() if os.path.exists(f) else ""


def recap_facts():
    who = lambda e: e["speaker"] or "Someone"
    corrections, policy, leaks, flags = [], [], [], []
    for e in SESSION:
        if e["status"] == "contradict":
            corrections.append(f"{who(e)} said \"{e['text']}\" but {e['source']} says: {e.get('fix') or 'something different'}")
        if e["status"] == "outdated":
            corrections.append(f"{who(e)} said \"{e['text']}\" but this changed in the meeting ({e['source']}); {e.get('older') or 'the doc'} may be outdated")
        for h in e["hits"]:
            if h["name"] == "Policy guard":
                policy.append(f"{who(e)}: \"{e['text']}\" (rule: {h['detail']})")
            elif h["name"] == "Leak guard":
                leaks.append(f"{who(e)} shared sensitive information: \"{e['text'][:80]}\". Rotate or redact it.")
            elif h["type"] == "flag" and h["name"] not in ("Policy guard",):
                flags.append(f"{h['name']}: {who(e)}: \"{e['text']}\"")
    return {"decisions": [f"{x['who']}: {x['text']}" for x in LEARNED],
            "action_items": [f"{x['who']}: {x['text']}" for x in ACTIONS],
            "corrections": corrections, "policy_flags": policy, "security": leaks, "other_flags": flags,
            "sentences_checked": len(SESSION)}


def template_recap(f):
    sec = [("✅ Decisions", f["decisions"]), ("📝 Action items", f["action_items"]), ("🦖 Corrections", f["corrections"]),
           ("⚖️ Policy flags", f["policy_flags"]), ("🔒 Security", f["security"]), ("🚩 Other flags", f["other_flags"])]
    lines = [f"*Meeting recap* ({f['sentences_checked']} statements checked by Hallucinot)"]
    for title, items in sec:
        if items:
            lines.append(f"\n*{title}*")
            lines += [f"• {i}" for i in items]
    return "\n".join(lines)


def write_recap():
    f = recap_facts()
    key = secret(".deepinfra_key", "DEEPINFRA_API_KEY")
    text, writer = None, "template"
    if key:
        prompt = ("Write a short Slack meeting recap from these facts. Use only these facts, invent nothing. "
                  "Sections (skip empty ones): Decisions, Action items (with owner), Corrections, Policy flags, Security. "
                  "Use Slack formatting (*bold*, • bullets). Under 180 words.\n\nFACTS:\n" + json.dumps(f, indent=1))
        try:
            req = urllib.request.Request("https://api.deepinfra.com/v1/openai/chat/completions",
                                         data=json.dumps({"model": DEEPINFRA_MODEL, "max_tokens": 500, "temperature": 0.2,
                                                          "messages": [{"role": "user", "content": prompt}]}).encode(),
                                         headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            text = json.load(urllib.request.urlopen(req, timeout=40))["choices"][0]["message"]["content"].strip()
            writer = f"DeepInfra · {DEEPINFRA_MODEL.split('/')[-1]}"
        except Exception as e:
            print("DeepInfra recap failed:", e)
    if not text:
        text = template_recap(f)
    intern = ""
    if f["action_items"]:
        intern = "@Intern please follow up on these action items from today's meeting:\n" + \
                 "\n".join(f"• {a}" for a in f["action_items"])
    return {"recap": text, "writer": writer, "intern_message": intern, "facts": f}


def post_slack(text):
    url = secret(".slack_webhook", "SLACK_WEBHOOK_URL")
    if not url:
        raise RuntimeError("No Slack webhook connected yet")
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=20).read()


# ---------------------------------------------------------------- judge mode
# Load each team's public GitHub repo as its own knowledge section, detect which team is presenting
# from what they say (a Drex decision), and check every claim against that team's own materials.
JUDGE = {"teams": [], "current": None, "scores": {}, "ranking": [], "phase": "setup", "last_live": 0}


def gh_get(path):
    """GitHub API via the gh CLI (authenticated, higher rate limit); falls back to anonymous HTTPS."""
    try:
        out = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return json.loads(out.stdout)
    except Exception:
        pass
    req = urllib.request.Request("https://api.github.com/" + path.lstrip("/"), headers={"User-Agent": "hallucinot"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def import_team(name, repo_url):
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise ValueError(f"not a GitHub repo link: {repo_url}")
    owner, repo = m.group(1), m.group(2)
    slug = "team:" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    info = gh_get(f"repos/{owner}/{repo}")
    import base64
    texts = []
    try:
        rd = gh_get(f"repos/{owner}/{repo}/readme")
        texts.append(("README.md", base64.b64decode(rd["content"]).decode(errors="ignore")))
    except Exception:
        pass
    try:  # a few extra top-level docs (pitch, submission, docs)
        for f in gh_get(f"repos/{owner}/{repo}/contents")[:60]:
            if f["type"] == "file" and f["name"].lower().endswith((".md", ".txt")) and f["name"].lower() != "readme.md" and len(texts) < 5:
                c = gh_get(f"repos/{owner}/{repo}/contents/{f['path']}")
                texts.append((f["name"], base64.b64decode(c["content"]).decode(errors="ignore")))
    except Exception:
        pass
    with LOCK:
        CHUNKS[:] = [c for c in CHUNKS if c["ws"] != slug]
        n = 0
        for fname, t in texts:
            n += add_document(t[:60000], f"{repo}/{fname}", slug)
        if info.get("description"):
            LOADING_WS[0] = slug; add_chunk(f"{repo} (GitHub)", f"{repo}: repo description", info["description"], kind="file"); LOADING_WS[0] = "company"
        build_index()
    first = re.sub(r"[#*`>\[\]]", "", next((t for _, t in texts), "")).strip()
    oneliner = (info.get("description") or " ".join(first.split()[:30]))[:200]
    team = {"name": name.strip(), "slug": slug, "repo": f"https://github.com/{owner}/{repo}", "oneliner": oneliner, "sections": n}
    JUDGE["teams"] = [t for t in JUDGE["teams"] if t["slug"] != slug] + [team]
    JUDGE["scores"].setdefault(slug, {"claims": 0, "agree": 0, "contradict": 0, "no_source": 0, "items": []})
    return team


def register_team(name, oneliner="", repo=""):
    """Self-registration: a team gives its name, a one-liner and optionally a GitHub repo; files can be added later."""
    name = name.strip()[:60]
    if not name:
        raise ValueError("Team name is required")
    if repo.strip():
        team = import_team(name, repo)
        if oneliner.strip():
            team["oneliner"] = oneliner.strip()[:200]
        return team
    slug = "team:" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    team = {"name": name, "slug": slug, "repo": "", "oneliner": oneliner.strip()[:200], "sections": 0}
    if oneliner.strip():
        with LOCK:
            LOADING_WS[0] = slug; add_chunk(name, f"{name}: project summary", oneliner, kind="file"); LOADING_WS[0] = "company"
            build_index()
    JUDGE["teams"] = [t for t in JUDGE["teams"] if t["slug"] != slug] + [team]
    JUDGE["scores"].setdefault(slug, {"claims": 0, "agree": 0, "contradict": 0, "no_source": 0, "items": []})
    return team


def ndi_parse_url(url, name):
    """NDI parses a public file link directly (no download on our side)."""
    key = os.environ.get("NACE_API_KEY") or open(os.path.join(ROOT, ".nace_key")).read().strip()
    req = urllib.request.Request(NACE + "/v1/documents/parse?wait_seconds=90", method="POST",
                                 data=json.dumps({"source": {"type": "url", "url": url, "file_name": name},
                                                  "output": {"formats": ["markdown"]}}).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    j = json.load(urllib.request.urlopen(req, timeout=120))
    if j.get("status") != "succeeded":
        raise RuntimeError(f"NDI {j.get('status')}")
    doc = j["result"]["document"]
    return re.sub(r"^-{3}\s*Page \d+\s*-{3}\s*$", "", doc.get("markdown") or doc.get("text") or "", flags=re.M)


def parse_submissions(raw):
    """Accept Nace's submissions export as CSV or JSON. Column names are matched loosely."""
    import csv, io
    raw = raw.strip()
    rows = []
    if raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        rows = data if isinstance(data, list) else data.get("submissions") or data.get("data") or [data]
    else:
        rows = list(csv.DictReader(io.StringIO(raw)))
    def pick(r, *keys):
        for k, v in r.items():
            kk = re.sub(r"[^a-z]", "", str(k).lower())
            if any(x in kk for x in keys) and v:
                return str(v).strip()
        return ""
    out = []
    for r in rows:
        r = {str(k): v for k, v in r.items()}
        out.append({"team": pick(r, "teamname", "team"), "project": pick(r, "projectname", "project", "title"),
                    "explanation": pick(r, "explanation", "description", "brief", "summary"),
                    "repo": pick(r, "repo", "code", "github"), "slides": pick(r, "presentation", "slides", "deck"),
                    "demo": pick(r, "demo")})
    return [x for x in out if x["team"] or x["project"]]


def table_to_rows(md):
    """Markdown tables (from NDI parsing Excel/PDF/Word) -> list of dicts."""
    lines = [l.strip() for l in md.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return []
    cells = lambda l: [c.strip() for c in l.strip("|").split("|")]
    head = cells(lines[0])
    rows = []
    for l in lines[1:]:
        if re.match(r"^\|?\s*:?-{2,}", l):
            continue
        c = cells(l)
        if len(c) >= 2:
            rows.append(dict(zip(head, c)))
    return rows


def llm_extract_teams(text):
    """System 2 fallback: pull team records out of any messy text."""
    out, _, _ = llm("Extract every hackathon team or submission from the text below. Reply with ONLY a JSON list of objects "
                    "with keys: team, project, explanation, repo, slides, demo (empty string if unknown). No commentary.\n\n"
                    + text[:12000], max_tokens=3000)
    m = re.search(r"\[.*\]", out, re.S)
    return json.loads(m.group(0)) if m else []


def ingest_any(data, name):
    """Whatever Nace gives us (CSV, JSON, Excel, PDF, Word, image, text) -> list of submissions + how we read it."""
    low = name.lower()
    text, how = None, ""
    if low.endswith((".csv", ".json", ".txt", ".tsv", ".md")):
        text, how = data.decode("utf-8", errors="ignore"), "read directly"
        try:
            subs = parse_submissions(text.replace("\t", ",") if low.endswith(".tsv") else text)
            if subs:
                return subs, how
        except Exception:
            pass
    if text is None:
        text, how = ndi_parse(data, name)["text"], "read by NDI"
    rows = table_to_rows(text)
    if rows:
        subs = parse_submissions(json.dumps(rows))
        if subs:
            return subs, how + " (table)"
    subs = [x for x in (llm_extract_teams(text) or []) if isinstance(x, dict)]
    subs = parse_submissions(json.dumps(subs)) if subs else []
    return subs, how + " + teams extracted by DeepInfra LLM"


def review_submission(sub):
    """Drex sanity-checks one extracted record before anything is imported."""
    r = drex({"record": sub},
             {"is_team": {"type": "noul", "instructions": "This row comes from a list of hackathon submissions, where each normal row names a team and/or the project it built. Is this row such a team entry, rather than a note, a comment, a section header, a total or an empty row?"},
              "explains": {"type": "noul", "instructions": "Does the explanation describe what the project actually does?"}})
    a = r["answers"]
    missing = [k for k in ("team", "project", "explanation") if not sub.get(k)]
    if sub.get("repo") and "github.com" not in sub["repo"]:
        missing.append("repo (not a GitHub link)")
    return {**sub, "is_team": round(a["is_team"]["noul"], 2),
            "explains": round(a["explains"]["noul"], 2) if sub.get("explanation") else None, "missing": missing}


def import_submission(sub):
    name = sub["team"] or sub["project"]
    clean = re.sub(r"[*_`#>]+", "", sub["explanation"])
    clean = re.sub(r"^\s*[-•]\s*", "", re.sub(r"(What it does|How we used Nace):?\s*", "", clean), flags=re.M)
    one = (sub["project"] + ": " if sub["project"] else "") + " ".join(clean.split()[:28])
    repo = sub["repo"] if "github.com" in sub["repo"] else ""
    team = register_team(name, one, repo)
    notes = []
    if sub["explanation"]:
        with LOCK:
            add_document(sub["explanation"], f"{name} submission", team["slug"]); build_index()
        team["sections"] = team.get("sections", 0) + 1
    link = sub["slides"]
    if link.startswith("http"):
        fname = re.sub(r"[?#].*$", "", link.rstrip("/").split("/")[-1]) or "slides.pdf"
        if not re.search(r"\.(pdf|pptx?|docx?|png|jpe?g)$", fname, re.I):
            fname += ".pdf"
        try:
            text = ndi_parse_url(link, fname)
            with LOCK:
                team["sections"] = team.get("sections", 0) + add_document(text, f"{name} slides", team["slug"]); build_index()
            notes.append("slides parsed by NDI")
        except Exception as e:
            notes.append(f"slides not readable ({str(e)[:60]}); upload the PDF instead")
    return {"team": team["name"], "sections": team.get("sections", 0), "notes": notes}


# Official criteria from the Drexathon rules; every team is scored the same way.
RUBRIC = [
    ("track", "Track fit", "How well does the project fit its hackathon track (Apex Predator: Drex beats a frontier LLM with measured results; Swarm Intelligence: multi-agent with Drex making every agent's calls; Wildcard: most creative use of Drex)?"),
    ("drex", "Drex usage", "How central and deep is the use of Drex (the Nace decision model) in what the project does?"),
    ("intern", "Intern usage", "How much does the project use Intern, Nace's AI agent in Slack?"),
    ("ndi", "NDI usage", "How much does the project use NDI (Nace Document Intelligence / Perception) to parse documents?"),
    ("partners", "Partner tools", "How much does the project use partner tools: Adobe (Express, Firefly, Photoshop), DeepInfra or Keenable?"),
    ("evidence", "Measured evidence", "How strong is the evidence: measured results, benchmarks, numbers or a working demo?"),
    ("credibility", "Credibility on stage", "How well were the team's live claims backed by their own materials?"),
]
LEVELS = ["none", "weak", "moderate", "strong", "excellent"]


def team_evidence(slug, k=10):
    I = INDEXES.get(slug)
    if not I:
        return ""
    chunks = sorted(I["chunks"], key=lambda c: (0 if "submission" in c["source"] else 1 if "slides" in c["source"] else 2))
    return "\n".join(f"- {c['title']}: {c['text'][:350]}" for c in chunks[:k])


def score_team(t):
    sc = JUDGE["scores"].get(t["slug"], {})
    live = (f"Live claims checked: {sc.get('claims', 0)}; backed by their materials: {sc.get('agree', 0)}; "
            f"contradicted their materials: {sc.get('contradict', 0)}; not found in their materials: {sc.get('no_source', 0)}.")
    state = {"team": t["name"], "project_summary": t.get("oneliner", ""), "public_repo": t.get("repo") or "none given",
             "materials": team_evidence(t["slug"]), "live_demo": live}
    qs = {key: {"type": "score", "criteria": LEVELS, "instructions": f"{q} Judge only from the evidence given; if there is no evidence, answer none."}
          for key, _, q in RUBRIC}
    r = drex(state, qs)
    out = {}
    for key, label, _ in RUBRIC:
        a = r["answers"][key]
        val = a.get("score")
        if isinstance(val, str):
            val = LEVELS.index(val) if val in LEVELS else 0
        out[key] = {"label": label, "score": round(float(val or 0), 2), "confidence": round(a.get("confidence", 0), 2)}
    if not sc.get("claims"):
        out["credibility"]["score"] = None  # no live demo heard yet: don't count it
    vals = [v["score"] for v in out.values() if v["score"] is not None]
    total = round(100 * sum(vals) / (4 * len(vals)), 1) if vals else 0
    return {"team": t["name"], "slug": t["slug"], "total": total, "criteria": out, "ms": r["_ms"]}


def rank_teams():
    JUDGE["phase"] = "scoring"
    try:
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            results = list(ex.map(score_team, JUDGE["teams"]))
    finally:
        JUDGE["phase"] = "results"
    results.sort(key=lambda x: -x["total"])
    JUDGE["ranking"] = results
    return results


def judge_analyze(text, override=None):
    t0 = time.time()
    text = normalize_spoken(re.sub(r"^[A-Z][a-z]{1,15}:\s*", "", text.strip()))
    text = fix_terms(text, JUDGE["current"] or "")
    teams = JUDGE["teams"]
    if not teams:
        raise RuntimeError("Import the teams first")
    out = {"text": text, "switched": False}
    if override:
        if override != JUDGE["current"]:
            out["switched"] = True
        JUDGE["current"] = override
    else:
        low = text.lower()
        def names(t):
            n = [t["name"], re.sub(r"^team\s+", "", t["name"], flags=re.I)]
            proj = (t.get("oneliner") or "").split(":")[0]
            if 2 < len(proj) < 40:
                n.append(proj)
            return [x.lower() for x in n if len(x) > 3]
        import difflib
        words = re.findall(r"[a-z0-9]+", low)
        def mentioned(x):  # exact phrase, or a close match for invented names speech engines mangle ("hallucinote")
            if re.search(r"\b" + re.escape(x) + r"\b", low):
                return True
            xs = x.split()
            for i in range(len(words) - len(xs) + 1):
                cand = " ".join(words[i:i + len(xs)])
                if len(cand) > 4 and difflib.SequenceMatcher(None, cand, x).ratio() >= 0.82:
                    return True
            return False
        named = [t["slug"] for t in teams if any(mentioned(x) for x in names(t))]
        if not named and len(teams) == 1 and not JUDGE["current"]:
            named = [teams[0]["slug"]]  # only one team loaded: it is the one presenting
        if len(named) == 1 and named[0] != JUDGE["current"]:
            JUDGE["current"] = named[0]; out["switched"] = True; out["team_guess"], out["team_conf"] = named[0], 1.0
    if not override and not out["switched"]:
        crit = {t["slug"]: f"{t['name']}: {t['oneliner']}" for t in teams}
        crit["unclear"] = "Cannot tell which project this is about, or it is general talk"
        r = drex({"presenter_just_said": text, "current_team": JUDGE["current"] or "none yet"},
                 {"team": {"type": "choice", "criteria": crit, "instructions":
                           "A hackathon team is presenting its project on stage. Which team's project is this sentence about? "
                           "Use the project names, features and descriptions. Pick unclear if it could be any of them."}})
        a = r["answers"]["team"]
        out["team_guess"], out["team_conf"] = a["choice"], round(a.get("confidence", 0), 2)
        if a["choice"] != "unclear" and a.get("confidence", 0) >= 0.6 and a["choice"] != JUDGE["current"]:
            JUDGE["current"] = a["choice"]; out["switched"] = True
    cur = JUDGE["current"]
    out["team"] = cur
    JUDGE["phase"], JUDGE["last_live"] = "live", time.time()
    if not cur:
        out["total_ms"] = round((time.time() - t0) * 1000)
        return out
    res = check_sentence(text, cur)
    out["check"] = res
    sc = JUDGE["scores"].setdefault(cur, {"claims": 0, "agree": 0, "contradict": 0, "no_source": 0, "items": []})
    if res["status"] in ("agree", "contradict", "no_source"):
        sc["claims"] += 1; sc[res["status"]] += 1
        sc["items"].append({"text": text, "status": res["status"], "source": (res.get("doc") or {}).get("title"), "t": time.strftime("%H:%M")})
    out["total_ms"] = round((time.time() - t0) * 1000)
    return out


# ---------------------------------------------------------------- game: "Catch the facts", judged by Drex
import random as _random


def _mutate_number(sent):
    """Make a plausible wrong version of a fact by changing one number."""
    nums = list(re.finditer(r"\d+(?:[.,]\d+)?", sent))
    nums = [m for m in nums if not re.fullmatch(r"(19|20)\d\d", m.group(0))] or nums
    if not nums:
        return None
    m = _random.choice(nums)
    v = m.group(0)
    if "." in v:
        new = v + "9" if len(v.split(".")[1]) < 3 else v[:-1]
    else:
        n = int(v.replace(",", ""))
        new = str(_random.choice([n * 3, n + 7, max(1, n // 2), n * 10])) if n else "5"
    return sent[:m.start()] + new + sent[m.end():] if new != v else None


def game_round(n=12):
    """Real sentences from the knowledge base plus altered copies; Drex decides which are true."""
    pool = []
    for c in CHUNKS:
        if c["kind"] == "file" and c["ws"] in ("company", "classroom"):
            for sent in source_sentences(c["text"]):
                if re.search(r"\d", sent) and 30 < len(sent) < 150:
                    pool.append((sent, c))
    _random.shuffle(pool)
    items = []
    for sent, c in pool[: n]:
        if _random.random() < 0.5:
            bad = _mutate_number(sent)
            if bad:
                items.append({"text": bad, "doc": c, "made": "altered", "orig": sent}); continue
        items.append({"text": sent, "doc": c, "made": "original", "orig": sent})
    def judge(it):
        r = drex({"statement": it["text"], "source": f"{it['doc']['title']}: {it['doc']['text']}"}, {"v": VERDICT})
        v = r["answers"]["v"]
        return {"text": it["text"], "true": v["choice"] == "agree", "verdict": v["choice"], "conf": round(v.get("confidence", 0), 2),
                "ms": r["_ms"], "source": citation(it["doc"]), "source_line": it["orig"], "made": it["made"]}
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        out = [x for x in ex.map(judge, items) if x["verdict"] != "unclear"]
    right = sum(1 for x in out if x["true"] == (x["made"] == "original"))
    return {"items": out, "drex_agrees_with_answer_key": f"{right}/{len(out)}"}


# ---------------------------------------------------------------- replay insurance
REPLAY_FILE = os.path.join(DATA, "replay.json")
REPLAY = json.load(open(REPLAY_FILE)) if os.path.exists(REPLAY_FILE) else {}


def replay_key(route, body):
    return f"{route}|{body.get('ws') or 'company'}|{body.get('mode', 'speech')}|{body.get('llm_mode') or 'drex'}|{(body.get('text') or '').strip()[:500]}"


def remember_replay(key, res):
    REPLAY[key] = res
    try:
        json.dump(REPLAY, open(REPLAY_FILE, "w"))
    except Exception:
        pass


# ---------------------------------------------------------------- HTTP
STATS = {"decisions": 0, "cards": 0, "ms": []}
# guardrails for when the app is exposed publicly (e.g. via ngrok): caps Drex spend
RATE = collections.defaultdict(list)
PER_IP_PER_MIN = int(os.environ.get("HALLUCINOT_PER_IP_PER_MIN", 30))
MAX_DECISIONS = int(os.environ.get("HALLUCINOT_MAX_DECISIONS", 3000))


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        if self.path.startswith("/api/agents"):
            return self._send(200, agents_view())
        if self.path.startswith("/api/judge"):
            phase = JUDGE["phase"]
            if phase == "live" and time.time() - JUDGE["last_live"] > 90:
                phase = "between"
            return self._send(200, {"teams": JUDGE["teams"], "current": JUDGE["current"], "scores": JUDGE["scores"],
                                    "ranking": JUDGE["ranking"], "phase": phase,
                                    "rubric": [{"key": k, "label": l, "question": q} for k, l, q in RUBRIC],
                                    "know": {t["slug"]: g for t in JUDGE["teams"] for g in [know_view().get(t["slug"], [])]}})
        if self.path.startswith("/api/game/round"):
            try:
                return self._send(200, game_round())
            except Exception as e:
                return self._send(503, {"error": str(e)})
        if self.path.startswith("/api/llmstats"):
            return self._send(200, LLM_STATS)
        if self.path.startswith("/api/integrations"):
            return self._send(200, {"slack": bool(secret(".slack_webhook", "SLACK_WEBHOOK_URL")),
                                    "deepinfra": bool(secret(".deepinfra_key", "DEEPINFRA_API_KEY"))})
        if self.path.startswith("/api/kb"):
            by = collections.Counter(c["kind"] for c in CHUNKS)
            wss = {ws: len(I["chunks"]) for ws, I in INDEXES.items()}
            return self._send(200, {"chunks": len(CHUNKS), "by_kind": by, "workspaces": wss, "know": know_view(),
                                    "sources": sorted({c["source"].split(" PR #")[0] for c in CHUNKS})[:50], "stats": STATS})
        path, _, query = self.path.partition("?")
        page = {"/": "home.html" if not query else "index.html", "": "home.html", "/app": "index.html", "/judge": "judge.html"}.get(path)
        f = os.path.join(ROOT, "ui", page or path.lstrip("/"))
        if os.path.isfile(f) and os.path.realpath(f).startswith(os.path.join(ROOT, "ui")):
            ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css", "png": "image/png",
                     "svg": "image/svg+xml"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
            return self._send(200, open(f, "rb").read(), ctype)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        route = self.path.split("?")[0]
        if route == "/api/judge/ingest":  # any file Nace gives us -> teams
            size = int(self.headers.get("Content-Length", 0))
            if size > 25 * 1024 * 1024:
                return self._send(413, {"error": "File too large (25 MB max)"})
            from urllib.parse import parse_qs, urlparse
            name = re.sub(r"[^\w.\- ]", "_", os.path.basename((parse_qs(urlparse(self.path).query).get("name") or ["upload"])[0]))[:120]
            data = self.rfile.read(size)
            try:
                subs, how = ingest_any(data, name)
            except Exception as e:
                return self._send(502, {"error": f"Could not read {name}: {e}"})
            if not subs:
                return self._send(400, {"error": f"Read {name} ({how}) but found no teams in it"})
            if "preview=1" in self.path:  # review step: nothing is imported yet
                with concurrent.futures.ThreadPoolExecutor(6) as ex:
                    rows = list(ex.map(review_submission, subs))
                return self._send(200, {"how": how, "rows": rows})
            done, errors = [], []
            with concurrent.futures.ThreadPoolExecutor(4) as ex:
                for sub, fut in [(x, ex.submit(import_submission, x)) for x in subs]:
                    try:
                        done.append(fut.result())
                    except Exception as e:
                        errors.append(f"{sub.get('team') or sub.get('project')}: {e}")
            return self._send(200, {"how": how, "imported": done, "errors": errors, "teams": JUDGE["teams"]})
        if route == "/api/parse":  # raw file bytes -> NDI -> text
            size = int(self.headers.get("Content-Length", 0))
            if size > 25 * 1024 * 1024:
                return self._send(413, {"error": "File too large for the demo (25 MB max)"})
            from urllib.parse import parse_qs, urlparse
            name = (parse_qs(urlparse(self.path).query).get("name") or ["upload.pdf"])[0]
            name = re.sub(r"[^\w.\- ]", "_", os.path.basename(name))[:120] or "upload.pdf"
            data = self.rfile.read(size)
            STATS["ndi_pages"] = STATS.get("ndi_pages", 0)
            if STATS["ndi_pages"] >= 300:
                return self._send(429, {"error": "NDI page cap reached for this demo"})
            try:
                res = ndi_parse(data, name)
            except Exception as e:
                return self._send(502, {"error": f"NDI could not parse {name}: {e}"})
            STATS["ndi_pages"] += res.get("pages") or 1
            return self._send(200, res)
        if route not in ("/api/analyze", "/api/check", "/api/agents", "/api/agents/delete", "/api/reset", "/api/kb/add",
                         "/api/recap", "/api/slack", "/api/slack/connect", "/api/judge/teams", "/api/judge/analyze", "/api/judge/reset", "/api/judge/register", "/api/judge/import", "/api/judge/score", "/api/judge/import_rows"):
            return self._send(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if route == "/api/judge/teams":
            added, errors = [], []
            for line in (body.get("lines") or "").splitlines():
                if not line.strip():
                    continue
                parts = [x.strip() for x in re.split(r"[,\t|]", line, maxsplit=1)]
                name, url = (parts + [""])[:2] if len(parts) > 1 else (re.sub(r".*github\.com/[\w.-]+/", "", parts[0]), parts[0])
                try:
                    added.append(import_team(name or url, url))
                except Exception as e:
                    errors.append(f"{line.strip()[:60]}: {e}")
            return self._send(200, {"added": added, "errors": errors, "teams": JUDGE["teams"]})
        if route == "/api/judge/import_rows":  # import the rows the user reviewed and fixed
            done, errors = [], []
            rows = [{k: str(r.get(k) or "").strip() for k in ("team", "project", "explanation", "repo", "slides", "demo")}
                    for r in (body.get("rows") or [])]
            with concurrent.futures.ThreadPoolExecutor(4) as ex:
                for sub, fut in [(x, ex.submit(import_submission, x)) for x in rows if x["team"] or x["project"]]:
                    try:
                        done.append(fut.result())
                    except Exception as e:
                        errors.append(f"{sub['team'] or sub['project']}: {e}")
            return self._send(200, {"imported": done, "errors": errors, "teams": JUDGE["teams"]})
        if route == "/api/judge/score":
            try:
                return self._send(200, {"ranking": rank_teams(), "rubric": [{"key": k, "label": l, "question": q} for k, l, q in RUBRIC]})
            except Exception as e:
                return self._send(503, {"error": str(e)})
        if route == "/api/judge/import":
            try:
                subs = parse_submissions(body.get("raw") or "")
            except Exception as e:
                return self._send(400, {"error": f"Could not read that export: {e}"})
            done, errors = [], []
            with concurrent.futures.ThreadPoolExecutor(4) as ex:
                for sub, fut in [(x, ex.submit(import_submission, x)) for x in subs]:
                    try:
                        done.append(fut.result())
                    except Exception as e:
                        errors.append(f"{sub['team'] or sub['project']}: {e}")
            return self._send(200, {"imported": done, "errors": errors, "teams": JUDGE["teams"]})
        if route == "/api/judge/register":
            try:
                t = register_team(body.get("name", ""), body.get("oneliner", ""), body.get("repo", ""))
                return self._send(200, {"team": t, "teams": JUDGE["teams"]})
            except Exception as e:
                return self._send(400, {"error": str(e)})
        if route == "/api/judge/analyze":
            try:
                return self._send(200, judge_analyze(body.get("text", ""), body.get("team") or None))
            except Exception as e:
                return self._send(503, {"error": str(e)})
        if route == "/api/judge/reset":
            JUDGE["current"] = None
            for v in JUDGE["scores"].values():
                v.update(claims=0, agree=0, contradict=0, no_source=0, items=[])
            return self._send(200, {"ok": True})
        if route == "/api/recap":
            return self._send(200, write_recap())
        if route == "/api/slack/connect":
            url = (body.get("url") or "").strip()
            if not url.startswith("https://hooks.slack.com/"):
                return self._send(400, {"error": "Paste a Slack incoming-webhook URL (https://hooks.slack.com/...)"})
            fd = os.open(os.path.join(ROOT, ".slack_webhook"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.write(fd, url.encode()); os.close(fd)
            return self._send(200, {"ok": True})
        if route == "/api/slack":
            try:
                post_slack((body.get("text") or "")[:3500]); return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(400, {"error": str(e)})
        if route == "/api/kb/add":  # add a parsed document to the knowledge base; its rules become agents
            text, name = (body.get("text") or "")[:200000], re.sub(r"[^\w.\- ]", "_", body.get("name") or "uploaded")[:120]
            ws = body.get("ws") or "company"
            if len(text) < 40:
                return self._send(400, {"error": "Nothing to add: the document is empty"})
            with LOCK:
                before = sum(1 for a in AGENTS if a["source"] == "docs")
                n = add_document(text, name, ws); build_index(); load_agents()
                for t in JUDGE["teams"]:
                    if t["slug"] == ws: t["sections"] = t.get("sections", 0) + n
                new_rules = [a for a in AGENTS if a["source"] == "docs" and a.get("doc") == name]
            return self._send(200, {"chunks_added": n, "ws": ws, "new_agents": [a["rule"] for a in new_rules],
                                    "workspaces": {w: len(I["chunks"]) for w, I in INDEXES.items()}})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        local = "X-Forwarded-For" not in self.headers and self.client_address[0] == "127.0.0.1"
        now = time.time()
        hits = [t for t in RATE[ip] if now - t < 60]
        RATE[ip] = hits + [now]
        if (not local and len(hits) >= PER_IP_PER_MIN) or STATS["decisions"] >= MAX_DECISIONS:
            return self._send(429, {"error": "Slow down: demo rate limit reached"})
        ws = body.get("ws") or "company"
        if self.path == "/api/agents":  # add a custom agent from one plain-English rule
            rule, name = (body.get("rule") or "").strip()[:300], (body.get("name") or "").strip()[:60]
            if len(rule) < 8:
                return self._send(400, {"error": "Write the rule as a yes/no question or statement"})
            a = {"id": f"custom{int(time.time()*1000)}", "icon": "🚩" if body.get("type") != "log" else "📝",
                 "name": name or agent_name(rule), "type": body.get("type") if body.get("type") in ("flag", "log") else "flag",
                 "rule": rule, "source": "custom"}
            with LOCK: AGENTS.append(a); save_custom()
            return self._send(200, agents_view())
        if self.path == "/api/agents/delete":
            with LOCK: AGENTS[:] = [x for x in AGENTS if not (x["id"] == body.get("id") and x["source"] == "custom")]; save_custom()
            return self._send(200, agents_view())
        if self.path == "/api/reset":  # clear what was learned this session (for rehearsals)
            with LOCK:
                CHUNKS[:] = [c for c in CHUNKS if c["kind"] != "learned"]; LEARNED.clear(); ACTIONS.clear(); SESSION.clear()
                AGENT_STATS.clear(); LAST_FLAG.clear(); LLM_STATS.clear(); build_index()
            return self._send(200, agents_view())
        rkey = replay_key(route, body)
        try:
            if self.path == "/api/check":
                res = check_document(body.get("text", "")[:20000], ws)
                STATS["decisions"] += res["drex_calls"]
                remember_replay(rkey, res)
                return self._send(200, res)
            if body.get("mode", "speech") == "speech":
                res = analyze_live(body.get("text", ""), body.get("previous", ""), ws, body.get("llm_mode") or "drex",
                                   [str(a)[:300] for a in (body.get("alternatives") or [])][:5])
            else:
                res = analyze(body.get("text", ""), body.get("mode", "speech"), body.get("previous", ""), ws)
        except Exception as e:  # keep the demo alive: fall back to a recorded real answer if we have one
            if rkey in REPLAY:
                return self._send(200, {**REPLAY[rkey], "replayed": True, "replay_reason": str(e)})
            return self._send(503, {"error": str(e)})
        remember_replay(rkey, res)
        STATS["decisions"] += 1; STATS["cards"] += bool(res.get("show"))
        if res.get("drex_ms"): STATS["ms"] = (STATS["ms"] + res["drex_ms"])[-200:]
        self._send(200, res)

    def do_HEAD(self):
        self._send(200, b"", "text/html")

    def log_message(self, fmt, *args):
        if args and "/api/analyze" in str(args[0]):
            sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", action="append", help="folder to index; use name=PATH to put it in a workspace (repeatable)")
    ap.add_argument("--repo", action="append", help="GitHub repo owner/name to index PRs from (repeatable)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8787)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    args = ap.parse_args()
    print("Building knowledge base:")
    folders = args.folder or [f"company={os.path.join(ROOT, 'kb', 'company')}", f"classroom={os.path.join(ROOT, 'kb', 'classroom')}"]
    for f in folders:
        ws, path = f.split("=", 1) if "=" in f else ("company", f)
        LOADING_WS[0] = ws
        if os.path.isdir(os.path.expanduser(path)):
            load_folder(os.path.expanduser(path))
    LOADING_WS[0] = "company"
    repos = args.repo or []
    if not repos and os.path.exists(os.path.join(ROOT, "kb", "github", "flask_prs.jsonl")):
        load_pr_file(os.path.join(ROOT, "kb", "github", "flask_prs.jsonl"), "pallets/flask")
    for r in repos:
        load_repo(r)
    build_index()
    load_agents()
    print(f"Agents: {len(AGENTS)} ({sum(a['source']=='docs' for a in AGENTS)} learned from your documents)")
    print(f"Ready: {len(CHUNKS)} chunks. Open http://localhost:{args.port}")
    ThreadingHTTPServer((args.host, args.port), H).serve_forever()
