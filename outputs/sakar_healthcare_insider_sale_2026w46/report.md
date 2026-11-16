# Call list: SAKAR HEALTHCARE LIMITED (insider_sale)

## Event
- Event id: sakar_healthcare_insider_sale_2026w46
- Type: insider_sale
- Company: SAKAR HEALTHCARE LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html): NSE | SAKAR | Rita S. Shah | SELL | 30,000 shares | value 31163400 | Market Sale | 2026-11-09
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 9 Nov 2026; sale date parsed: 2026-11-09; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 30,000 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Rita S. Shah | Promoter | sold 30,000 shares (Market Sale) on 9 Nov 2026 | ₹3.12 crore ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html)) | settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago) | medium |

## Briefs

### 1. Rita S. Shah
> Rita S. Shah, Promoter, received money after a Market Sale of 30,000 shares that settled settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago).
> Proceeds of ₹3.12 crore arrived 6 days ago, so the money is already in hand.
> Open with the completed sale and ask how they plan to deploy the ₹3.12 crore they now hold.

- Brief source: llm
- Proceeds: ₹3.12 crore; working: 30,000 shares, value as printed ₹3.12 crore (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html)
- Proceeds timing: settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago) ([trade_date XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html))
- Confidence: medium (named in the exchange insider-trading disclosure (structured record, read by code); name printed with initials (S); confirm the client before calling)
- Family: none found
- Also seen in: sakar_healthcare_insider_sale_2026w44 (SAKAR HEALTHCARE LIMITED): Promoter, ₹4.45 crore [likely same holder]; sakar_healthcare_insider_sale_2026w45 (SAKAR HEALTHCARE LIMITED): Promoter, ₹2.54 crore [likely same holder]
- Rank reasons: Cash in hand: ₹3.12 crore; settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago).; score 2.18 = ₹3.12 crore (proceeds settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago)) × 0.7 (medium confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_14283_20261110_230458936_WEB.html)

## Entities (not called directly)

None.

## No money from this event (context, not called)

None.

## Follow-on: also seen in other processed events

| Person | Other event | Company | Role there | Amount there | Strength |
| --- | --- | --- | --- | --- | --- |
| Rita S. Shah | sakar_healthcare_insider_sale_2026w44 | SAKAR HEALTHCARE LIMITED | Promoter | ₹4.45 crore | likely same holder |
| Rita S. Shah | sakar_healthcare_insider_sale_2026w45 | SAKAR HEALTHCARE LIMITED | Promoter | ₹2.54 crore | likely same holder |

Index lookups: 1; matches: 2.
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

- Run: auto-sakar_healthcare_insider_sale_2026w46-20261115T190144Z
- Model calls: 2 (0 cached)
- Cost this run: $0.000367; with no cache: $0.000367
- Tokens: 2565 in, 220 out
- Wall time: 3.5 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Rita S. Shah | 0.000367 | 0.000367 | 2.0 |
