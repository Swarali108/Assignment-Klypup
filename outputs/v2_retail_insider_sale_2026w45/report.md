# Call list: V2 RETAIL LIMITED (insider_sale)

## Event
- Event id: v2_retail_insider_sale_2026w45
- Type: insider_sale
- Company: V2 RETAIL LIMITED
- Documents: none (built from exchange records)
- Exchange records: 2 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html): NSE | V2RETAIL | Ram Chandra Agarwal | SELL | 62,60,000 shares | value 1001600000 | Block Deal | 2026-11-06
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115756309_WEB.html): NSE | V2RETAIL | Ricon Commodities Private Limited | SELL | 98,65,000 shares | value 1578400000 | Block Deal | 2026-11-06
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 6 Nov 2026; sale date parsed: 2026-11-06; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 1,61,25,000 shares sold by 2 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Ram Chandra Agarwal | Promoter | sold 62,60,000 shares (Block Deal) on 6 Nov 2026 | ₹100.16 crore ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html)) | unknown: mode of sale not printed as a market sale (Block Deal), so the settlement date is not known | low |

## Briefs

### 1. Ram Chandra Agarwal
> Ram Chandra Agarwal, Promoter, is receiving proceeds from a block sale of 62,60,000 shares made 10 days ago.
> Proceeds total ₹100.16 crore; the settlement date is not known, since the sale was not printed as a market sale.
> Ask whether they plan to redeploy the proceeds, since the holder's remaining stake and next steps may shape the conversation.
> Timing is unknown because the sale is printed as a Block Deal, so the settlement date cannot be confirmed.

- Brief source: llm
- Proceeds: ₹100.16 crore; working: 62,60,000 shares, value as printed ₹100.16 crore (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html)
- Proceeds timing: unknown (mode of sale not printed as a market sale (Block Deal), so the settlement date is not known)
- Confidence: low (mode unsure: not printed as a market or off-market sale (Block Deal); confirm it was for cash; named in the exchange insider-trading disclosure (structured record, read by code))
- Family: none found
- Also seen in: v2_retail_block_deal_2026w45 (V2 Retail Limited): role unknown, ₹100.16 crore [likely same holder]
- Rank reasons: Cash due, date not confirmed: ₹100.16 crore; unknown: mode of sale not printed as a market sale (Block Deal), so the settlement date is not known.; score 10.02 = ₹100.16 crore (proceeds, timing unknown) × 0.4 (low confidence) × 0.25 (timing unknown) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115841252_WEB.html)

## Entities (not called directly)

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Ricon Commodities Private Limited | Promoter group | sold 98,65,000 shares (Block Deal) on 6 Nov 2026 | ₹157.84 crore ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115756309_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2621_20261106_115756309_WEB.html)) | unknown: mode of sale not printed as a market sale (Block Deal), so the settlement date is not known | low |

## No money from this event (context, not called)

None.

## Follow-on: also seen in other processed events

| Person | Other event | Company | Role there | Amount there | Strength |
| --- | --- | --- | --- | --- | --- |
| Ram Chandra Agarwal | v2_retail_block_deal_2026w45 | V2 Retail Limited | unknown | ₹100.16 crore | likely same holder |
| Ricon Commodities Private Limited | v2_retail_block_deal_2026w45 | V2 Retail Limited | unknown | ₹157.84 crore | likely same holder |

Index lookups: 2; matches: 2.
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

- Run: auto-v2_retail_insider_sale_2026w45-20261115T190106Z
- Model calls: 1 (0 cached)
- Cost this run: $0.000208; with no cache: $0.000208
- Tokens: 1195 in, 176 out
- Wall time: 2.1 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Ram Chandra Agarwal | 0.000208 | 0.000208 | 1.0 |
| Ricon Commodities Private Limited | 0.000000 | 0.000000 | 0.0 |
