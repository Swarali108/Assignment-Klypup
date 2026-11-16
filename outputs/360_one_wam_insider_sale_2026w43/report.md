# Call list: 360 ONE WAM LIMITED (insider_sale)

## Event
- Event id: 360_one_wam_insider_sale_2026w43
- Type: insider_sale
- Company: 360 ONE WAM LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html): NSE | 360ONE | Guarav Doshi | SELL | 1,200 shares | value 1226292 | Market Sale | 2026-10-23
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 23 Oct 2026; sale date parsed: 2026-10-23; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 1,200 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Guarav Doshi | unknown | sold 1,200 shares (Market Sale) on 23 Oct 2026 | ₹12.26 lakh ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html)) | settled 26 Oct 2026, T+1 after the 23 Oct 2026 trade (21 days ago) | high |

## Briefs

### 1. Guarav Doshi
> Guarav Doshi is a holder whose role is unknown, receiving money from a share sale.
> They sold 1,200 shares and ₹12.26 lakh settled 21 days ago, so this money has already arrived.
> Confirm their role and ask whether the sale changes their overall holdings plan.
> Role is unknown, so confirm it before the call.

- Brief source: llm
- Proceeds: ₹12.26 lakh; working: 1,200 shares, value as printed ₹12.26 lakh (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html)
- Proceeds timing: settled 26 Oct 2026, T+1 after the 23 Oct 2026 trade (21 days ago) ([trade_date XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html))
- Confidence: high (named in the exchange insider-trading disclosure (structured record, read by code); full name printed)
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash in hand: ₹12.26 lakh; settled 26 Oct 2026, T+1 after the 23 Oct 2026 trade (21 days ago).; score 0.12 = ₹0.12 crore (proceeds settled 26 Oct 2026, T+1 after the 23 Oct 2026 trade (21 days ago)) × 1.0 (high confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_17593_20261027_180313775_WEB.html)

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

- Run: auto-360_one_wam_insider_sale_2026w43-20261115T185212Z
- Model calls: 2 (0 cached)
- Cost this run: $0.000376; with no cache: $0.000376
- Tokens: 2574 in, 238 out
- Wall time: 4.6 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Guarav Doshi | 0.000376 | 0.000376 | 2.0 |
