# Hallucinot: slide content (for Adobe Express)

Six slides, one idea each. Use the Firefly 🦖 art if it's ready. Speaker notes are in *italics*.

---

## 1. Hallucinot 🦖
**For once, AI fixes *human* hallucinations.**
Live fact-checking for meetings, docs and chatbots, decided by Drex.
Team: Harsh · Mahak

*"Everyone worries about AI hallucinating. Humans do it in every meeting."*

---

## 2. The problem
- In meetings people state wrong numbers, make promises the contract doesn't allow, and leak secrets.
- Sales one-pagers, chatbot answers and student posters carry the same made-up facts.
- Nobody checks in real time. The mistake ships, and someone fixes it later at a cost.

*"Microsoft is shipping a version of this for Teams. The hard part is deciding when to speak, on every sentence, cheaply."*

---

## 3. How it works: a team of agents, every decision by Drex
**Knowledge:** your docs, contracts and GitHub PRs, parsed by **NDI** (PDF, scans, slides, images)
→ **Drex router** classifies each sentence: question, claim, promise or small talk
→ **Agents run in parallel**, each one a Drex decision:
📚 Fact checker · 💡 Suggest · ⚖️ Policy guards (**auto-created from your documents' rules**) · 📝 Action items · 🔒 Leak guard · 🧠 Decision recorder · 🚩 your own rules in plain English
→ **Agents negotiate:** when two disagree, a third Drex call arbitrates
→ **Card with receipts:** the exact source line, plus the correct sentence to say instead

---

## 4. It learns with no clicks
- 🧠 A decision announced in the meeting is remembered: *"We moved the SLA to 99.95%."*
- ⚠️ Later: *"So the SLA is 99.9%, right?"* → "This changed today. The contract may be outdated."
- ✅ When someone corrects themselves after a card, the agent learns it helped (+1).
- ➕ Upload a policy PDF and its rules **become new agents** instantly.

---

## 5. Beyond meetings
- 📄 **Check any document:** chatbot answers, customer emails, sales flyers. Every claim gets 🦖 / ✅ / 🟡, plus **Fix** and **Cite**.
- 🎓 **Classroom (Adobe EDU):** a student's Adobe Express poster → wrong facts caught → corrected from the course notes, with citations.
- 🧩 **Chrome extension:** checks whatever tab you're on.
- 📋 **After the meeting:** a recap goes to Slack, and **@Intern** follows up on the action items.

---

## 6. Why Drex
| | Drex | Claude Opus |
|---|---|---|
| Picked the right source (50 meeting lines, 300 real PRs) | **47/50** | 47/50 |
| Time per decision | **0.38 s** | 2.2 s |
| Cost per 1M sentences | **~$30** | ~$15,000 |

**Same accuracy, about 6× faster, about 500× cheaper.** That's what makes checking *every sentence* by *many agents* possible.
When unsure, Drex said "none" instead of guessing: a hallucination detector that doesn't hallucinate.

### Drex as System 1, the LLM as System 2
Same 12-line meeting, two designs (DeepInfra Llama 3.3 70B as the writer):

| | **Drex decides when the LLM writes** | LLM on every sentence |
|---|---|---|
| LLM calls | **5 / 12** (58% fewer) | 12 / 12 |
| LLM cost | **~7× lower** | baseline |
| Discount-policy break caught | ✅ | ❌ |
| Leaked API key caught | ✅ | ❌ |
| Action item logged | ✅ | ❌ |

*Drex doesn't replace the big model. It decides when the big model is worth calling, and it catches what the big model misses.*

**Content Credentials prove who made it. Hallucinot proves what it says is true.**
