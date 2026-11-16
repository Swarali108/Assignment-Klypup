# Call list: LUX INDUSTRIES LIMITED (insider_sale)

## Event
- Event id: lux_industries_insider_sale_2026w46
- Type: insider_sale
- Company: LUX INDUSTRIES LIMITED
- Documents: none (built from exchange records)
- Exchange records: 1 used from outputs/signals/insider.json (refreshed 2026-11-15T18:48:41+00:00)
  - source bse_insider: status: ok; note: 125 disclosures read, 38 equity sales for cash kept; 25 also filed on NSE, kept once as the NSE record; records: 11; http status: unknown; url: https://www.bseindia.com/corporates/Insider_Trading_new.aspx; terms url: https://www.bseindia.com/rgess/disclaimer.htm
  - source nse_insider: status: ok; note: 301 filings, 60 XBRL files downloaded, 177 sales, 396 buys, pledges, gifts, inter-se transfers and others skipped; 9 filings wait for the next run (at most 60 downloads per run); records: 167; http status: unknown; url: https://www.nseindia.in/companies-listing/corporate-filings-insider-trading; terms url: https://www.nseindia.in/nse-terms-of-use
  - [XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html): NSE | LUXIND | PRADIP KUMAR TODI HUF | SELL | 13,340 shares | value 15662494 | Others | 2026-11-12
- Price basis: unknown (the records print no trade price)
- Sale: sale date: 12 Nov 2026; sale date parsed: 2026-11-12; settlement: T+1 equity cash-market settlement; exchange holidays not checked; total shares offered: 13,340 shares sold by 1 seller(s)

## Ranked people

| Rank | Name | Role | Why money | Amount | Timing | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | PRADIP KUMAR TODI HUF | Promoter group | sold 13,340 shares (Others) on 12 Nov 2026 | ₹1.57 crore ([shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html)) | unknown: mode of sale not printed as a market sale (Others), so the settlement date is not known | low |

## Briefs

### 1. PRADIP KUMAR TODI HUF
> PRADIP KUMAR TODI HUF is a promoter group holder, and proceeds from their share sale are coming to them.
> They sold 13,340 shares for ₹1.57 crore, with timing not known yet.
> Recent sale, 4 days ago; the sale was recorded as Others, so settlement date is unclear.
> Timing is unknown because the sale was not printed as a market sale.

- Brief source: llm
- Proceeds: ₹1.57 crore; working: 13,340 shares, value as printed ₹1.57 crore (NSE XBRL context Disclosure1); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html)
- Proceeds timing: unknown (mode of sale not printed as a market sale (Others), so the settlement date is not known)
- Confidence: low (mode unsure: not printed as a market or off-market sale (Others); confirm it was for cash; named in the exchange insider-trading disclosure (structured record, read by code))
- Family: none found
- Also seen in: none found in processed events
- Rank reasons: Cash due, date not confirmed: ₹1.57 crore; unknown: mode of sale not printed as a market sale (Others), so the settlement date is not known.; score 0.16 = ₹1.57 crore (proceeds, timing unknown) × 0.4 (low confidence) × 0.25 (timing unknown) × 1.0 (recency); evidence: [shares_sold XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html), [trade_value XBRL context Disclosure1](https://nsearchives.nseindia.in/corporate/ixbrl/IT_13245_20261113_125326334_WEB.html)

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

- Run: auto-lux_industries_insider_sale_2026w46-20261115T190321Z
- Model calls: 1 (0 cached)
- Cost this run: $0.000181; with no cache: $0.000181
- Tokens: 1187 in, 124 out
- Wall time: 2.5 s

| Person | Cost this run (USD) | With no cache (USD) | Calls |
| --- | --- | --- | --- |
| PRADIP KUMAR TODI HUF | 0.000181 | 0.000181 | 1.0 |
