# Call list: Axis Bank Limited (insider_sale)

## Event
- Event id: axis_bank_insider_sale_2026w46
- Type: insider_sale
- Company: Axis Bank Limited
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html): NSE | AXISBANK | Monish Saraf | SELL | 2,000 shares | value 2684340 | Market Sale | 2026-11-11
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 11 Nov 2026; sale date parsed: 2026-11-11; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 2,000 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Monish Saraf | unknown | sold 2,000 shares (Market Sale) on 11 Nov 2026 | ₹26.84 lakh ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html)) | settled 12 Nov 2026, T+1 after the 11 Nov 2026 trade (4 days ago) | high |

## Briefs

### 1. Monish Saraf
> Monish Saraf is a holder whose role is unknown, receiving money from a market sale of shares.
> Proceeds of ₹26.84 lakh from 2,000 shares were settled 12 Nov 2026, T+1 after the 11 Nov 2026 trade (4 days ago), so the money is already in hand.
> Open by asking how they plan to deploy the ₹26.84 lakh they have received.
> Confirm their position and relationship before discussing next steps, since the role is unknown.

- Brief source: llm
- Proceeds: ₹26.84 lakh; working: 2,000 shares, value as printed ₹26.84 lakh (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html)
- Proceeds timing: settled 12 Nov 2026, T+1 after the 11 Nov 2026 trade (4 days ago) ([trade_date XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html))
- Confidence: high (named in the exchange insider-trading disclosure (structured record, read by code); full name printed)
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash in hand: ₹26.84 lakh; settled 12 Nov 2026, T+1 after the 11 Nov 2026 trade (4 days ago).; score 0.27 = ₹0.27 crore (proceeds settled 12 Nov 2026, T+1 after the 11 Nov 2026 trade (4 days ago)) × 1.0 (high confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_1693_20261112_185051730_WEB.html)

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

- Run: auto-axis_bank_insider_sale_2026w46-20261115T190207Z
- Model calls: 2 (0 cached)
- Cost this run: $0.000393; with no cache: $0.000393
- Tokens: 2592 in, 267 out
- Wall time: 3.4 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Monish Saraf | 0.000393 | 0.000393 | 2.0 |
