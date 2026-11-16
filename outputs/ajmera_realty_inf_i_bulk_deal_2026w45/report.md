# Call list: Ajmera Realty & Inf I Ltd (block_deal)

## Event
- Event id: ajmera_realty_inf_i_bulk_deal_2026w45
- Type: block_deal
- Company: Ajmera Realty & Inf I Ltd
- Documents: none (built from exchange records)
- Exchange records: 3 used from outputs/signals/deals.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_block_deals: status: ok; note: 31 rows read, 31 in the window; records: 29; http status: unknown; url: https://www.bseindia.com/markets/equity/EQReports/block_deals.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source bse_bulk_deals: status: ok; note: 51 rows read, 51 in the window; records: 51; http status: unknown; url: https://www.bseindia.com/markets/equity/EQReports/bulk_deals.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_block_deals: status: ok; note: 92 rows read; records: 87; http status: unknown; url: https://www.nseindia.in/report-detail/display-bulk-and-block-deals; terms url: https://www.nseindia.in/nse-terms-of-use
  - source nse_bulk_deals: status: ok; note: 1250 rows read; NSE returned its 70-row maximum for 2026-10-19, 2026-10-21, 2026-10-22, 2026-10-23, 2026-10-26, 2026-10-27, 2026-10-29, 2026-10-30, 2026-11-02, 2026-11-03, 2026-11-04, 2026-11-05, 2026-11-06, 2026-11-09, 2026-11-11, 2026-11-12, 2026-11-13: those lists may be cut (the archive file has the full latest day); records: 1249; http status: unknown; url: https://www.nseindia.in/report-detail/display-bulk-and-block-deals; terms url: https://www.nseindia.in/nse-terms-of-use
  - source nse_deals_archive: status: ok; note: bulk.csv: 136 rows, 136 in the window; block.csv: 26 rows, 26 in the window; records: 162; http status: unknown; url: https://www.nseindia.in/all-reports; terms url: https://www.nseindia.in/nse-terms-of-use
  - [04-NOV-2026 · AJMERA · CELLO PENS AND STATIONERY PRIVATE LIMITED · BUY · 2500000](https://www.nseindia.in/report-detail/display-bulk-and-block-deals): NSE | AJMERA | CELLO PENS AND STATIONERY PRIVATE LIMITED | BUY | 25,00,000 shares | price 141 | 2026-11-04
  - [04-NOV-2026 · AJMERA · GOPANI JIGNESH GUNVANT · BUY · 1440000](https://www.nseindia.in/report-detail/display-bulk-and-block-deals): NSE | AJMERA | GOPANI JIGNESH GUNVANT | BUY | 14,40,000 shares | price 139.56 | 2026-11-04
  - [04-NOV-2026 · AJMERA · VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED · SELL · 2500000](https://www.nseindia.in/report-detail/display-bulk-and-block-deals): NSE | AJMERA | VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED | SELL | 25,00,000 shares | price 141 | 2026-11-04
- Price basis: trade_price ₹141 ([trade_price 04-NOV-2026 · AJMERA · VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED · SELL · 2500000](https://www.nseindia.in/report-detail/display-bulk-and-block-deals))
- Sale: sale date: 4 Nov 2026; sale date parsed: 2026-11-04; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 25,00,000 shares sold by 1 seller(s)

## Ranked people

None.

## Briefs

## Entities (not called directly)

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED | unknown | sold 25,00,000 shares in a bulk deal on 4 Nov 2026 | ₹35.25 crore ([shares_sold 04-NOV-2026 · AJMERA · VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED · SELL · 2500000](https://www.nseindia.in/report-detail/display-bulk-and-block-deals), [trade_price 04-NOV-2026 · AJMERA · VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED · SELL · 2500000](https://www.nseindia.in/report-detail/display-bulk-and-block-deals)) | settled 5 Nov 2026, T+1 after the 4 Nov 2026 trade (11 days ago) | high |

## No money from this event (context, not called)

| Name | Role | Why no money |
| --- | --- | --- |
| CELLO PENS AND STATIONERY PRIVATE LIMITED | unknown | Bought shares: buying is not coming into money, so listed for context, not to call. |
| GOPANI JIGNESH GUNVANT | unknown | Bought shares: buying is not coming into money, so listed for context, not to call. |

## Follow-on: also seen in other processed events

| Person | Other event | Company | Role there | Amount there | Strength |
| --- | --- | --- | --- | --- | --- |
| CELLO PENS AND STATIONERY PRIVATE LIMITED | ajmera_realty_inf_i_block_deal_2026w45 | Ajmera Realty & Inf I Ltd | unknown | not applicable: bought shares; buying is not coming into money | likely same holder |
| VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED | ajmera_realty_inf_i_block_deal_2026w45 | Ajmera Realty & Inf I Ltd | unknown | ₹35.25 crore | likely same holder |

Index lookups: 3; matches: 2.
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

- Run: unknown
- Model calls: 0 (0 cached)
- Cost this run: $0.000000; with no cache: $0.000000
- Tokens: 0 in, 0 out
- Wall time: 0.1 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| CELLO PENS AND STATIONERY PRIVATE LIMITED | 0.000000 | 0.000000 | 0.0 |
| GOPANI JIGNESH GUNVANT | 0.000000 | 0.000000 | 0.0 |
| VALUEQUEST INVESTMENT ADVISORS PRIVATE LIMITED | 0.000000 | 0.000000 | 0.0 |
