# Signals v2: every source, a live scheduler, auto-processing under a cap (design addendum, 2026-11-16)

## Owner rulings
- **Read NSE and BSE too**, although their terms forbid automated collection and the assignment brief says not to scrape
  where terms forbid it. Owner's call, recorded in decision_log.md and on the Sources page.
- **Auto-process new signals under a daily spend cap** (default $1.00/day, `AUTO_PROCESS_DAILY_CAP_USD`); above it, items
  wait for an admin's confirm. Discovery runs every 3 hours while the API is up (`DISCOVERY_EVERY_HOURS`), plus
  "Check for new filings now" (admin, estimate + confirm).

## Guardrails on exchange reading (non-negotiable)
Polite client: ≥ 2 s between requests per host, cache every response (tools/fetch.py), fetch only what is new, an honest
User-Agent string naming the app, standard session cookies like a browser visit, **no proxies, no IP rotation, no CAPTCHA
solving, no header tricks beyond what a normal browser sends; on 401/403/429 back off and stop for that run**, and show the
source as "blocked" with the reason. One switch `EXCHANGE_SOURCES=on|off` (on locally). Production on cloud IPs will likely
be blocked by NSE; documented, not worked around.

## Coverage after v2
| Signal | Source | Becomes |
|---|---|---|
| IPO filed / final prospectus | SEBI (existing) + NSE/BSE IPO lists | ipo events |
| Basis of allotment / listing notice | NSE/BSE announcements | attached to the IPO event as `announcement` → confirms listing date and price |
| Offer for sale through the exchange | NSE/BSE OFS notices | ofs_stock_exchange events (existing rules) |
| Buyback | SEBI (existing) + exchange announcements | buyback events |
| Open offer / acquisition (Reg 30) | SEBI takeover list + exchange announcements | discovered + listed ("not processed yet") |
| Bulk and block deals | NSE/BSE deal reports (structured) | new `block_deal` events: seller, qty, price, value, date — no model needed |
| Promoter/insider sales (PIT / SAST disclosures) | NSE/BSE disclosures (structured) | new `insider_sale` events: name, category, qty, value, date — no model needed |
| Draft offer documents (early warning) | SEBI DRHP list | watchlist items ("IPO coming") |

Structured signals (deals, insider sales) skip the PDF pipeline: code builds people rows directly with the exchange record
as evidence (link + row), confidence by name match, timing = trade date + settlement. Entities stay out of the call list.

## Surfaces
- **Sources page** (admin): every source — on/off/blocked, why, terms link, risk label, last checked, items found, errors.
- **Events feed**: source badge per item (SEBI / NSE / BSE), new signal types, "Check now" with estimate + confirm.
- **Auto-processing log**: what ran automatically, its cost, today's spend vs the cap.
