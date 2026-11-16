# Live-run rehearsal: a new IPO, end to end, from two links

Date of the rehearsal: 16 Nov 2026 (machine clock 15 Nov 2026, 17:48 UTC). Goal: prove the
pipeline works on an event it has never seen, the way it would be shown live: an RM pastes
links, the event is filed, "Process now" is pressed, and the call list appears with every
number traced to a page. Everything below is measured from `outputs/runs.csv`,
`cost_log.csv` and `outputs/sahajanand_medical_technologies_limited_ipo_202611/trace.json`.

## The event and why it was picked

| | |
|---|---|
| Company | Sahajanand Medical Technologies Limited (main board, BSE and NSE) |
| Event | IPO, 100% offer for sale: 13,822,116 shares at ₹344 (₹475.48 crore) |
| Bid period | 15–19 Oct 2026; allotment 21 Oct 2026 |
| Listed | **23 Oct 2026**: 24 days before 16 Nov, inside the 30-day window. The call list says "23 days ago" because it counts from the machine date, 15 Nov |
| Documents | SEBI-hosted red herring prospectus (569 pages): `https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1791785603861.pdf`; NSE basis-of-allotment advertisement (2 pages): `https://nsearchives.nseindia.com/corporate/ADV_INE356Y01018_22OCT2026.pdf` |

How it was found, and why it was the right test:

1. `outputs/discovery.json` and the SEBI "red herring documents filed with ROC" listing showed
   every main-board IPO of the last 30 days. Every one with a final prospectus on SEBI was
   already in `events/auto/`. Two RHPs from 9–10 Oct had no event and no prospectus on SEBI.
2. This one's RHP cover prints the anchor bid date (14 Oct). The NSE allotment advertisement
   confirms the price, ₹344, and "trading is expected to commence on October 23, 2026". The
   30-day test rests on that exchange document, not on news sites.
3. It is a **pure offer for sale**, so all the money goes to the sellers. That is exactly what
   an RM wants: who received cash and how much. The sellers are a promoter trust, one
   promoter-group individual and three investor funds.
4. The RHP prints every price as ₹[●]. The price and the dates exist only in the exchange
   notice, so this run tests the two-document path: the RHP for people and share counts, and
   the notice for price and dates.

The NSE file name follows the exchange's pattern `ADV_<ISIN>_<date>.pdf`. It was found from
the ISIN and checked by opening the PDF. Fetching it is a plain public GET, with no headers
added and no 401/403 to bypass.

## Timeline (first run, fresh: no cached model answer for this event)

| Step | What happened | Time | Model calls | Cost |
|---|---|---:|---:|---:|
| Add from links | `POST /api/events/from-links` with the 2 URLs: both PDFs downloaded (7.3 MB + 1.4 MB). Type, document kind and company found by rules from the first pages, with no model call | 7.1 s | 0 | $0 |
| File the event | `POST /api/events` (the add-event dialog's spec) | 0.01 s | 0 | $0 |
| Process now: find pages | Downloads reused from the step above. **PDF to text: 27.2 s for 569 pages.** Page scoring: 3.4 s | 31.4 s | 0 | $0 |
| Read the tables | 10 sections, one Haiku call each, then each answer verified in code against its cited pages | 32.9 s | 10 | $0.01418 |
| Match people and families | 10 rows → 8 people, 2 merges, 1 family, no model needed | 0.04 s | 0 | $0 |
| Rank | 4 to call, 4 entities | 0.03 s | 0 | $0 |
| Briefs | 4 people, 5 calls (1 retry) | 8.6 s | 5 | $0.00118 |
| Assemble | report.md, cost.json, trace.json | 0.04 s | 0 | $0 |
| **Total (Process now)** | | **72.9 s** | **15** | **$0.0154** |

Tokens: 121,957 in, 6,332 out. That is 0.8% of the $2 budget per event. Every step and every
one of the 31 agents shows in the live agent tree as it runs, and in the trace view on the
event page afterwards. Screenshots were taken locally and are not in the repo: `live-live-*.png` during the run,
`live-done.png`, `rerun-done.png`, `cached-done.png` and `final-trace.png`, in the
screenshot folder next to the repo (`.shots/trace/`).

## What broke, and the generic fixes

Both problems are generic: no company or person name is in the code. Each has a test.

**1. The issuer's shareholding table lost to a subsidiary's (locate).**
Pages 308–313 are the "Our Subsidiaries" chapter. Each subsidiary has a "Capital structure and
shareholding pattern" sub-heading and repeats "shareholding pattern" three times, so those
pages outscored the company's own table (pdf 124, "Shareholding Pattern of our Company"). The
model correctly found no holders there. As a result, the promoter-group seller's pre-offer
holding of 4,082,700 shares was never read, and their retained stake showed as "unknown".
*Fix* (`config/sections.py`, `agents/locate.py`): a counter-term with negative weight and no
heading or table bonus (`"capital structure and shareholding pattern"`, −8), plus an
issuer-phrase term (`"shareholding pattern of our company"`, +8). Re-scoring every event on
disk moved the issuer page to the top for three other IPOs and dropped a subsidiary page from a
fourth's list. Nothing else changed.
Test: `tests/test_locate.py::test_issuer_shareholding_pattern_outranks_a_subsidiary_write_up`.

**2. The top person's brief fell back to the template (briefs).**
The model wanted to say when the kept shares unlock ("locked until 21 Apr 2027"). There was no
placeholder for that date, so it wrote the digits and failed the no-digits rule twice. Across
all events, 11 of 109 briefs had fallen back the same way: the model wrote a date or invented
a placeholder name. *Fix* (`agents/brief.py`): the retry now lists the exact placeholders the
person has and offers `{locked_until}`, the first future lock-in end, filled by code. The first
request is unchanged, so every cached brief stays valid and costs nothing to rerun.
Test: `tests/test_rank_brief_report.py::test_retry_offers_the_lock_in_end_date_as_a_placeholder`.

## Second and third runs (after the fixes)

| Run | Time | Model calls | Reused | Cost | What changed |
|---|---:|---:|---:|---:|---|
| 1 (fresh) | 72.9 s | 15 | 0 | $0.0154 | |
| 2 (after fixes) | 19.4 s | 16 | 12 | $0.0028 | Only the shareholding-pattern section was read again ($0.0021), plus 3 new briefs |
| 3 (no change) | 4.6 s | 16 | 16 | **$0.0000** | Everything reused. The panel reads "This run $0.0000 vs first run $0.0154 — 16 of 16 model calls reused · 4.6 s vs 1 m 13 s" |

The 4.6 s floor is now page scoring (3.4 s for 569 pages, in code). The parsed pages and the
model answers are both cached.

## Call list quality (after the fixes)

**To call (5).**

1. **Promoter-group selling shareholder.** Up to ₹68.80 crore in hand since 23 Oct 2026
   (2,000,000 × ₹344). Gain up to ₹68.67 crore over a ₹0.63 average cost. Keeps at least
   2,082,700 shares, locked until 21 Apr 2027. Each figure links to its page: shares offered
   (p. 470), average cost (p. 117), price (NSE notice p. 1). The brief is written by the model
   and every number in it was checked.
2. **A public shareholder from the top-ten table.** Holds 1,095,890 shares, about ₹37.70 crore
   at the offer price. This is shares, not cash, and the person is not a seller. The pipeline
   found this person only after fix 1.
3–5. **The three named promoters.** One holds 5,000 shares. Two print "Nil" because they hold
   through the promoter trust. Both lock-in dates (21 Apr 2027 and 21 Apr 2028) come from the
   lock-in rule pages, with the arithmetic shown.

**Entities (6).** The investor fund sellers (up to ₹222.88, ₹45.93 and ₹44.99 crore), the
promoter trust (up to ₹92.88 crore), the employee stock trust and one investment firm.

**Still weak (honest list):**

- **Trust beneficiaries.** The promoter trust received up to ₹92.88 crore, but its
  beneficiaries are the promoters. The two promoters printed as "Nil" show an amount of
  "unknown" when it should be "₹0 directly, beneficiaries of a trust that sold". Linking a
  trust to its family is not modelled yet. This is the biggest gap for an RM on this event.
- **Missing role.** The public shareholder's role is "unknown" because the top-ten table has
  no role column.
- **Payment day.** The day sellers are paid is not printed in either document. Proceeds timing
  uses the listing date and flags this as a TODO, and confidence stays medium.
- **Speed.** PDF to text dominates a fresh run (27 s of 73 s). See `docs/what_if.md` for 500
  events a week.
