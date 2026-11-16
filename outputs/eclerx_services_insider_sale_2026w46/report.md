# Call list: eClerx Services Ltd (insider_sale)

## Event
- Event id: eclerx_services_insider_sale_2026w46
- Type: insider_sale
- Company: eClerx Services Ltd
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html): NSE | ECLERX | Eclerx Employee Welfare | SELL | 11,059 shares | value 17152813 | Market Sale | 2026-11-09
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 9 Nov 2026; sale date parsed: 2026-11-09; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 11,059 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Eclerx Employee Welfare | unknown | sold 11,059 shares (Market Sale) on 9 Nov 2026 | ₹1.72 crore ([shares_sold XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html), [trade_value XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html)) | settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago) | high |

## Briefs

### 1. Eclerx Employee Welfare
> Eclerx Employee Welfare is an unknown-role holder receiving money from a recent share sale.
> ₹1.72 crore arrived, settled settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago), from 11,059 shares sold in the market.
> The sale was 6 days ago, so the conversation can focus on how they plan to use these proceeds.
> Role is unknown; confirm it before the call.

- Brief source: llm
- Proceeds: ₹1.72 crore; working: 11,059 shares, value as printed ₹1.72 crore (NSE XBRL context Disclosure2); evidence: [shares_sold XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html), [trade_value XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html)
- Proceeds timing: settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago) ([trade_date XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html))
- Confidence: high (named in the exchange insider-trading disclosure (structured record, read by code); full name printed)
- Family: none found
- Also seen in: eclerx_services_insider_sale_2026w43 (eClerx Services Ltd): role unknown, ₹25.31 lakh [likely same holder]
- Rank reasons: Cash in hand: ₹1.72 crore; settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago).; score 1.72 = ₹1.72 crore (proceeds settled 10 Nov 2026, T+1 after the 9 Nov 2026 trade (6 days ago)) × 1.0 (high confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html), [trade_value XBRL context Disclosure2](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261111_165102806_WEB.html)

## Entities (not called directly)

None.

## No money from this event (context, not called)

None.

## Follow-on: also seen in other processed events

| Person | Other event | Company | Role there | Amount there | Strength |
| --- | --- | --- | --- | --- | --- |
| Eclerx Employee Welfare | eclerx_services_insider_sale_2026w43 | eClerx Services Ltd | unknown | ₹25.31 lakh | likely same holder |

Index lookups: 1; matches: 1.
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

- Run: auto-eclerx_services_insider_sale_2026w46-20261115T190131Z
- Model calls: 1 (0 cached)
- Cost this run: $0.000177; with no cache: $0.000177
- Tokens: 1184 in, 117 out
- Wall time: 2.5 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Eclerx Employee Welfare | 0.000177 | 0.000177 | 1.0 |
