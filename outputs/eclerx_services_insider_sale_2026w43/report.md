# Call list: eClerx Services Ltd (insider_sale)

## Event
- Event id: eclerx_services_insider_sale_2026w43
- Type: insider_sale
- Company: eClerx Services Ltd
- Documents: none (built from exchange records)
- Exchange records: 2 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html): NSE | ECLERX | Eclerx Employee Welfare | SELL | 3,565 shares | value 2530829 | Off Market | 2026-10-22
  - [Fld_ID 165398 · Eclerx Employee Welfare](https://www.bseindia.com/XBRLFILES/PITXBRLDataXML/PIT_532927_2310202618565_PIT.html): BSE | 532927 | Eclerx Employee Welfare | SELL | 3,565 shares | value 2530829.00 | Off Market | 2026-10-22
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 22 Oct 2026; sale date parsed: 2026-10-22; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 7,130 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Eclerx Employee Welfare | unknown | sold 3,565 shares (Off Market) on 22 Oct 2026 | ₹25.31 lakh ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html)) | unknown: off-market transfer (mode as printed: Off Market): paid between the parties, so there is no exchange settlement date | high |

## Briefs

### 1. Eclerx Employee Welfare
> Eclerx Employee Welfare is the holder, role unknown, receiving proceeds from selling 3,565 shares.
> They received ₹25.31 lakh from the sale, which happened 25 days ago.
> Recent off-market sale, so the relationship angle is what Eclerx Employee Welfare plans to do with the proceeds.
> Timing of the money is unknown because the transfer was off-market and settled between parties.

- Brief source: llm
- Proceeds: ₹25.31 lakh; working: 3,565 shares, value as printed ₹25.31 lakh (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html)
- Proceeds timing: unknown (off-market transfer (mode as printed: Off Market): paid between the parties, so there is no exchange settlement date)
- Confidence: high (named in the exchange insider-trading disclosure (structured record, read by code); full name printed)
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash due, date not confirmed: ₹25.31 lakh; unknown: off-market transfer (mode as printed: Off Market): paid between the parties, so there is no exchange settlement date.; score 0.06 = ₹0.25 crore (proceeds, timing unknown) × 1.0 (high confidence) × 0.25 (timing unknown) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_2698_20261023_185625040_WEB.html)

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

- Run: auto-eclerx_services_insider_sale_2026w43-20261115T185200Z
- Model calls: 1 (0 cached)
- Cost this run: $0.000184; with no cache: $0.000184
- Tokens: 1212 in, 125 out
- Wall time: 2.4 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| Eclerx Employee Welfare | 0.000184 | 0.000184 | 1.0 |
