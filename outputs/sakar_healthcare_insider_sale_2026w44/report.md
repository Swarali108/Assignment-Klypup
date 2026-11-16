# Call list: SAKAR HEALTHCARE LIMITED (insider_sale)

## Event
- Event id: sakar_healthcare_insider_sale_2026w44
- Type: insider_sale
- Company: SAKAR HEALTHCARE LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html): NSE | SAKAR | Rita S. Shah | SELL | 45,000 shares | value 44536958 | Market Sale | 2026-10-28
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 28 Oct 2026; sale date parsed: 2026-10-28; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 45,000 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Rita S. Shah | Promoter | sold 45,000 shares (Market Sale) on 28 Oct 2026 | ₹4.45 crore ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html)) | settled 29 Oct 2026, T+1 after the 28 Oct 2026 trade (18 days ago) | medium |

## Briefs

### 1. Rita S. Shah
> Rita S. Shah, Promoter, sold shares in a Market Sale, which is why money is coming to them.
> The ₹4.45 crore proceeds from 45,000 shares settled 18 days ago, so the money is already in hand.
> Ask how they plan to think about their remaining holding in light of this recent liquidity.

- Brief source: llm
- Proceeds: ₹4.45 crore; working: 45,000 shares, value as printed ₹4.45 crore (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html)
- Proceeds timing: settled 29 Oct 2026, T+1 after the 28 Oct 2026 trade (18 days ago) ([trade_date XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html))
- Confidence: medium (named in the exchange insider-trading disclosure (structured record, read by code); name printed with initials (S); confirm the client before calling)
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash in hand: ₹4.45 crore; settled 29 Oct 2026, T+1 after the 28 Oct 2026 trade (18 days ago).; score 3.12 = ₹4.45 crore (proceeds settled 29 Oct 2026, T+1 after the 28 Oct 2026 trade (18 days ago)) × 0.7 (medium confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261030_170021796_WEB.html)

## Entities (not called directly)

None.

## No money from this event (context, not called)

None.

## Follow-on: also seen in other processed events

No matches in other processed events.

Index lookups: 1; matches: 0.
Stop rules: only events already processed into outputs/index.json are searched; no web search and no new document fetch; at most 10 matches per person; one level deep: a match's own matches are not followed.

## What we didn't trust

### Holder table completeness (verified rows summed against the printed total)
- no table this event type checks

### Unattributed rows (name failed verification; their amounts are not used)
- none

### Rejected fields by section and reason
| Section | Reason | Count |
| --- | --- | --- |

### Identity decisions sent to the model
- none: every pair was settled by code

## Cost

- Run: auto-sakar_healthcare_insider_sale_2026w44-20261115T185415Z
- Model calls: 2 (0 cached)
- Cost this run: $0.000363; with no cache: $0.000363
- Tokens: 2557 in, 216 out
- Wall time: 3.5 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Rita S. Shah | 0.000363 | 0.000363 | 2.0 |
