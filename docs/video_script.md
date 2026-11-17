# Video script (under 10 minutes)

**Goal:** run one event live, and say at each moment which agent is running, why that one, and what it costs.

**Set-up before recording** (none of this is on camera):
- `./demo.sh start`, signed in as `admin@finsight.demo`. Browser at 1440×900.
- A terminal on the left half, the browser on the right.
- **The live event:** an IPO or buyback filed on SEBI in the last few weeks that is **not** yet in `outputs/` (Events → New filings lists them). Keep its document link copied. Fallback: any stored event run with an empty model cache, so every call is paid again: `LLM_CACHE_DIR=$(mktemp -d) .venv/bin/python run.py --event events/<id>.json --step all`.
- Check the key once: `.venv/bin/python -m tools.llm --ping`.

| Time | Screen | What I say |
| --- | --- | --- |
| **0:00–0:40** | Home (control tower), empty prompt box | "A wealth firm's RMs hear about IPO money a month late. This reads the public filings for a money event and tells an RM who to call, how much, when, how sure we are, and the page that proves it. One rule above all: **the system never invents a number.** The model copies text; code checks it and does every sum." |
| **0:40–1:30** | **Today** | "This is the RM's morning: cash in hand first, then shares that just unlocked, then holders. Not the richest people: the people whose money just moved. Households are grouped, so one family is one conversation." |
| **1:30–2:10** | Home: paste *"Process this IPO: \<link\>"* → the **estimate card** | "Before anything spends money, it shows the bill: each step, which model, how many calls, and a low–high range in dollars, all from what past runs really cost. Nothing runs until I confirm." → **Confirm** |
| **2:10–2:40** | Steps streaming. Terminal: `.venv/bin/python run.py --event events/<id>.json --step all` (if run from the terminal instead) | "Now watch which agent runs, and why." |
| 2:40–3:10 | Step **fetch + locate** | "**Fetch** and **locate** are plain code. The offer document is hundreds of pages. Code scores every page for fixed SEBI headings (selling shareholders, shareholding pattern, price, timetable) and keeps the top few per section. No model has read anything yet, and it has cost nothing." |
| 3:10–4:00 | Step **extract** (`STEP extract … calls=…`) | "**Extract** is the only reading the model does: `claude-haiku-5.5`, one small call per section, 3 to 5 pages each. It must return each value with a quote. Why the cheap model? Because it only copies; it never decides or calculates." |
| 4:00–4:40 | Same step, the verify counts | "**Verify** is code. Is the quote on the cited page? Is the value inside the quote? Is it in this person's row? If any answer is no, the value becomes *unknown*, with the reason. If the verified rows don't add up to the printed total, the section is re-asked once." |
| 4:40–5:20 | Step **people** | "**People** is code: names normalised, families grouped, `Decimal` arithmetic (shares × price), and timing from the lock-in rule quoted from *this* filing. Only when two names are nearly the same and the rules can't decide, like *CEAQ Technologies Private Limited* and *CEAQ Technologies Pte. Ltd.*, does a stronger model (`claude-sonnet-5.5`) get one question. Unsure stays separate, and flagged." |
| 5:20–5:50 | Steps **rank → brief → report** | "**Rank** is code: cash now beats an unlock, which beats a holding. **Brief**: the model writes the words, but every number is a placeholder that code fills in. If it slips in a digit of its own, the brief is rejected." |
| **5:50–6:30** | The finished event page + the terminal's timeline table | "Done. This first run cost **$\<total\>** in **\<seconds\>** s. For comparison, the most expensive event so far cost $0.029 fresh, against a $2 budget." Then run the **same command again**: "Second run: every call is a cache hit, so **$0.000**. Downloads are cached by URL and content hash, and model answers by model, prompt version and the exact pages sent." |
| **6:30–7:30** | Open the top person → **click the ₹ figure** | "Here is the moment that matters to a Head of RMs. The ₹ figure shows its working, and one click opens the filing at that page with the quote highlighted. If we can't show the page, we don't show the number." |
| 7:30–8:20 | Home: *"What money does Sharma have?"* → the clarify options → pick one → steps with model and $ each | "The control tower asks back when a name is ambiguous, instead of guessing. Exact lookups run on code for $0. A model (`gpt-6-luna`) is used only to understand the question. Every number in its answer is checked against the data, and removed if it isn't there." |
| 8:20–9:10 | `whats_broken.md` on screen | "Where it's wrong. One real case: Zetwerk's subsidiary table was read as a shareholder, worth ₹4.18 crore. Every check passed, because the number *is* printed; it just isn't a Zetwerk holding. The fix is binding each value to a table cell and its column, and that's first on my two-week list. Measured accuracy on 20 hand-checked people is in the README." |
| **9:10–9:40** | Trust & Ops | "Every run is logged: cost per event and per person, time per step, and checked vs rejected values. All development so far: about $0.46 across about 2,000 model calls." |

**Lines to have ready if asked:**
- *Why no agent framework?* The step order is fixed, and the hard parts (finding pages, checking quotes, arithmetic) are code a framework doesn't help with.
- *What stops follow-on leads from exploding?* The pipeline looks only at already-processed events, one level deep, at most 10 matches per person. The chat deep dive has a $0.25 budget, caps per branch kind, depth 2, a visited set, and most promising first.
- *Budget cut to $0.50 per event?* Already under it. The first cut would be briefs (the template costs $0), then strong-model name checks (flag them unsure instead).
