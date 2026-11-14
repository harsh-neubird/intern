> **Drexathon entry (Wildcard track).** Team Hallucinot: Mahak Gupta and Harsh. This folder is a copy of the project for review next to Intern; it does not change any Intern code. Canonical repo: https://github.com/harsh-neubird/hallucinot

# Hallucinot 🦖

*For once, AI fixes **human** hallucinations.*

Hallucinot listens to what you say (or reads the tab you're on), finds the relevant piece of your knowledge base, and shows it. When you say something that contradicts the source, it says so in red with the receipt. Every decision is made by **Drex**: should we speak, which document, and does it agree or contradict.

**Built with Nace:**
- **Drex** makes every decision: the router, each agent, the verdict, which fix to show, and the negotiation between agents.
- **NDI** (Perception API) parses uploaded PDFs, images (OCR), Word and slides into the knowledge base, and the rules it finds become new agents.
- **Intern** gets the meeting recap and action items in Slack for follow-up.

**Partners:**
- **Adobe Express / Firefly:** classroom posters, slides.
- **DeepInfra:** "System 2" writer for the recap.

| Feature | Where |
|---|---|
| 🎙️ Live meeting: agents check every sentence, learn decisions, negotiate | Live tab |
| 📄 Check any document claim by claim, with **Fix** and **Cite** | Check a document tab |
| ➕ Add knowledge (PDF, image, Word, slides via NDI); its rules become agents | "What I know" box |
| 📋 Meeting recap → Slack → **@Intern** follows up on action items | "After the meeting" box |
| 🧩 Chrome extension: check the tab you're on | `extension/` |
| ✍️ System 2: Drex decides when DeepInfra's LLM writes (answers, corrections); toggle to compare with LLM-on-every-sentence | Live tab, Writer toggle |
| 🛟 Replay insurance: real answers recorded and replayed (labeled) if the API is down | automatic |

Optional keys (files are git-ignored, or set them as env vars): `.nace_key` / `NACE_API_KEY` (required), `.deepinfra_key` / `DEEPINFRA_API_KEY`, `.slack_webhook` / `SLACK_WEBHOOK_URL`.

## Run it

```bash
git clone https://github.com/harsh-neubird/hallucinot && cd hallucinot
echo "YOUR_NACE_KEY" > .nace_key      # or: export NACE_API_KEY=...
python3 server.py
```

Then open http://localhost:8787 in **Chrome**. Click **Start listening**, or type a sentence and press Enter.

To use your own knowledge (any folder, any public GitHub repo):

```bash
python3 server.py --folder ~/path/to/docs --repo owner/name
```

- **Folders:** `.md .txt .csv .json .py .js .yaml …` are read directly. PDFs go through `parse_pdf()` in `server.py`; swap in **NDI** there at the event.
- **Repos:** the last ~300 merged PRs are fetched with `gh` and cached in `kb/github/`.
- **Drex key:** read from `NACE_API_KEY` or the `.nace_key` file (git-ignored).

Without flags, the server loads `kb/company/` (fictional "Quokka Analytics" docs) plus the `pallets/flask` PRs.

## Check a document (any text, claim by claim)

Open the **📄 Check a document** tab. Paste text or drop a PDF (for example one exported from **Adobe Express** or Acrobat), then click **Check every claim**. Each sentence gets one of:
- 🦖 **Hallucination**, with what the source actually says
- ✅ **Checks out**
- 🟡 **No source**, meaning add a citation

The built-in samples are a 🤖 chatbot answer, a 🎓 student poster and a ✉️ customer email. Sentences are checked in parallel, so a whole document takes about 1 second.

**Workspaces:** switch the knowledge base between 🏢 **Company** (`kb/company` + GitHub PRs) and 🎓 **Classroom** (`kb/classroom`, demo Bio 101 notes). Add your own with `--folder name=PATH`.

## Multi-agent (Track 2: Swarm Intelligence)

Every sentence goes through a Drex router, then a panel of agents evaluates it — each one a separate Drex call, so no agent's verdict is generated, only decided. Built in: 📚 Fact checker, 📝 Action items, 🔒 Leak guard, 🧠 Decision recorder. Plus ⚖️ policy agents that write themselves — every rule-like sentence in your documents ("requires...", "only...", "cannot...") becomes a standing checker automatically. Plus custom agents typed in plain English via **+ Add agent**.

It learns with no clicks: a decision announced in the meeting is remembered; a later statement that contradicts it shows ⚠️ "this changed today"; a self-correction counts as "learned (+1)".

**Agents don't just run in parallel — they negotiate.** When ⚖️ Policy guard flags a statement by a rule's wording, and 📚 Fact checker independently finds the same statement actually matches the real source, that's a live disagreement between two agents. A third Drex call arbitrates between their two positions, and one agent can stand the other down — the system shows a single 🤝 resolved verdict instead of two conflicting cards.

Demo lines (prefix with a speaker name, e.g. `Dana: ...`, and **↺ Reset session** first):
| Say | Expected |
|---|---|
| "Sure, I can give you 20% off if you sign today" | ⚖️ Policy guard |
| "We're giving Acme a 25 percent credit this month since their uptime dropped below 99 percent" | ⚖️ would normally fire (>10% needs approval) — 📚 Fact checker matches it to the SLA's automatic credit clause — 🤝 Drex arbitrates and stands the policy flag down |
| "Our SLA with Acme is 99.99 percent uptime" → "Sorry, I meant 99.9 percent" | 🦖 then ✅ corrected (+1) |
| "I'll send you the renewal quote by Friday" | 📝 Action items |
| "The staging API key is sk-live-8812" | 🔒 Leak guard |
| "We decided last week to move the SLA to 99.95 percent" → "So the SLA is 99.9 percent, right?" | 🧠 learned → ⚠️ outdated |

## Chrome extension (any-tab mode)

1. Start the server (above).
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and pick the `extension/` folder.
3. Click the Hallucinot toolbar icon to open the side panel. It checks each tab you switch to, or click **Check this page**. Select text on a page to check just that.

Use the mic on the main page at localhost:8787. Inside the side panel, Chrome may block the microphone.

## Demo script

| Say / show | Expected |
|---|---|
| "Why did churn go up in Q3?" | 📄 Q3 metrics: Starter plan price increase |
| "Let's grab lunch after this." | 🤫 stays quiet |
| "We switched redirects to 301." | 🦖 Human hallucination: PR #5898 says 303 |
| "Our SLA with Acme is 99.99 percent uptime." | 🦖 Contract says 99.9% |
| "Acme gets a 10% credit if uptime drops below 99.9%." | ✅ Checks out |
| "We use JWTs for dashboard login." | 🦖 Design doc: session cookies, not JWTs |
| Gmail tab with Raj's email claiming 99.99% / 25% credit | 🦖 Contract clause |
| A random recipe site | 🤫 stays quiet |

## How it works

```
mic (Chrome speech-to-text) or tab text
  → keyword search over the knowledge base → top 12 candidates
  → Drex call 1: what was said (question / claim / other) + which candidate (or none)
  → Drex call 2 (claims only): agree / contradict / unclear vs the chosen source
  → card: blue context · green checks out · red hallucination · amber unsure
```

Typical latency: about 0.3 s per Drex call, 0.6 s for a full fact-check.

## Benchmark (Drex vs Claude)

`eval/cases.py` holds 50 meeting lines labeled against the Flask PRs. The 2026-11-13 run: Drex 47/50 and Claude Opus 5.5 47/50. Drex took a median 0.38 s against 2.2 s for Claude, at roughly 1/500th of the cost. All three misses came from the keyword search, not from either model.
