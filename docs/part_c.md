# Part C: Win the client

**Client:** a mid-sized Indian wealth firm, about 40 RMs. **Their problem, in their words:** *"My RMs hear about IPO money a month late, after a competitor has already called."*

## 1. First meeting: ten questions for the Head of RMs

Every question is here because one of its answers would change what I build.

| # | Question | If they answer… | …the design changes like this |
| --- | --- | --- | --- |
| 1 | When an RM hears about an IPO today, where from, and how many days after? | "Word of mouth, within a week" | Day-of-IPO alerts add little. Lead with the **unlock calendar** (lock-ins ending 6–18 months later), which word of mouth misses |
| 2 | Below what amount is a call not worth an RM's time? | "₹25 Cr or more of liquid money" | A firm-wide **minimum ticket** filter on Today. Small SME IPOs drop out of the default view |
| 3 | Do RMs pitch on cash received only, or also on shares that just became sellable? | "Cash only" | "Just unlocked" moves from the call list to a watch list, and the ranking weights change |
| 4 | Which money events matter most to your book: IPOs, buybacks, promoter sales, acquisitions, ESOP buybacks? | "Promoter block sales and acquisitions" | Takeover open offers become the next event type, and a **licensed exchange feed** moves up the plan, because exchange sites can't be read automatically |
| 5 | Where do RMs live all day: which CRM, WhatsApp, email? | "Our CRM, and nothing else gets opened" | Ship a **Monday push into the CRM** (export exists today) plus an email digest. The app becomes the evidence viewer behind each lead |
| 6 | Can we check names against your client book, and where may that list be stored? | "Yes, but only on our servers" | Matching runs inside the firm's environment. Existing clients are flagged "in your book" or hidden |
| 7 | How are leads assigned: by region, by RM, by who knows the family? | "Whoever has a relationship with the family" | Group by **household** and route a lead to the RM who already covers any member, so two RMs never call one family |
| 8 | What has compliance already approved for prospecting calls? | "Only warm introductions" | The product leads with **relationship paths** (shared directors, co-investors) instead of cold-call lists |
| 9 | If a figure can't be confirmed, should the RM see "unknown", or a best estimate marked as such? | "Show the estimate" | Unconfirmed values appear as *"printed on p. N, not yet tied to this person"* rather than being hidden |
| 10 | After four weeks, what result would make you roll this out to all 40 RMs? | "Two new mandates" | That becomes the pilot's success line, and we size the pilot group so it can be reached |

## 2. The five-minute demo

**Open with their sentence, not the product:** *"You said your RMs hear a month late. Here is this morning."*

| Time | Show | Say |
| --- | --- | --- |
| 0:00 | **Today**, signed in as an RM: the day's list, grouped as cash in hand → just unlocked → holds shares | "Who to call today, most actionable money first. Not the richest people: the ones whose money moved." |
| 0:45 | Open **Dr. Dharminder Kumar Nagar**, Paras Healthcare IPO: **₹300.00 Cr**, cash in hand | "4,329,004 shares sold × ₹693 offer price. The working is printed on the card. The machine never does arithmetic in its head." |
| **1:30** | **The moment: click the ₹ figure.** The prospectus opens at page 1, with *"aggregating to ₹3,000.00 million"* highlighted | "Every number your RM says on a call, they can show on the filing. If we can't show it, we write *unknown*." |
| 2:30 | The 3-line call brief, then "Log the call": Called / Follow up / Not now | "Two minutes of preparation, one click to record the outcome. That record is how we will measure the pilot." |
| 3:30 | **Chat → "Process this link" (or Events, as admin)**: six steps stream, and the run costs cents, not dollars | "A new IPO this morning is on your list before your competitor's RM has read the news." |
| 4:30 | Ask: *"What money does Manish Sharma have?"* | Then stop, and ask them question 10. |

**The pilot-winning moment is 1:30.** A Head of RMs has usually been burned by a data vendor before. The highlighted line on the printed page answers *"can I trust this figure?"* before they ask it.

## 3. The four-week pilot

- **Ship:** Today's list, the person card with evidence, call logging, and a Monday CRM export. Coverage: IPOs, promoter sales through the exchange, and tender-offer buybacks.
- **Who:** **8 RMs** using it, against a **control group of 8** with similar books and regions, working as they do today. That leaves 24 RMs untouched.
- **Weekly rhythm:** Monday, the list lands in the CRM. Friday, a 20-minute review with the Head of RMs: what was called, what was wrong, what to change. Fixes ship the following Monday.

| What we count (pilot vs control) | Why it's the right measure |
| --- | --- |
| **Calls booked** with people on the list | Did the list create action? |
| **Meetings held** | Did the action reach a conversation? |
| **New money in** (₹, mandates opened) within the pilot and 60 days after | The outcome the firm is paid for |
| Days from the money event to the first call | The "month late" problem, measured directly |
| Wrong figures reported by RMs (target: **0**) | Trust is the precondition for all of the above |

**We need from them:** 8 named RMs and one sponsor; the client book (names only) for suppression; their CRM's import format; compliance sign-off on the call approach; 20 minutes every Friday.

**What could stop it:** compliance won't approve (so we start that conversation in week 0); RMs don't log calls, so nothing can be measured (logging is one click, and the Friday review checks it); a quiet IPO month (unlocks and buybacks fill the list); one wrong number, shown to a client, that destroys trust (every figure is sourced, and a reported error is fixed within the week).

## 4. The pushback: "Is it legal for us to research people like this and call them?"

> *Not legal advice; this is the answer I would give, and then confirm with counsel.*
>
> **Very likely yes, for the research; and calling follows the rules you already apply to any prospect.** Everything we use is published because the law requires it: offer documents, buyback letters and exchange notices are filed under SEBI regulations, and they name these people with their holdings and sale amounts. India's Digital Personal Data Protection Act, 2023 does not apply to personal data that someone was **legally obliged to make public** (section 3(c)(ii)), and a filed prospectus is exactly that. We collect **no** phone numbers, personal emails or home addresses: only public roles, holdings and transactions. The RM reaches the person through the firm's normal channels, under its own marketing, KYC and Do-Not-Disturb rules. One caution: unlike Europe's GDPR, the DPDP Act has no general "legitimate interest" ground. If the exemption did not cover our use, we would need consent or one of the Act's narrow "legitimate uses". That is why I would check the first item below before saying any of this for real.

**What I would check first:**
1. With counsel: does the section 3(c)(ii) exemption still cover data once it is **compiled into a profile**? Which DPDP provisions are in force on the pilot date?
2. TRAI's telemarketing rules and the national Do-Not-Disturb registry, for any call or SMS to a number the firm holds.
3. The SEBI rules for the firm's own licence (investment adviser, portfolio manager or distributor) on solicitation, advertising and record-keeping.
4. The firm's own marketing and data-retention policies, and where its client book may be processed.
5. Each source's terms of use. SEBI allows linking. NSE and BSE forbid automated collection, so we don't do it.
6. Where the model provider processes these names, and its data-retention terms.
