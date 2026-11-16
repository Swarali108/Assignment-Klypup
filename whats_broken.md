# What's broken

The system's promise is narrow: **every figure an RM sees is printed in a public filing, or labelled an estimate with its working.** Most of the time it keeps that promise by showing "unknown" instead of guessing. Below is where it does not, measured on the 19 events stored in `outputs/` as of 15 Nov 2026.

> **Why it matters.** An RM who calls a promoter with the wrong ₹ figure loses the relationship on the first call. A wrong number is worse than a missing one, so this page leads with wrong numbers, then wrong ranks, then gaps.

## Measured accuracy

On a 20-person sample (top 3 by rank in 6 events, plus 2 extra), **109 of 118 fields that the filings print were right (92%), 0 were wrong and 9 were missing** (shown as "unknown"). The 22 fields the filings leave blank were all left unknown: nothing was invented. 15 of 20 people have every field right. The weakest event is the FDC buyback (6 of 12): the promoter role and the ₹500 price are printed but not picked up. The full table, the limits of the sample and the command to re-run it are in the [README](README.md#measured-accuracy). The sample comes from people the system already called, so it does not count people it missed, which is the larger risk and is not yet measured.

## 1. A real wrong answer

**Zetwerk IPO: "Our Company" holds ₹4.18 crore of shares.** It is in the Zetwerk event's organisations list (rank 10 of 13 entities), with a source link that opens a real page:

| What the system shows | What the page actually says |
| --- | --- |
| Holder "Our Company", 276,814 shares, **₹4.18 crore** (estimate, valued at the ₹151 offer price) | Prospectus pdf page 381 (printed p. 377): *"the shareholding pattern of **Sharp Tanks** is as follows: … value of ₹ 100 each … Our Company 276,814 99.99"* |

This is Zetwerk's stake in a **subsidiary**, not a holder of Zetwerk. The subsidiary's shares have a ₹100 face value and were multiplied by Zetwerk's own IPO price. Every check passed: the quote is on the cited page, 276,814 is inside the quote, and the quote sits in that holder's row. The checks prove that a number is **printed**. They do not prove that it **means what we think**. The page finder ranked six subsidiary shareholding tables above the issuer's own table, and nothing in the rules asks "whose shareholding table is this?".

It does little harm to an RM, because an organisation called "Our Company" is not on the call list. It still breaks the product's rule, so it goes first.

**Two more, both still live in the outputs:**

- **Vectras IPO shows a ₹4.93–5.23 crore range per seller, although the final price is printed.** The prospectus says *"FOR CASH AT A PRICE OF ₹ 105 PER EQUITY SHARE"* (pdf 3). The model's quote for the price was *"the Offer Price is 10.50 times of the face value of the Equity Shares"* (pdf 102). Code correctly rejected it, since 105 is not in that sentence. The system then fell back to the ₹99–105 band. The failure is safe (the range contains the truth, ₹5.23 crore), but it is still wrong, because the system never looked for the price a second time.
- **SEDEMAC's Pushkaraj Panse ranks #18 of 19 with ₹118.23 crore of shares.** No role is printed next to his holding, so the timing rules cannot place him, and "timing unknown" is weighted 0.25. The RHP's lock-in applies to all pre-offer capital, which would make him "just unlocked" and put him near the top. The amount is right; the call order is wrong.

## 2. Wrong answers that can happen on a new event (reproduced on synthetic rows only)

| Risk | How it happens | Real page with this shape |
| --- | --- | --- |
| **Wrong column, right row** | A seller row prints "pre-offer holding, shares offered, % pre, % post". If the model copies the holding into "shares offered", the quote, page and row checks all pass. Proceeds would come out several times too high. | SFC pdf 163: *"Mulesh Manilal Savla (held jointly 170,625 0.18% 170,625 0.17%"* |
| **Total row attaches to the last person** | A row ends at the next extracted name, or 400 characters later. After the last seller there is no next name, so a "Total" line can bind to them. | None found in the stored events; reproduced only with a made-up table |

The fix is to bind each value to a table cell (row = this name, column = this header), not to a text window. I started on it in `tools/tables.py`, but that code can only **rescue** values the text check rejected: it rescued 20 kept values. It cannot yet **block** a wrong column.

## 3. Gaps that show as "unknown" or as nobody

- **Six of the 7 buybacks processed by 15 Nov yield nobody with cash.** At Garware (14 people) and Jyothy (16), the promoters printed in the letter of offer are the ones *not* tendering, so they sit in a "context" list, not the call list. FDC's 3 promoters are listed as holders, because the system could not verify the buyback price (₹500 is printed 3 times on a newspaper-style page). Goa yields nobody. Genus and Medi Assist are scanned images, and there is no OCR. The exception is **Wipro (`wipro_buyback`)**: its letter of offer prints each promoter's maximum tender (table 7.1), the ₹250 price and the "10 for every 197" entitlement, so 4 people reach the call list with estimated cash (Azim H Premji ≈ ₹332.60 crore, the others ₹6.50–17.18 crore, paid by 24 Jun 2026). These are estimates at the entitlement ratio, not shares actually accepted: the post-buyback announcement that would give the real figure is a scan with no text layer.
- **Follow-on leads have found nothing yet.** The cross-event index holds 183 people from 15 events, and 0 of them match a person in another event. The code works (tested), but these events simply do not share sellers. One level deep is untested on real overlap.
- **21 of 105 callable people have no ₹ figure**, and 82 proposed values were rejected by the checks (down from 115). The main reasons are "no evidence" (31) and "value not in quote" (20).
- **KMP and ESOP tables are located but never extracted.** Named key managers with options are missed. Unnamed ESOP holders are, correctly, never invented.
- **Brief wording can stumble after code fills the numbers**, e.g. *"…are in hand since in hand since 11 Mar 2026"* (SEDEMAC, Atul Hiralal Shah). The numbers are right; the sentence is clumsy.
- **The chat's number check compares digits, not units.** Prose that says "₹17 lakh" passes when the data holds 17 as crore. Every figure on a card comes from stored values, so the risk is in the short prose only.

## 4. What I tried that did not work

| Tried | What happened | What replaced it |
| --- | --- | --- |
| Anchor a person's row on the first time their name appears on the page | Manish Sharma lost his 45,000 offered shares, because a paragraph mentioned him far above the table | Anchor on the span of that row's own name quote |
| Let the model write briefs, then check that each number appears somewhere in the person's fields | It passed *"retained 42,000 shares"*. 42,000 was his pre-offer holding; he kept 29,400 | The model writes `{placeholders}`; code fills every digit. The same brief now reads *"They keep at least 29,400 shares"* |
| Find lock-in end dates by matching anchor words | Column-split pages interleave words: *"4.85 November Aggarwal 2025 3, 2029"* (BLS pdf 122). No anchor list can read that | Still open: needs table reading (item 1 below) |
| Run the pipeline inside the Streamlit page | Any click stopped the page from watching the run | Moved to a FastAPI job with a live progress stream |
| Read NSE/BSE feeds for discovery | Their terms forbid automated collection | SEBI listings only; an exchange PDF is added by hand when needed |

## 5. Where AI tools helped, and where they misled me

**Helped most:**
- Writing the dull, exact code fast: Indian number formats (`74,99,820`), PDF page mapping, and 311 offline tests.
- An independent audit pass that re-derived numbers from the cached pages. It found the Zetwerk subsidiary figure and the Vectras price, which I had not seen.
- Copying text from 3–5 chosen pages for a fraction of a cent: about $0.002–$0.029 per event when run fresh.

**Misled me:**
- **Confident wrong quotes.** It quoted "10.50 times of the face value" as the offer price. The verifier caught it, but only because I had made the verifier distrust the model.
- **Instructions it contradicted itself.** A prompt example wrote `{retained_shares} shares` while the checker rejected exactly that, so briefs that followed the example were rejected by the checker until the example was fixed (commit `0c5464c`).
- **Plausible but invented filters.** The Ask feature asked the model for a timing status that no stored item carries, and the answer to "promoters with cash in hand above 50 crore" came back empty (fixed in `9c3540c`: statuses are now validated).
- **Summaries that drop the caveat.** An AI-written audit summary said a row-binding fix "recovers about 19 holdings" and left out its own note that this does not prove the column is right. It also miscounted 199 verified quotes as 185. A second pass caught both. **Lesson: AI checks AI only when the second pass re-derives from the source, not from the first pass's text.**

## 6. With two more weeks, in this order

1. **Bind values to table cells** (row = name, column = header). This closes the wrong-column and Total-row risks, and reads lock-in dates from the printed tables. *(1 week)*
2. **Issuer guard and plausibility checks:** whose table is this; shares offered ≤ shares held; price inside the band and above face value; rows sum to the printed total. This blocks the Zetwerk class. *(2 days)*
3. **A second look for offer facts:** when the first quote fails, try the other places the same fact is printed (Vectras ₹105, FDC ₹500). *(2 days)*
4. **Grow the checked set from 20 to 100 people** and run it on every change from the cached model answers ($0). Any wrong number fails the build. *(2 days)*
5. **Default lock-in for holders with no printed role** (pre-offer capital rule, cited from the RHP). This fixes Panse-type rankings. *(1 day)*
6. **OCR for scanned buyback notices**, shown as a number only when a second read agrees. *(3 days)*
7. **KMP and named-ESOP extraction**, and director IDs (DIN) as a hard identity key across events. *(3 days)*
8. **Warm paths from the client book: "who already knows this lead?"** Word of mouth is the strongest way into a new
   relationship, so match every new lead against the firm's existing clients: shared boards and directorships (DIN across
   filings), co-investors in the same offer or round, the same promoter group or family, and earlier events they shared.
   The output is one line an RM can act on: *"Your client A sits on the board of B with this seller."* The client book stays
   inside the firm; only names and public filing links are compared. *(4 days)*
9. **On-demand deep research on one person, to help an RM double down on a lead or an existing client.** This means more
   public context before an important meeting: other directorships, earlier liquidity events, news, public professional
   profile, philanthropy. It is powerful, and it sits close to the line, so **it needs a conversation with compliance
   before it is built**: what counts as a legitimate purpose, what may be kept and for how long, consent where India's
   DPDP Act requires it, never personal contact details, a log of who researched whom and why, and a way for a person to be
   removed. The first version would be on request only, per person, with the cost and the sources shown. *(1 week, after the
   compliance discussion)*
