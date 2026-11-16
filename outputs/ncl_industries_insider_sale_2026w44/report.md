# Call list: NCL INDUSTRIES LIMITED (insider_sale)

## Event
- Event id: ncl_industries_insider_sale_2026w44
- Type: insider_sale
- Company: NCL INDUSTRIES LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2568_20261028_143732664_WEB.html): NSE | NCLIND | Vinodrai V Goradia | SELL | 3,09,034 shares | value 0 | Others | 2026-10-26
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 26 Oct 2026; sale date parsed: 2026-10-26; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 3,09,034 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Vinodrai V Goradia | Promoter | sold 3,09,034 shares (Others) on 26 Oct 2026 | unknown: NSE XBRL context Disclosure1 prints neither a trade value nor a price | unknown: mode of sale not printed as a market sale (Others), so the settlement date is not known | low |

## Briefs

### 1. Vinodrai V Goradia
> Vinodrai V Goradia is a Promoter who sold 3,09,034 shares via an Others transaction, so money is coming to them.
> The amount is unknown and the settlement timing is unknown, since the sale was not printed as a market sale.
> The sale happened 21 days ago, so the proceeds may already be settled; confirm the timing before discussing it.
> Caveat: neither the trade value nor the settlement date is printed in the filing, so both remain unknown.

- Brief source: llm
- Proceeds: unknown (NSE XBRL context Disclosure1 prints neither a trade value nor a price)
- Proceeds timing: unknown (mode of sale not printed as a market sale (Others), so the settlement date is not known)
- Confidence: low (mode unsure: not printed as a market or off-market sale (Others); confirm it was for cash; named in the exchange insider-trading disclosure (structured record, read by code))
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash due, date not confirmed: receives cash from this event, but the amount is not disclosed, so they come after holders with a known amount.; score 0.00 = ₹0 crore (proceeds, timing unknown) × 0.4 (low confidence) × 0.25 (timing unknown) × 1.0 (recency)

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

- Run: auto-reprocess-ncl
- Model calls: 1 (0 cached)
- Cost this run: $0.000202; with no cache: $0.000202
- Tokens: 1261 in, 152 out
- Wall time: 2.2 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Vinodrai V Goradia | 0.000202 | 0.000202 | 1.0 |
