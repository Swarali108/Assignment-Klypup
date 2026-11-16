# Call list: KARUR VYSYA BANK LIMITED (insider_sale)

## Event
- Event id: karur_vysya_bank_insider_sale_2026w44
- Type: insider_sale
- Company: KARUR VYSYA BANK LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html): NSE | KARURVYSYA | M V Usha | SELL | 1,500 shares | value 535446 | Market Sale | 2026-10-29
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 29 Oct 2026; sale date parsed: 2026-10-29; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 1,500 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | M V Usha | Promoter group | sold 1,500 shares (Market Sale) on 29 Oct 2026 | ₹5.35 lakh ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html)) | settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago) | medium |

## Briefs

### 1. M V Usha
> M V Usha is a Promoter group member who sold 1,500 shares on the market, bringing in money.
> Proceeds of ₹5.35 lakh settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago), reaching them as recent cash.
> Ask how they plan to deploy these proceeds given the recent settlement.

- Brief source: llm
- Proceeds: ₹5.35 lakh; working: 1,500 shares, value as printed ₹5.35 lakh (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html)
- Proceeds timing: settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago) ([trade_date XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html))
- Confidence: medium (named in the exchange insider-trading disclosure (structured record, read by code); name printed with initials (M V); confirm the client before calling)
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash in hand: ₹5.35 lakh; settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago).; score 0.04 = ₹0.05 crore (proceeds settled 30 Oct 2026, T+1 after the 29 Oct 2026 trade (17 days ago)) × 0.7 (medium confidence) × 1.0 (timing settles) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_539_20261030_184003864_WEB.html)

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

- Run: auto-karur_vysya_bank_insider_sale_2026w44-20261115T185537Z
- Model calls: 2 (0 cached)
- Cost this run: $0.000353; with no cache: $0.000353
- Tokens: 2550 in, 196 out
- Wall time: 3.6 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| M V Usha | 0.000353 | 0.000353 | 2.0 |
