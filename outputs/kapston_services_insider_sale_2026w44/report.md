# Call list: KAPSTON SERVICES LIMITED (insider_sale)

## Event
- Event id: kapston_services_insider_sale_2026w44
- Type: insider_sale
- Company: KAPSTON SERVICES LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html): NSE | KAPSTON | SRIKANTH KODALI | SELL | 1,00,000 shares | value 49949700 | Market Sale | 2026-10-29
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 29 Oct 2026; sale date parsed: 2026-10-29; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 1,00,000 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | SRIKANTH KODALI | Promoter | sold 1,00,000 shares (Market Sale) on 29 Oct 2026 | ₹4.99 crore ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html)) | settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago) | high |

## Briefs

### 1. SRIKANTH KODALI
> SRIKANTH KODALI, a Promoter, is receiving money from selling 1,00,000 shares in a market sale.
> Proceeds of ₹4.99 crore arrived settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago), a sale that happened 17 days ago.
> Ask whether they plan to reinvest the proceeds, since the sale settled 17 days ago and funds are now available.

- Brief source: llm
- Proceeds: ₹4.99 crore; working: 1,00,000 shares, value as printed ₹4.99 crore (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html)
- Proceeds timing: settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago) ([trade_date XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html))
- Confidence: high (named in the exchange insider-trading disclosure (structured record, read by code); full name printed)
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash in hand: ₹4.99 crore; settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago).; score 4.99 = ₹4.99 crore (proceeds settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago)) × 1.0 (high confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_16041_20261030_155622867_WEB.html)

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

- Run: auto-kapston_services_insider_sale_2026w44-20261115T185533Z
- Model calls: 2 (0 cached)
- Cost this run: $0.000377; with no cache: $0.000377
- Tokens: 2602 in, 234 out
- Wall time: 3.7 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| SRIKANTH KODALI | 0.000377 | 0.000377 | 2.0 |
