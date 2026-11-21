# FinSight API contract

Base URL: `http://localhost:8000/api` (set `NEXT_PUBLIC_API_URL`). Start it with

```bash
.venv/bin/python -m uvicorn api.main:app --port 8000
```

Every example below is a **real response** captured from the service on the committed `outputs/`
(as of 15 Nov 2026). Long arrays are cut to 1 to 3 entries; nothing else is edited. The ask,
from-links, create and job examples were captured in-process (model stubbed, run.py replaced by a
stand-in that prints its progress lines), so no model or network call was made.

## Conventions (read once)

- **Money.** `value_cr` is a number in ₹ crore copied from a stored, verified figure, or
  `null` when unknown. **`null` is never zero**: show `display` ("Amount not disclosed",
  "Not tendering", "Value not disclosed") and `reason`. `display` is ready-made short text
  ("₹6.08 Cr"; under ₹10 lakh it is full rupees, "₹15,100", and `value_cr` then keeps 6 decimals,
  e.g. 0.00151; otherwise 2 dp). `detail` is the longer stored
  sentence ("Up to ₹6.08 crore, if all offered shares are sold"). `kind` is `"cash"` (money from
  a sale) or `"shares"` (value of shares still held, always `estimate: true`). Format numbers with
  `formatCr(value_cr)` if you need your own rendering; never print `value_cr` when it is null.
- **Tiers.** `tier` is `cash_now` > `unlock` > `holding`; `tier_label` is RM words
  ("Cash in hand", "Cash due soon", "Shares just unlocked", "Holds shares"). When the pipeline
  writes `call_tier` the API passes it through; otherwise it derives the tier from stored fields
  (computed/unknown proceeds with cash timing, or a scheduled listing in the past or within 30
  days → `cash_now`; an unlock in the last 120 days → `unlock`; else `holding`). Lists arrive
  already in call order: tier, known amount before unknown, then rank/score.
- **Timing.** `timing = {label, status, date_iso|null, past}`. `label` is the line to show.
  Status values seen: `in_hand`, `due_past` (listing date passed, listing notice not yet seen),
  `scheduled`, `after_date`, `unlocked`, `partly_unlocked`, `locked_in`, `not_applicable`, `unknown`.
- **Confidence.** `confidence = {level: high|medium|low, reason, reasons[]}`, separate from amount.
- **Evidence ref** (everywhere): `{doc_sha, doc_label, pdf_index, printed_page|null, quote, url,
  source_url, image_url, cached}`. `image_url` is the highlighted page PNG; `url` opens the PDF
  at the page (`#page=n`); `source_url` is the original public link. `cached: false` means the
  PDF is not on this machine (show the quote and the source link only).
- **Ids.** A call item's `id` is `"<event_id>/<person_id>"`; households are
  `"<event_id>:<family id>"`. Use `event.id` + `person.id` for the person page and the RM endpoints.
- **Errors** are `{"detail": "plain sentence"}` with 404 / 409 / 422.
- Text fields contain no file or field names; they are safe to show.

---

## GET /api/summary

KPIs for the Today header. `people_to_call` counts queue slots (households folded) whose RM status
is `to_call` or `follow_up`. `cash_now_cr` is the sum of known cash-now amounts.

```json
{
  "as_of": "2026-11-15",
  "as_of_display": "15 Nov 2026",
  "people_to_call": 89,
  "people_total": 101,
  "households": 89,
  "cash_now_cr": 2720.78,
  "cash_now_people": 52,
  "unlock_people": 6,
  "new_events_this_week": 14,
  "events_processed": 16,
  "events_total": 18,
  "called": 0
}
```

## GET /api/today?limit=

The cross-event call queue. One slot per person, or per household: the best-placed member is the
slot and the others are in `members` (each with its own tier and amount); `household_total_cr`
sums the members' known amounts of the same kind. `household` (on every item that belongs to one)
carries `label`, `reason` and all `members`. Example shows the first slot, a household slot and an
unknown-amount slot.

Repeat sales (16 Nov): one holder's cash sales at one company in several weeks (insider sales, block/bulk deals,
exchange offers for sale) are one slot, led by the newest sale (its `id`, amount, timing, `rm` and place in the
order). Such a slot adds `trades` (every sale, newest first: `{id, event, date_iso, date_display, amount, sources,
rm_status}`), `trades_total_cr` / `trades_total_display` (known cash together; under ₹10 lakh in rupees) and
`trades_unpriced`. A family slot (with `members`) is never folded. Each sale keeps its own row on its event page, in
`/api/calendar` and in the CSV export; a call logged on the slot is saved on the newest sale only. Before this, an
insider disclosure whose exchange lines (date, shares) wholly contain another sale's (a block deal reported on its
own) is merged into one item listing both `sources`, so the cash is counted once.

```json
{
  "as_of": "2026-11-15",
  "count": 89,
  "items": [
    {
      "id": "hd_fire_protect_limited_ipo_202610/p_kusum_harish_dharamshi",
      "event": {
        "id": "hd_fire_protect_limited_ipo_202610",
        "company": "HD Fire Protect Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_kusum_harish_dharamshi",
        "name": "KUSUM HARISH DHARAMSHI",
        "role": null,
        "holder_type": "person"
      },
      "tier": "cash_now",
      "tier_label": "Cash in hand",
      "amount": {
        "value_cr": 468.85,
        "low_cr": 468.85,
        "display": "₹468.85 Cr",
        "detail": "₹468.85 crore",
        "kind": "cash",
        "estimate": false,
        "reason": null,
        "source": "proceeds"
      },
      "timing": {
        "label": "Listing was due 21 Oct 2026 (25 days ago); listing notice not yet seen",
        "status": "due_past",
        "date_iso": "2026-10-21",
        "past": true
      },
      "confidence": {
        "level": "medium",
        "reason": "Name verified in the seller table; Holdings found in one section only (shareholding pattern)",
        "reasons": [
          "Name verified in the seller table",
          "Holdings found in one section only (shareholding pattern)"
        ]
      },
      "why": "Sells 17,300,800 shares in the offer for sale",
      "brief_first_line": "KUSUM HARISH DHARAMSHI, role unknown, is due proceeds from selling 17,300,800 shares in the offer for sale.",
      "household": {
        "id": "hd_fire_protect_limited_ipo_202610:family_2",
        "label": "Dharamshi household",
        "reason": "'KUSUM HARISH DHARAMSHI' and 'HARISH NARSHI DHARAMSHI' share surname 'dharamshi', and the middle name 'harish' of 'KUSUM HARISH DHARAMSHI' is the first name of 'HARISH NARSHI DHARAMSHI'",
        "members": [
          {
            "id": "hd_fire_protect_limited_ipo_202610/p_kusum_harish_dharamshi",
            "name": "KUSUM HARISH DHARAMSHI",
            "role": null,
            "tier": "cash_now",
            "amount": {
              "value_cr": 468.85,
              "low_cr": 468.85,
              "display": "₹468.85 Cr",
              "detail": "₹468.85 crore",
              "kind": "cash",
              "estimate": false,
              "reason": null,
              "source": "proceeds"
            }
          },
          {
            "id": "hd_fire_protect_limited_ipo_202610/p_harish_narshi_dharamshi",
            "name": "HARISH NARSHI DHARAMSHI",
            "role": null,
            "tier": "cash_now",
            "amount": {
              "value_cr": 243.46,
              "low_cr": 243.46,
              "display": "₹243.46 Cr",
              "detail": "₹243.46 crore",
              "kind": "cash",
              "estimate": false,
              "reason": null,
              "source": "proceeds"
            }
          }
        ],
        "printed_members": [
          "HARISH NARSHI DHARAMSHI",
          "KUSUM HARISH DHARAMSHI"
        ]
      },
      "household_id": "hd_fire_protect_limited_ipo_202610:family_2",
      "rank": 1,
      "score": 262.556,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "position": 1,
      "members": [
        {
          "id": "hd_fire_protect_limited_ipo_202610/p_harish_narshi_dharamshi",
          "name": "HARISH NARSHI DHARAMSHI",
          "role": null,
          "tier": "cash_now",
          "amount": {
            "value_cr": 243.46,
            "low_cr": 243.46,
            "display": "₹243.46 Cr",
            "detail": "₹243.46 crore",
            "kind": "cash",
            "estimate": false,
            "reason": null,
            "source": "proceeds"
          }
        }
      ],
      "household_total_cr": 712.31
    },
    {
      "id": "hd_fire_protect_limited_ipo_202610/p_kusum_harish_dharamshi",
      "event": {
        "id": "hd_fire_protect_limited_ipo_202610",
        "company": "HD Fire Protect Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_kusum_harish_dharamshi",
        "name": "KUSUM HARISH DHARAMSHI",
        "role": null,
        "holder_type": "person"
      },
      "tier": "cash_now",
      "tier_label": "Cash in hand",
      "amount": {
        "value_cr": 468.85,
        "low_cr": 468.85,
        "display": "₹468.85 Cr",
        "detail": "₹468.85 crore",
        "kind": "cash",
        "estimate": false,
        "reason": null,
        "source": "proceeds"
      },
      "timing": {
        "label": "Listing was due 21 Oct 2026 (25 days ago); listing notice not yet seen",
        "status": "due_past",
        "date_iso": "2026-10-21",
        "past": true
      },
      "confidence": {
        "level": "medium",
        "reason": "Name verified in the seller table; Holdings found in one section only (shareholding pattern)",
        "reasons": [
          "Name verified in the seller table",
          "Holdings found in one section only (shareholding pattern)"
        ]
      },
      "why": "Sells 17,300,800 shares in the offer for sale",
      "brief_first_line": "KUSUM HARISH DHARAMSHI, role unknown, is due proceeds from selling 17,300,800 shares in the offer for sale.",
      "household": {
        "id": "hd_fire_protect_limited_ipo_202610:family_2",
        "label": "Dharamshi household",
        "reason": "'KUSUM HARISH DHARAMSHI' and 'HARISH NARSHI DHARAMSHI' share surname 'dharamshi', and the middle name 'harish' of 'KUSUM HARISH DHARAMSHI' is the first name of 'HARISH NARSHI DHARAMSHI'",
        "members": [
          {
            "id": "hd_fire_protect_limited_ipo_202610/p_kusum_harish_dharamshi",
            "name": "KUSUM HARISH DHARAMSHI",
            "role": null,
            "tier": "cash_now",
            "amount": {
              "value_cr": 468.85,
              "low_cr": 468.85,
              "display": "₹468.85 Cr",
              "detail": "₹468.85 crore",
              "kind": "cash",
              "estimate": false,
              "reason": null,
              "source": "proceeds"
            }
          },
          {
            "id": "hd_fire_protect_limited_ipo_202610/p_harish_narshi_dharamshi",
            "name": "HARISH NARSHI DHARAMSHI",
            "role": null,
            "tier": "cash_now",
            "amount": {
              "value_cr": 243.46,
              "low_cr": 243.46,
              "display": "₹243.46 Cr",
              "detail": "₹243.46 crore",
              "kind": "cash",
              "estimate": false,
              "reason": null,
              "source": "proceeds"
            }
          }
        ],
        "printed_members": [
          "HARISH NARSHI DHARAMSHI",
          "KUSUM HARISH DHARAMSHI"
        ]
      },
      "household_id": "hd_fire_protect_limited_ipo_202610:family_2",
      "rank": 1,
      "score": 262.556,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "position": 1,
      "members": [
        {
          "id": "hd_fire_protect_limited_ipo_202610/p_harish_narshi_dharamshi",
          "name": "HARISH NARSHI DHARAMSHI",
          "role": null,
          "tier": "cash_now",
          "amount": {
            "value_cr": 243.46,
            "low_cr": 243.46,
            "display": "₹243.46 Cr",
            "detail": "₹243.46 crore",
            "kind": "cash",
            "estimate": false,
            "reason": null,
            "source": "proceeds"
          }
        }
      ],
      "household_total_cr": 712.31
    },
    {
      "id": "spacenet_ofs/p_lanka_divyabharathi",
      "event": {
        "id": "spacenet_ofs",
        "company": "String Metaverse Limited",
        "type": "ofs_stock_exchange",
        "type_label": "Offer for sale (exchange)"
      },
      "person": {
        "id": "p_lanka_divyabharathi",
        "name": "Lanka Divyabharathi",
        "role": "Promoter Group",
        "holder_type": "person"
      },
      "tier": "cash_now",
      "tier_label": "Cash in hand",
      "amount": {
        "value_cr": null,
        "low_cr": null,
        "display": "Amount not disclosed",
        "detail": null,
        "kind": "cash",
        "estimate": false,
        "reason": "The notice prints Up to 38,10,000 Equity Shares for all sellers together, not this seller's own shares",
        "source": "proceeds"
      },
      "timing": {
        "label": "Settles after the sale on 21 Apr 2026 (6 months ago)",
        "status": "after_date",
        "date_iso": "2026-04-21",
        "past": true
      },
      "confidence": {
        "level": "medium",
        "reason": "Name verified in the seller list in the notice; Found in one section only (sellers)",
        "reasons": [
          "Name verified in the seller list in the notice",
          "Found in one section only (sellers)"
        ]
      },
      "why": "Sells in the offer for sale through the stock exchange; own shares not printed",
      "brief_first_line": "Lanka Divyabharathi, Promoter Group, sells shares in the offer for sale through the stock exchange.",
      "household": null,
      "household_id": null,
      "rank": 1,
      "score": 0.0,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "position": 1,
      "members": [],
      "household_total_cr": null
    }
  ]
}
```

## GET /api/events

Every event file (hand-made and discovered). `status`: `ready | processing | failed | scanned |
not_supported | not_processed`, with `status_reason` in RM words. `docs[].scanned` is computed from the
parsed page text (80%+ of pages under 50 characters). `cash_cr` is `null` when no one has known
cash. `empty_reason` is set whenever `people_count` is 0. Example: first row, a scanned event and an
event with no individual to call.

```json
{
  "count": 18,
  "events": [
    {
      "id": "fdc_limited_buyback_202610",
      "company": "FDC Limited",
      "type": "buyback",
      "type_label": "Buyback",
      "status": "ready",
      "status_reason": "Call list ready",
      "people_count": 3,
      "entities_count": 0,
      "context_count": 0,
      "tier_counts": {
        "cash_now": 0,
        "unlock": 0,
        "holding": 3
      },
      "cash_cr": null,
      "listing_date": null,
      "money_date": {
        "kind": "unknown",
        "label": "Date not confirmed",
        "date_iso": null,
        "confirmed": false,
        "display": "",
        "relative": ""
      },
      "empty_reason": null,
      "docs": [
        {
          "doc_sha": "9060a2654afb7203286ef55e906a4aa7150011362168c9c11ee9ebea440d0fea",
          "label": "Public announcement",
          "doc_type": "public_announcement",
          "note": "FDC Limited",
          "source_url": "https://www.sebi.gov.in/sebi_data/commondocs/nov-2026/FDC%20Limited-PA_p.pdf",
          "url": "/api/docs/9060a2654afb7203286ef55e906a4aa7150011362168c9c11ee9ebea440d0fea.pdf",
          "pages": 3,
          "scanned": false,
          "scanned_label": null
        }
      ],
      "source": "discovered",
      "discovered_on": "2026-11-15"
    },
    {
      "id": "genus_power_infrastructure_limited_buyback_202610",
      "company": "Genus Power Infrastructure Limited",
      "type": "buyback",
      "type_label": "Buyback",
      "status": "scanned",
      "status_reason": "Scanned filing: text not readable yet",
      "people_count": 0,
      "entities_count": 0,
      "context_count": 0,
      "tier_counts": {
        "cash_now": 0,
        "unlock": 0,
        "holding": 0
      },
      "cash_cr": null,
      "listing_date": null,
      "money_date": {
        "kind": "unknown",
        "label": "Date not confirmed",
        "date_iso": null,
        "confirmed": false,
        "display": "",
        "relative": ""
      },
      "empty_reason": "Scanned filing: text not readable yet, so no names could be read from it.",
      "docs": [
        {
          "doc_sha": "a799b74e7271606ef2f990b1108068eb13fc074393a654a6aff126917c6baad0",
          "label": "Public announcement",
          "doc_type": "public_announcement",
          "note": "Genus Power Infrastructure Limited",
          "source_url": "https://www.sebi.gov.in/sebi_data/commondocs/oct-2026/Genus%20Power%20Infrastructure%20Limited-%20PA_p.pdf",
          "url": "/api/docs/a799b74e7271606ef2f990b1108068eb13fc074393a654a6aff126917c6baad0.pdf",
          "pages": 6,
          "scanned": true,
          "scanned_label": "Scanned filing: text not readable yet"
        }
      ],
      "source": "discovered",
      "discovered_on": "2026-11-15"
    },
    {
      "id": "jio_platforms_limited_ipo_202610",
      "company": "Jio Platforms Ltd",
      "type": "ipo",
      "type_label": "IPO",
      "status": "ready",
      "status_reason": "Call list ready",
      "people_count": 0,
      "entities_count": 1,
      "context_count": 0,
      "tier_counts": {
        "cash_now": 0,
        "unlock": 0,
        "holding": 0
      },
      "cash_cr": null,
      "listing_date": "2026-10-28",
      "money_date": {
        "kind": "listing",
        "label": "Listing due",
        "date_iso": "2026-10-28",
        "confirmed": false,
        "display": "28 Oct 2026",
        "relative": "18 days ago"
      },
      "empty_reason": "Every holder named is a company or fund (Reliance Industries Limited); there is no individual to call.",
      "docs": [
        {
          "doc_sha": "5a686ac4989df41c209dcf5bf3190a02070f7c6233dca46f4fa51c2f1ea4eb1a",
          "label": "Prospectus",
          "doc_type": "prospectus",
          "note": "Jio Platforms Ltd.- Prospectus",
          "source_url": "https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1793005577827.pdf",
          "url": "/api/docs/5a686ac4989df41c209dcf5bf3190a02070f7c6233dca46f4fa51c2f1ea4eb1a.pdf",
          "pages": 596,
          "scanned": false,
          "scanned_label": null
        }
      ],
      "source": "discovered",
      "discovered_on": "2026-11-15"
    }
  ]
}
```

## GET /api/events/{id}

Same fields as one `/api/events` row plus the facts strip: `price` (with evidence inputs), `dates[]`
(listing, allotment, buyback dates, exchange sale), `issue_type`, `offer_size`, `run` (cost in USD
and run time) and `as_of`.

```json
{
  "id": "sedemac_ipo",
  "company": "SEDEMAC Mechatronics Limited",
  "type": "ipo",
  "type_label": "IPO",
  "status": "ready",
  "status_reason": "Call list ready",
  "people_count": 19,
  "entities_count": 16,
  "context_count": 0,
  "tier_counts": {
    "cash_now": 12,
    "unlock": 6,
    "holding": 1
  },
  "cash_cr": 186.75,
  "listing_date": "2026-03-11",
  "money_date": {
    "kind": "listing",
    "label": "Listed",
    "date_iso": "2026-03-11",
    "confirmed": true,
    "display": "11 Mar 2026",
    "relative": "249 days ago"
  },
  "empty_reason": null,
  "docs": [
    {
      "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
      "label": "Red herring prospectus",
      "doc_type": "rhp",
      "note": "RHP dated 25 Feb 2026, hosted by a book-running lead manager",
      "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
      "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf",
      "pages": 582,
      "scanned": false,
      "scanned_label": null
    },
    {
      "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
      "label": "Exchange notice",
      "doc_type": "announcement",
      "note": "Basis of allotment advertisement: final offer price and listing date",
      "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
      "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf",
      "pages": 2,
      "scanned": false,
      "scanned_label": null
    }
  ],
  "source": "added",
  "discovered_on": null,
  "as_of": "2026-11-15",
  "price": {
    "kind": "offer_price",
    "label": "Final offer price",
    "display": "₹1,352 per share",
    "low": 1352.0,
    "high": 1352.0,
    "inputs": [
      {
        "label": "Offer price",
        "value": "₹1,352",
        "evidence": [
          {
            "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
            "doc_label": "Exchange notice",
            "pdf_index": 1,
            "printed_page": null,
            "quote": "OFFER PRICE: ₹1,352* PER EQUITY SHARE OF FACE VALUE OF ₹10 EACH",
            "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=1",
            "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
            "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=1&quote=OFFER%20PRICE%3A%20%E2%82%B91%2C352%2A%20PER%20EQUITY%20SHARE%20OF%20FACE%20VALUE%20OF%20%E2%82%B910%20EACH",
            "cached": true
          }
        ]
      }
    ],
    "reason": null
  },
  "dates": [
    {
      "label": "Listing",
      "date_iso": "2026-03-11",
      "display": "11 Mar 2026",
      "relative": "249 days ago",
      "status": "verified",
      "as_printed": "March 11, 2026",
      "inputs": [
        {
          "label": "Listing date",
          "value": "March 11, 2026",
          "evidence": [
            {
              "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
              "doc_label": "Exchange notice",
              "pdf_index": 1,
              "printed_page": null,
              "quote": "the trading will commence on March 11, 2026.",
              "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=1",
              "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=1&quote=the%20trading%20will%20commence%20on%20March%2011%2C%202026.",
              "cached": true
            }
          ]
        }
      ]
    },
    {
      "label": "Allotment",
      "date_iso": "2026-03-09",
      "display": "9 Mar 2026",
      "relative": "251 days ago",
      "status": "verified",
      "as_printed": "March 9, 2026",
      "inputs": [
        {
          "label": "Allotment date",
          "value": "March 9, 2026",
          "evidence": [
            {
              "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
              "doc_label": "Exchange notice",
              "pdf_index": 2,
              "printed_page": null,
              "quote": "The IPO Committee of the Company on March 9, 2026 has taken on record the Basis of Allotment",
              "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=2",
              "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=2&quote=The%20IPO%20Committee%20of%20the%20Company%20on%20March%209%2C%202026%20has%20taken%20on%20record%20the%20Basis%20of%20Allotment",
              "cached": true
            }
          ]
        }
      ]
    }
  ],
  "issue_type": "IPO",
  "offer_size": null,
  "run": {
    "cost_usd": 0.00142,
    "fresh_cost_usd": 0.02685,
    "seconds": 19.3,
    "run_at": "2026-11-15T09:51:35Z"
  }
}
```

## GET /api/events/{id}/people

`callable` (call order, each with `position`), `entities` (companies and funds on the register,
"Also on the register"), `context` (holders who get no money from this event, each with
`context_reason`, "No money from this event") and `empty_reason` (null when `callable` is not empty).

`empty_reason` wording depends on the event type (`empty_reason` in `api/views.py`): "Scanned filing..." /
"not supported yet" / "not processed yet" for unprocessed events; for a processed **buyback** with context
holders, "No individual gets money from this buyback: N named holders said they will not tender..."; for any
**other** type (block/bulk/insider deals, IPOs) with context holders, "No individual gets money from this
event: N other holders named get no money from it", or, when companies or funds are on the entities list,
"No individual to call: the money from this event goes to companies or funds (A, B, C and N more), and ...";
with only entities, "Every holder named is a company or fund (...); there is no individual to call."; with
nothing, "The documents were read, but they do not name any individual shareholder who gets money from this
event." A block deal is never described as a buyback nobody tendered in.

```json
{
  "event": {
    "id": "sedemac_ipo",
    "company": "SEDEMAC Mechatronics Limited",
    "type": "ipo",
    "type_label": "IPO"
  },
  "callable": [
    {
      "id": "sedemac_ipo/p_ashwini_amit_dixit",
      "event": {
        "id": "sedemac_ipo",
        "company": "SEDEMAC Mechatronics Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_ashwini_amit_dixit",
        "name": "Ashwini Amit Dixit",
        "role": "Promoter Group Selling Shareholder",
        "holder_type": "person"
      },
      "tier": "cash_now",
      "tier_label": "Cash in hand",
      "amount": {
        "value_cr": 9.13,
        "low_cr": 9.13,
        "display": "₹9.13 Cr",
        "detail": "Up to ₹9.13 crore, if all offered shares are sold",
        "kind": "cash",
        "estimate": true,
        "reason": null,
        "source": "proceeds"
      },
      "timing": {
        "label": "In hand since 11 Mar 2026 (8 months ago)",
        "status": "in_hand",
        "date_iso": "2026-03-11",
        "past": true
      },
      "confidence": {
        "level": "high",
        "reason": "Name verified in the seller table; Holdings agree across 2 sections (promoter holdings, shareholding pattern)",
        "reasons": [
          "Name verified in the seller table"
        ]
      },
      "why": "Sells up to 67,500 shares in the offer for sale",
      "brief_first_line": "Ashwini Amit Dixit, Promoter Group Selling Shareholder, is due proceeds from selling up to 67,500 shares in the offer for sale.",
      "household": {
        "id": "sedemac_ipo:family_1",
        "label": "Dixit household",
        "reason": "'Ashwini Amit Dixit' and 'Amit Arun Dixit' share surname 'dixit', and the middle name 'amit' of 'Ashwini Amit Dixit' is the first name of 'Amit Arun Dixit'",
        "members": [
          {
            "id": "sedemac_ipo/p_ashwini_amit_dixit",
            "name": "Ashwini Amit Dixit",
            "role": "Promoter Group Selling Shareholder",
            "tier": "cash_now",
            "amount": {
              "value_cr": 9.13,
              "low_cr": 9.13,
              "display": "₹9.13 Cr",
              "detail": "Up to ₹9.13 crore, if all offered shares are sold",
              "kind": "cash",
              "estimate": true,
              "reason": null,
              "source": "proceeds"
            }
          }
        ],
        "printed_members": [
          "Amit Arun Dixit"
        ]
      },
      "household_id": "sedemac_ipo:family_1",
      "rank": 2,
      "score": 32.04,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "position": 1
    }
  ],
  "entities": [
    {
      "id": "sedemac_ipo/p_a91_emerging_fund_ii_llp",
      "event": {
        "id": "sedemac_ipo",
        "company": "SEDEMAC Mechatronics Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_a91_emerging_fund_ii_llp",
        "name": "A91 Emerging Fund II LLP",
        "role": "Investor Selling Shareholders",
        "holder_type": "entity"
      },
      "tier": "cash_now",
      "tier_label": "Cash in hand",
      "amount": {
        "value_cr": 325.92,
        "low_cr": 325.92,
        "display": "₹325.92 Cr",
        "detail": "Up to ₹325.92 crore, if all offered shares are sold",
        "kind": "cash",
        "estimate": true,
        "reason": null,
        "source": "proceeds"
      },
      "timing": {
        "label": "In hand since 11 Mar 2026 (8 months ago)",
        "status": "in_hand",
        "date_iso": "2026-03-11",
        "past": true
      },
      "confidence": {
        "level": "high",
        "reason": "Name verified in the seller table; Holdings agree across 2 sections (promoter holdings, shareholding pattern)",
        "reasons": [
          "Name verified in the seller table"
        ]
      },
      "why": "Sells up to 2,410,650 shares in the offer for sale",
      "brief_first_line": null,
      "household": null,
      "household_id": null,
      "rank": 1,
      "score": 380.24,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      }
    }
  ],
  "context": [],
  "empty_reason": null
}
```

Event with no one to call (Review focus 1):

```json
{
  "event": {
    "id": "jio_platforms_limited_ipo_202610",
    "company": "Jio Platforms Ltd",
    "type": "ipo",
    "type_label": "IPO"
  },
  "callable": [],
  "entities": [
    {
      "id": "jio_platforms_limited_ipo_202610/p_reliance_industries_limited",
      "event": {
        "id": "jio_platforms_limited_ipo_202610",
        "company": "Jio Platforms Ltd",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_reliance_industries_limited",
        "name": "Reliance Industries Limited",
        "role": null,
        "holder_type": "entity"
      },
      "tier": "holding",
      "tier_label": "Holds shares",
      "amount": {
        "value_cr": 664444.48,
        "low_cr": 664444.48,
        "display": "₹6,64,444.48 Cr",
        "detail": "₹664,444.48 crore (estimate, valued at offer price)",
        "kind": "shares",
        "estimate": true,
        "reason": null,
        "source": "retained"
      },
      "timing": {
        "label": "Lock-in end date not confirmed (no role printed)",
        "status": "unknown",
        "date_iso": null,
        "past": false
      },
      "confidence": {
        "level": "medium",
        "reason": "Not in the seller table; Holdings found in one section only (shareholding pattern)",
        "reasons": [
          "Not in the seller table"
        ]
      },
      "why": "Holds 5,937,841,645 shares before the offer; not selling in it",
      "brief_first_line": null,
      "household": null,
      "household_id": null,
      "rank": 1,
      "score": 0.0,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      }
    }
  ],
  "context": [],
  "empty_reason": "Every holder named is a company or fund (Reliance Industries Limited); there is no individual to call."
}
```

Buyback where everyone named is not tendering (context list):

```json
{
  "event": {
    "id": "jyothy_labs_limited_buyback_202611",
    "company": "Jyothy Labs Limited",
    "type": "buyback",
    "type_label": "Buyback"
  },
  "callable": [],
  "entities": [
    {
      "id": "jyothy_labs_limited_buyback_202611/p_jaya_trust",
      "event": {
        "id": "jyothy_labs_limited_buyback_202611",
        "company": "Jyothy Labs Limited",
        "type": "buyback",
        "type_label": "Buyback"
      },
      "person": {
        "id": "p_jaya_trust",
        "name": "Jaya Trust",
        "role": "Members of the Promoter Group",
        "holder_type": "entity"
      },
      "tier": "holding",
      "tier_label": "Holds shares",
      "amount": {
        "value_cr": null,
        "low_cr": null,
        "display": "Not tendering",
        "detail": null,
        "kind": "cash",
        "estimate": false,
        "reason": "The filing states: “have expressed their intention not to participate in the Buyback”",
        "source": "proceeds"
      },
      "timing": {
        "label": "No payment from this event",
        "status": "not_applicable",
        "date_iso": null,
        "past": false
      },
      "confidence": {
        "level": "medium",
        "reason": "Name verified in the promoter intention disclosure; Holdings found in one section only (promoter intention); Found in one section only (promoter intention)",
        "reasons": [
          "Name verified in the promoter intention disclosure"
        ]
      },
      "why": "States they will not tender in the buyback",
      "brief_first_line": null,
      "household": null,
      "household_id": null,
      "rank": 1,
      "score": 0.0,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      }
    }
  ],
  "context": [
    {
      "id": "jyothy_labs_limited_buyback_202611/p_geetha_moothedath_divakaran",
      "event": {
        "id": "jyothy_labs_limited_buyback_202611",
        "company": "Jyothy Labs Limited",
        "type": "buyback",
        "type_label": "Buyback"
      },
      "person": {
        "id": "p_geetha_moothedath_divakaran",
        "name": "Geetha Moothedath Divakaran",
        "role": "Members of the Promoter Group",
        "holder_type": "person"
      },
      "tier": "holding",
      "tier_label": "Holds shares",
      "amount": {
        "value_cr": null,
        "low_cr": null,
        "display": "Not tendering",
        "detail": null,
        "kind": "cash",
        "estimate": false,
        "reason": "The filing states: “have expressed their intention not to participate in the Buyback”",
        "source": "proceeds"
      },
      "timing": {
        "label": "No payment from this event",
        "status": "not_applicable",
        "date_iso": null,
        "past": false
      },
      "confidence": {
        "level": "medium",
        "reason": "Name verified in the promoter intention disclosure; Holdings found in one section only (promoter intention); Found in one section only (promoter intention)",
        "reasons": [
          "Name verified in the promoter intention disclosure"
        ]
      },
      "why": "States they will not tender in the buyback",
      "brief_first_line": "Geetha Moothedath Divakaran, a Promoter Group member, has stated they will not tender in the buyback.",
      "household": null,
      "household_id": "jyothy_labs_limited_buyback_202611:family_1",
      "rank": 1,
      "score": 0.0,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "context_reason": "Not tendering shares in this buyback, so no money from it"
    }
  ],
  "empty_reason": "No individual gets money from this buyback: 14 named holders said they will not tender, and the other holders named are companies or funds. They are listed below for context."
}
```

## GET /api/people/{event_id}/{person_id}

The call card. Everything a call item has, plus: `list` (`callable|entities|context`), `brief.lines`,
`why_now`, `tier_reason`, `amounts[]` (each: `label`, `value_cr|null`, `display`, `short`, `working`,
`reason`, `inputs[]` each with `evidence[]`, `caveats[]`), `timing_detail[]` (with `rule_evidence[]`,
`inputs[]`, `periods[]`), `name_evidence[]`, `rank_reasons[]`, `household`, `rm` (with `updated_at`),
`event_facts`.

```json
{
  "id": "sedemac_ipo/p_manish_sharma",
  "event": {
    "id": "sedemac_ipo",
    "company": "SEDEMAC Mechatronics Limited",
    "type": "ipo",
    "type_label": "IPO"
  },
  "person": {
    "id": "p_manish_sharma",
    "name": "Manish Sharma",
    "role": "Promoter Selling Shareholder",
    "holder_type": "person"
  },
  "tier": "cash_now",
  "tier_label": "Cash in hand",
  "amount": {
    "value_cr": 6.08,
    "low_cr": 6.08,
    "display": "₹6.08 Cr",
    "detail": "Up to ₹6.08 crore, if all offered shares are sold",
    "kind": "cash",
    "estimate": true,
    "reason": null,
    "source": "proceeds"
  },
  "timing": {
    "label": "In hand since 11 Mar 2026 (8 months ago)",
    "status": "in_hand",
    "date_iso": "2026-03-11",
    "past": true
  },
  "confidence": {
    "level": "high",
    "reason": "Name verified in the seller table; Holdings agree across 2 sections (promoter holdings, shareholding pattern)",
    "reasons": [
      "Name verified in the seller table",
      "Holdings agree across 2 sections (promoter holdings, shareholding pattern)"
    ]
  },
  "why": "Sells up to 45,000 shares in the offer for sale",
  "brief_first_line": "Manish Sharma, Promoter Selling Shareholder, receives money by selling up to 45,000 shares in the offer for sale.",
  "household": {
    "id": "sedemac_ipo:family_3",
    "label": "Sharma household",
    "reason": "'Priyanka Manish Sharma' contains 'Manish Sharma'",
    "members": [
      {
        "id": "sedemac_ipo/p_manish_sharma",
        "name": "Manish Sharma",
        "role": "Promoter Selling Shareholder",
        "tier": "cash_now",
        "amount": {
          "value_cr": 6.08,
          "low_cr": 6.08,
          "display": "₹6.08 Cr",
          "detail": "Up to ₹6.08 crore, if all offered shares are sold",
          "kind": "cash",
          "estimate": true,
          "reason": null,
          "source": "proceeds"
        }
      },
      {
        "id": "sedemac_ipo/p_priyanka_manish_sharma",
        "name": "Priyanka Manish Sharma",
        "role": "Promoter Group",
        "tier": "unlock",
        "amount": {
          "value_cr": 7.71,
          "low_cr": 7.71,
          "display": "₹7.71 Cr",
          "detail": "₹7.71 crore (estimate, valued at offer price)",
          "kind": "shares",
          "estimate": true,
          "reason": null,
          "source": "retained"
        }
      }
    ],
    "printed_members": [
      "Manish Sharma",
      "Priyanka Manish Sharma"
    ]
  },
  "household_id": "sedemac_ipo:family_3",
  "rank": 8,
  "score": 1.824,
  "flags": [],
  "rm": {
    "status": "to_call",
    "follow_up": null,
    "note": "",
    "updated_at": "2026-11-15T13:43:10Z"
  },
  "position": 6,
  "list": "callable",
  "brief": {
    "lines": [
      "Manish Sharma, Promoter Selling Shareholder, receives money by selling up to 45,000 shares in the offer for sale.",
      "Up to ₹6.08 crore in proceeds, if all offered shares are sold; in hand since 11 Mar 2026, 249 days ago."
    ],
    "written_by": "assistant"
  },
  "why_now": "Sells up to 45,000 shares in the offer for sale",
  "tier_reason": "Sold shares in this event; the cash is paid or due within a month",
  "amounts": [
    {
      "key": "proceeds",
      "label": "Cash from the sale",
      "status": "computed",
      "value_cr": 6.08,
      "low_cr": 6.08,
      "display": "Up to ₹6.08 crore, if all offered shares are sold",
      "short": "₹6.08 Cr",
      "working": "45,000 × ₹1,352 = ₹6.08 crore",
      "reason": null,
      "inputs": [
        {
          "label": "Shares offered",
          "value": "45,000",
          "evidence": [
            {
              "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
              "doc_label": "Red herring prospectus",
              "pdf_index": 20,
              "printed_page": "16",
              "quote": "Up to 45,000 Equity Shares of face",
              "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=20",
              "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=20&quote=Up%20to%2045%2C000%20Equity%20Shares%20of%20face",
              "cached": true
            }
          ]
        },
        {
          "label": "Offer price",
          "value": "₹1,352",
          "evidence": [
            {
              "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
              "doc_label": "Exchange notice",
              "pdf_index": 1,
              "printed_page": null,
              "quote": "OFFER PRICE: ₹1,352* PER EQUITY SHARE OF FACE VALUE OF ₹10 EACH",
              "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=1",
              "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=1&quote=OFFER%20PRICE%3A%20%E2%82%B91%2C352%2A%20PER%20EQUITY%20SHARE%20OF%20FACE%20VALUE%20OF%20%E2%82%B910%20EACH",
              "cached": true
            }
          ]
        }
      ],
      "caveats": [
        "Offer price shown; employee-portion shares sold at a discount, so actual proceeds are slightly lower."
      ]
    },
    {
      "key": "gain",
      "label": "Gain over cost",
      "status": "computed",
      "value_cr": 5.88,
      "low_cr": 5.88,
      "display": "Up to ₹5.88 crore, before offer expenses and taxes, if all offered shares are sold",
      "short": "₹5.88 Cr",
      "working": "45,000 × (₹1,352 − ₹46.00) = ₹5.88 crore",
      "reason": null,
      "inputs": [
        {
          "label": "Shares offered",
          "value": "45,000",
          "evidence": [
            {
              "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
              "doc_label": "Red herring prospectus",
              "pdf_index": 20,
              "printed_page": "16",
              "quote": "Up to 45,000 Equity Shares of face",
              "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=20",
              "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=20&quote=Up%20to%2045%2C000%20Equity%20Shares%20of%20face",
              "cached": true
            }
          ]
        },
        {
          "label": "Average cost per share",
          "value": "46.00",
          "evidence": [
            {
              "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
              "doc_label": "Red herring prospectus",
              "pdf_index": 28,
              "printed_page": "24",
              "quote": "Manish Sharma^ 864,000 1.95 46.00",
              "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=28",
              "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=28&quote=Manish%20Sharma%5E%20864%2C000%201.95%2046.00",
              "cached": true
            }
          ]
        }
      ],
      "caveats": []
    }
  ],
  "timing_detail": [
    {
      "key": "proceeds",
      "label": "When the cash arrives",
      "status": "in_hand",
      "display": "In hand since 11 Mar 2026 (8 months ago)",
      "note": null,
      "periods": [],
      "rule_evidence": [
        {
          "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
          "doc_label": "Red herring prospectus",
          "pdf_index": 144,
          "printed_page": "140",
          "quote": "… in the first instance (except fees and expenses for the legal counsel to the Selling Shareholders) and the Selling Shareholders agree that upon commencement of listing and trading of the Equity Shares on the Stock Exchanges pursuant to the Offer, each Selling Shareholder shall, severally and not jointly, reimburse our Company …",
          "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=144",
          "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
          "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=144&quote=%E2%80%A6%20in%20the%20first%20instance%20%28except%20fees%20and%20expenses%20for%20the%20legal%20counsel%20to%20the%20Selling%20Shareholders%29%20and%20the%20Selling%20Shareholders%20agree%20that%20upon%20commencement%20of%20listing%20and%20trading%20of%20the%20Equity%20Shares%20on%20the%20Stock%20Exchanges%20pursuant%20to%20the%20Offer%2C%20each%20Selling%20Shareholder%20shall%2C%20severally%20and%20not%20jointly%2C%20reimburse%20our%20Company%20%E2%80%A6",
          "cached": true
        }
      ],
      "inputs": [
        {
          "label": "Listing date",
          "value": "March 11, 2026",
          "evidence": [
            {
              "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
              "doc_label": "Exchange notice",
              "pdf_index": 1,
              "printed_page": null,
              "quote": "the trading will commence on March 11, 2026.",
              "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=1",
              "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=1&quote=the%20trading%20will%20commence%20on%20March%2011%2C%202026.",
              "cached": true
            }
          ]
        }
      ],
      "rule_found": true
    },
    {
      "key": "retained",
      "label": "When the shares are free",
      "status": "partly_unlocked",
      "display": "Minimum Promoters' Contribution: locked until 9 Sep 2027 (allotment 9 Mar 2026 + 18 months = 9 Sep 2027); promoter shares above the 20%: unlocked since 9 Sep 2026 (2 months ago; allotment 9 Mar 2026 + 6 months = 9 Sep 2026)",
      "note": "Which of this promoter's shares fall in the 20% is not extracted.",
      "periods": [
        {
          "label": "Minimum Promoters' Contribution",
          "ends_on": "2027-09-09",
          "display": "Minimum Promoters' Contribution: locked until 9 Sep 2027 (allotment 9 Mar 2026 + 18 months = 9 Sep 2027)",
          "status": "locked_until",
          "share_of_retained": "unknown"
        },
        {
          "label": "Promoter shares above the 20%",
          "ends_on": "2026-09-09",
          "display": "Promoter shares above the 20%: unlocked since 9 Sep 2026 (2 months ago; allotment 9 Mar 2026 + 6 months = 9 Sep 2026)",
          "status": "unlocked_since",
          "share_of_retained": "unknown"
        }
      ],
      "rule_evidence": [
        {
          "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
          "doc_label": "Red herring prospectus",
          "pdf_index": 132,
          "printed_page": "128",
          "quote": "Pursuant to Regulations 14 and 16 of the SEBI ICDR Regulations, as amended, an aggregate of 20% of the fully diluted post-Offer Equity Share capital of our Company held by our Promoters (assuming exercise of vested options, if any, under the …",
          "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=132",
          "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
          "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=132&quote=Pursuant%20to%20Regulations%2014%20and%2016%20of%20the%20SEBI%20ICDR%20Regulations%2C%20as%20amended%2C%20an%20aggregate%20of%2020%25%20of%20the%20fully%20diluted%20post-Offer%20Equity%20Share%20capital%20of%20our%20Company%20held%20by%20our%20Promoters%20%28assuming%20exercise%20of%20vested%20options%2C%20if%20any%2C%20under%20the%20%E2%80%A6",
          "cached": true
        },
        {
          "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
          "doc_label": "Red herring prospectus",
          "pdf_index": 132,
          "printed_page": "128",
          "quote": "… Regulations, as minimum Promoters’ contribution (“Minimum Promoters’ Contribution”) from the date of Allotment and the shareholding of the Promoter in excess of 20% of the fully diluted post-Offer Equity Share capital shall be locked in for a period of six months from the date of Allotment.",
          "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=132",
          "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
          "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=132&quote=%E2%80%A6%20Regulations%2C%20as%20minimum%20Promoters%E2%80%99%20contribution%20%28%E2%80%9CMinimum%20Promoters%E2%80%99%20Contribution%E2%80%9D%29%20from%20the%20date%20of%20Allotment%20and%20the%20shareholding%20of%20the%20Promoter%20in%20excess%20of%2020%25%20of%20the%20fully%20diluted%20post-Offer%20Equity%20Share%20capital%20shall%20be%20locked%20in%20for%20a%20period%20of%20six%20months%20from%20the%20date%20of%20Allotment.",
          "cached": true
        }
      ],
      "inputs": [
        {
          "label": "Allotment date",
          "value": "March 9, 2026",
          "evidence": [
            {
              "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
              "doc_label": "Exchange notice",
              "pdf_index": 2,
              "printed_page": null,
              "quote": "The IPO Committee of the Company on March 9, 2026 has taken on record the Basis of Allotment",
              "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=2",
              "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=2&quote=The%20IPO%20Committee%20of%20the%20Company%20on%20March%209%2C%202026%20has%20taken%20on%20record%20the%20Basis%20of%20Allotment",
              "cached": true
            }
          ]
        }
      ],
      "rule_found": null
    }
  ],
  "name_evidence": [
    {
      "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
      "doc_label": "Red herring prospectus",
      "pdf_index": 20,
      "printed_page": "16",
      "quote": "Manish Sharma",
      "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=20",
      "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
      "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=20&quote=Manish%20Sharma",
      "cached": true
    },
    {
      "doc_sha": "2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e",
      "doc_label": "Red herring prospectus",
      "pdf_index": 28,
      "printed_page": "24",
      "quote": "Manish Sharma^ 864,000 1.95 46.00",
      "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf#page=28",
      "source_url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
      "image_url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=28&quote=Manish%20Sharma%5E%20864%2C000%201.95%2046.00",
      "cached": true
    }
  ],
  "rank_reasons": [
    "Sells up to 45,000 shares in the offer for sale",
    "Family link: 'Priyanka Manish Sharma' contains 'Manish Sharma'"
  ],
  "names_as_printed": [
    "Manish Sharma"
  ],
  "holder_type_reason": "No entity or family marker",
  "context_reason": null,
  "event_facts": {
    "price": {
      "kind": "offer_price",
      "label": "Final offer price",
      "display": "₹1,352 per share",
      "low": 1352.0,
      "high": 1352.0,
      "inputs": [
        {
          "label": "Offer price",
          "value": "₹1,352",
          "evidence": [
            {
              "doc_sha": "3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53",
              "doc_label": "Exchange notice",
              "pdf_index": 1,
              "printed_page": null,
              "quote": "OFFER PRICE: ₹1,352* PER EQUITY SHARE OF FACE VALUE OF ₹10 EACH",
              "url": "/api/docs/3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53.pdf#page=1",
              "source_url": "https://nsearchives.nseindia.com/corporate/ADV_INE00XB01019_10MAR2026.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=3d8957a1863771d7423cb562ae1d021aa5046f50f73dab52045b294f7594aa53&pdf_index=1&quote=OFFER%20PRICE%3A%20%E2%82%B91%2C352%2A%20PER%20EQUITY%20SHARE%20OF%20FACE%20VALUE%20OF%20%E2%82%B910%20EACH",
              "cached": true
            }
          ]
        }
      ],
      "reason": null
    },
    "money_date": {
      "kind": "listing",
      "label": "Listed",
      "date_iso": "2026-03-11",
      "confirmed": true
    }
  }
}
```

Unknown amount (Review focus 2): `value_cr` is null, `display` says "Amount not disclosed", `reason` says why.

```json
{
  "id": "spacenet_ofs/p_lanka_divyabharathi",
  "event": {
    "id": "spacenet_ofs",
    "company": "String Metaverse Limited",
    "type": "ofs_stock_exchange",
    "type_label": "Offer for sale (exchange)"
  },
  "person": {
    "id": "p_lanka_divyabharathi",
    "name": "Lanka Divyabharathi",
    "role": "Promoter Group",
    "holder_type": "person"
  },
  "tier": "cash_now",
  "tier_label": "Cash in hand",
  "amount": {
    "value_cr": null,
    "low_cr": null,
    "display": "Amount not disclosed",
    "detail": null,
    "kind": "cash",
    "estimate": false,
    "reason": "The notice prints Up to 38,10,000 Equity Shares for all sellers together, not this seller's own shares",
    "source": "proceeds"
  },
  "timing": {
    "label": "Settles after the sale on 21 Apr 2026 (6 months ago)",
    "status": "after_date",
    "date_iso": "2026-04-21",
    "past": true
  },
  "confidence": {
    "level": "medium",
    "reason": "Name verified in the seller list in the notice; Found in one section only (sellers)",
    "reasons": [
      "Name verified in the seller list in the notice"
    ]
  },
  "why": "Sells in the offer for sale through the stock exchange; own shares not printed",
  "brief_first_line": "Lanka Divyabharathi, Promoter Group, sells shares in the offer for sale through the stock exchange.",
  "household": null,
  "household_id": null,
  "rank": 1,
  "score": 0.0,
  "flags": [],
  "rm": {
    "status": "to_call",
    "follow_up": null,
    "note": "",
    "updated_at": null
  },
  "position": 1,
  "list": "callable",
  "brief": {
    "lines": [
      "Lanka Divyabharathi, Promoter Group, sells shares in the offer for sale through the stock exchange."
    ],
    "written_by": "assistant"
  },
  "why_now": "Sells in the offer for sale through the stock exchange; own shares not printed",
  "tier_reason": "Sold shares in this event; the cash is paid or due within a month",
  "amounts": [
    {
      "key": "proceeds",
      "label": "Cash from the sale",
      "status": "unknown",
      "value_cr": null,
      "low_cr": null,
      "display": "Amount not disclosed",
      "short": "",
      "working": null,
      "reason": "The notice prints Up to 38,10,000 Equity Shares for all sellers together, not this seller's own shares",
      "inputs": [],
      "caveats": []
    }
  ],
  "timing_detail": [
    {
      "key": "proceeds",
      "label": "When the cash arrives",
      "status": "after_date",
      "display": "Settles after the sale on 21 Apr 2026 (6 months ago)",
      "note": "Settlement words as printed; the trading-day count is not turned into a date",
      "periods": [],
      "rule_evidence": [],
      "inputs": [
        {
          "label": "Sale date",
          "value": "21st April, 2026",
          "evidence": [
            {
              "doc_sha": "8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850",
              "doc_label": "Exchange notice",
              "pdf_index": 3,
              "printed_page": null,
              "quote": "For non-Retail Investors (defined below): 21st April, 2026",
              "url": "/api/docs/8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850.pdf#page=3",
              "source_url": "https://nsearchives.nseindia.com/corporate/SPCENET_20042026211814_MCOutcomeOFSofSML.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850&pdf_index=3&quote=For%20non-Retail%20Investors%20%28defined%20below%29%3A%2021st%20April%2C%202026",
              "cached": true
            }
          ]
        }
      ],
      "rule_found": null
    }
  ],
  "name_evidence": [
    {
      "doc_sha": "8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850",
      "doc_label": "Exchange notice",
      "pdf_index": 3,
      "printed_page": "2 of 18",
      "quote": "3. Lanka Divyabharathi, and",
      "url": "/api/docs/8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850.pdf#page=3",
      "source_url": "https://nsearchives.nseindia.com/corporate/SPCENET_20042026211814_MCOutcomeOFSofSML.pdf",
      "image_url": "/api/evidence/page.png?doc_sha=8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850&pdf_index=3&quote=3.%20Lanka%20Divyabharathi%2C%20and",
      "cached": true
    }
  ],
  "rank_reasons": [
    "Sells in the offer for sale through the stock exchange; own shares not printed"
  ],
  "names_as_printed": [
    "Lanka Divyabharathi"
  ],
  "holder_type_reason": "No entity or family marker",
  "context_reason": null,
  "event_facts": {
    "price": {
      "kind": "floor_price",
      "label": "Floor price",
      "display": "₹66 per share",
      "low": 66.0,
      "high": 66.0,
      "inputs": [
        {
          "label": "Floor price",
          "value": "INR 66.00/- (Rupees Sixty Six Only) per Equity Share",
          "evidence": [
            {
              "doc_sha": "8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850",
              "doc_label": "Exchange notice",
              "pdf_index": 6,
              "printed_page": null,
              "quote": "The floor price for the Offer shall be INR 66.00/- (Rupees",
              "url": "/api/docs/8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850.pdf#page=6",
              "source_url": "https://nsearchives.nseindia.com/corporate/SPCENET_20042026211814_MCOutcomeOFSofSML.pdf",
              "image_url": "/api/evidence/page.png?doc_sha=8607a7311de1cff9129b5affb48513aeec4d4335eaf22fa4349253b2295b5850&pdf_index=6&quote=The%20floor%20price%20for%20the%20Offer%20shall%20be%20INR%2066.00/-%20%28Rupees",
              "cached": true
            }
          ]
        }
      ],
      "reason": null
    },
    "money_date": {
      "kind": "ofs_sale",
      "label": "Sale on the exchange",
      "date_iso": "2026-04-21",
      "confirmed": true
    }
  }
}
```

## GET /api/evidence/page.png?doc_sha=&pdf_index=&quote=

A PNG of the page (150 dpi, longest side at most 2200 px) with the quote's lines boxed in yellow.
Use the ready-made `image_url` from any evidence ref. Headers:

- `X-Highlight: found | none`. On `none` the plain page is returned (Review focus 5): show it with
  the quote text beside it.
- `X-Highlight-Box: x0,y0,x1,y1` (fractions 0..1 of the image) when found, to scroll the viewer to it.
- 404 `{"detail": ...}` when the PDF is not stored or the page does not exist.

First render of a page takes 0.5 to 4 s; then it is cached on disk. On startup the API pre-renders
the headline evidence of the top 25 calls (`FINSIGHT_WARM=0` skips this).

```json
{
  "url": "/api/evidence/page.png?doc_sha=2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e&pdf_index=20&quote=Up%20to%2045%2C000%20Equity%20Shares%20of%20face",
  "status": 200,
  "content-type": "image/png",
  "X-Highlight": "found",
  "X-Highlight-Box": "0.4493,0.8755,0.6424,0.8850",
  "bytes": 607706
}
```

```json
{
  "status": 200,
  "X-Highlight": "none",
  "bytes": 606489
}
```

## GET /api/docs/{sha}.pdf

The cached PDF, inline. Append `#page=<pdf_index>` to open at a page.

```json
{
  "url": "/api/docs/2a9bdef9398146e01591a75719a467640f34e941aea5f101fd55436f80aa036e.pdf",
  "status": 200,
  "content-type": "application/pdf",
  "bytes": 10183378
}
```

## GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD

Dated money items, one per (date, kind, event): `kind` is `listing` (sellers paid),
`unlock` (lock-in ends), `buyback_payment`, `buyback_closing` or `ofs_sale`. `confirmed: false` means
the date is from the offer timetable, not a later notice. `total_cr` sums known amounts (null when
none are known); `unknown_count` counts people without an amount. Both bounds optional, inclusive.

```json
{
  "from": "2026-10-01",
  "to": "2026-12-31",
  "as_of": "2026-11-15",
  "count": 6,
  "items": [
    {
      "date_iso": "2026-10-21",
      "display": "21 Oct 2026",
      "relative": "25 days ago",
      "kind": "listing",
      "label": "Listing day: sellers paid",
      "event": {
        "id": "hd_fire_protect_limited_ipo_202610",
        "company": "HD Fire Protect Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "confirmed": false,
      "past": true,
      "people": [
        {
          "id": "hd_fire_protect_limited_ipo_202610/p_kusum_harish_dharamshi",
          "person_id": "p_kusum_harish_dharamshi",
          "name": "KUSUM HARISH DHARAMSHI",
          "tier": "cash_now",
          "value_cr": 468.85,
          "value_kind": "cash"
        },
        {
          "id": "hd_fire_protect_limited_ipo_202610/p_harish_narshi_dharamshi",
          "person_id": "p_harish_narshi_dharamshi",
          "name": "HARISH NARSHI DHARAMSHI",
          "tier": "cash_now",
          "value_cr": 243.46,
          "value_kind": "cash"
        }
      ],
      "total_cr": 712.31,
      "people_count": 2,
      "unknown_count": 0
    },
    {
      "date_iso": "2026-10-23",
      "display": "23 Oct 2026",
      "relative": "23 days ago",
      "kind": "listing",
      "label": "Listing day: sellers paid",
      "event": {
        "id": "tonbo_imaging_india_limited_ipo_202610",
        "company": "Tonbo Imaging India Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "confirmed": false,
      "past": true,
      "people": [
        {
          "id": "tonbo_imaging_india_limited_ipo_202610/p_arvind_kondangi_lakshmikumar",
          "person_id": "p_arvind_kondangi_lakshmikumar",
          "name": "ARVIND KONDANGI LAKSHMIKUMAR",
          "tier": "cash_now",
          "value_cr": 80.5,
          "value_kind": "cash"
        },
        {
          "id": "tonbo_imaging_india_limited_ipo_202610/p_ankit_kumar",
          "person_id": "p_ankit_kumar",
          "name": "ANKIT KUMAR",
          "tier": "cash_now",
          "value_cr": 40.6,
          "value_kind": "cash"
        }
      ],
      "total_cr": 168.93,
      "people_count": 8,
      "unknown_count": 1
    }
  ]
}
```

## GET /api/network

Graph for react-force-graph. Only connected holders are returned: a holder is kept when it appears at
more than one company (`event_count > 1`), in more than one money event (`money_events > 1`), or in a
family group. Holders tied to a single event and no family are left out.

Node ids: company nodes are `e:<company tokens joined>` (not an event id; see below), holder nodes are
`p:<clean name>`. Node `type`: `event | person | entity`. Edge `kind`: `holds` (holder to company) and
`household` (members of one family group). The API no longer emits `same_person` edges (one holder is
one node, so there is nothing to join); the web type still tolerates the kind. Every edge has a `reason`.

**Company ("event") nodes** are one per company, not one per event. Weekly block/insider deals and an IPO
of the same firm merge into one node. Spellings merge via `company_tokens` / `same_company` in
`api/views.py`: case, punctuation and legal suffixes (`Limited`, `Ltd`, `L`, `Pvt`, `Private`, `The`, `Co`,
`Inc`) are ignored, and two names are one company when they have the same first word, the same number of
words (at least two) and each word is a prefix of the other ("Ltd." vs "Limited", the exchange's truncated
"Medical Tech L", "tech" vs "technologies"). The fullest spelling is the label.

| Field | Meaning |
|---|---|
| `label` | the company's fullest spelling seen |
| `events[]` | one row per money event behind the node: `{event: <event_ref>, date_iso, to_call}`. `to_call` is that event's callable-individual count. Sorted most `to_call` first, newest first among ties |
| `event` | the event to open on click; always `events[0].event` (the one with the most people to call) |
| `to_call` | individuals to call across all of the company's events, a name counted once (the call list holds no funds) |
| `people_count` | linked holders drawn (kept holders with a `holds` edge to this node, people and funds); sets the dot size |
| `linked_people`, `linked_entities` | `people_count` split into persons and companies/funds |
| `event_count` | how many money events the company has |
| `event_types` | sorted type labels of those events (for the event-type filter) |

**Holder nodes** (`person` or `entity`) carry `label`, `role`, `tier`, `list` (`callable | entities | context`,
of the primary appearance), `value_cr`, `estimate`, plus:

| Field | Meaning |
|---|---|
| `event_id`, `person_id` | the primary appearance (the biggest amount seen), used for the link to the person page |
| `company` | the company of that primary appearance (merged spelling) |
| `also_in` | other companies the holder appears in, sorted |
| `event_count` | number of distinct companies the holder is in (`also_in` plus the primary one) |
| `money_events` | number of distinct money events (one insider selling in several weekly disclosures counts several) |
| `in_household` | true when the holder is in a family group |
| `event_types` | sorted type labels of the events the holder is tied to |

A holder is typed `entity` when `holder_type` is `entity` on any list it sits on (a fund that is a buyer in
a block deal is on the `context` list but is still drawn as a fund), or when any appearance is on the
`entities` list. A same-named person and fund merge into one node and the entity classification wins.

Shape example (values illustrative):

```json
{
  "nodes": [
    {
      "id": "e:examplemedicaltech",
      "type": "event",
      "label": "Example Medical Technologies Limited",
      "event": {"id": "example_block_deal_20261110", "company": "Example Medical Technologies Limited",
                "type": "block_deal", "type_label": "Block deal"},
      "events": [
        {"event": {"id": "example_block_deal_20261110", "company": "Example Medical Technologies Limited",
                   "type": "block_deal", "type_label": "Block deal"}, "date_iso": "2026-11-10", "to_call": 3},
        {"event": {"id": "example_ipo_202606", "company": "Example Medical Tech L",
                   "type": "ipo", "type_label": "IPO"}, "date_iso": "2026-06-20", "to_call": 0}
      ],
      "to_call": 3,
      "people_count": 4,
      "linked_people": 3,
      "linked_entities": 1,
      "event_count": 2,
      "event_types": ["Block deal", "IPO"]
    },
    {
      "id": "p:example holder",
      "type": "person",
      "label": "Example Holder",
      "role": "Promoter",
      "tier": "cash_now",
      "list": "callable",
      "value_cr": 12.5,
      "estimate": false,
      "event_id": "example_block_deal_20261110",
      "person_id": "p_example_holder",
      "company": "Example Medical Technologies Limited",
      "also_in": ["Another Company Limited"],
      "event_count": 2,
      "money_events": 3,
      "in_household": true,
      "event_types": ["Block deal", "IPO"]
    }
  ],
  "edges": [
    {"source": "p:example holder", "target": "e:examplemedicaltech", "kind": "holds",
     "reason": "Promoter in Example Medical Technologies Limited"},
    {"source": "p:example holder", "target": "p:example relative", "kind": "household",
     "reason": "'Example Holder' and 'Example Relative' share surname 'holder', ..."}
  ],
  "legend": {
    "event": "Money event",
    "person": "Person to call",
    "entity": "Company or fund",
    "holds": "Holds shares in",
    "household": "Same household"
  }
}
```

There is no `_counts` field; count `nodes` and `edges` yourself.

## GET /api/feed

Discovered filings in three groups (`today`, `upcoming`, `recent` = last 30 days). Item `status`:
`ready | empty | failed | waiting | unsupported | scanned`, with `status_label`, `reason`,
`next_action` (button text) and `processable` (show "Process now").

```json
{
  "refreshed_at": "2026-11-15T10:11:13+00:00",
  "sources_ok": [
    "SEBI · Red herring documents filed with ROC",
    "SEBI · Final offer documents filed with ROC",
    "SEBI · Buybacks: tender offers",
    "SEBI · Takeovers: letters of offer",
    "SEBI · RSS"
  ],
  "sources_with_problems": [],
  "items_total": 100,
  "groups": {
    "today": [],
    "upcoming": [
      {
        "id": "548de7f80191",
        "title": "Crystal Crop Protection Limited– RHP",
        "company": "Crystal Crop Protection Limited",
        "source": "SEBI · Red herring documents filed with ROC",
        "published_iso": "2026-11-12",
        "published_display": "12 Nov 2026",
        "link": "https://www.sebi.gov.in/filings/public-issues/nov-2026/crystal-crop-protection-limited-rhp_105734.html",
        "kind_label": "IPO red herring prospectus",
        "event_type": "ipo",
        "event_id": "crystal_crop_protection_limited_ipo_202611",
        "status": "ready",
        "status_label": "Call list ready",
        "reason": "6 to call",
        "next_action": "Open call list",
        "processable": false,
        "money_date": "2026-11-26",
        "money_date_display": "26 Nov 2026"
      }
    ],
    "recent": [
      {
        "id": "cf32cc98fc3f",
        "title": "Shree OSFM E-Mobility Limited",
        "company": "Shree OSFM E-Mobility Limited",
        "source": "SEBI · Takeovers: letters of offer",
        "published_iso": "2026-11-12",
        "published_display": "12 Nov 2026",
        "link": "https://www.sebi.gov.in/filings/takeovers/nov-2026/shree-osfm-e-mobility-limited_105747.html",
        "kind_label": "Takeover open offer",
        "event_type": null,
        "event_id": null,
        "status": "unsupported",
        "status_label": "Detected; not supported yet",
        "reason": "Takeover open offer",
        "next_action": "Not supported yet",
        "processable": false,
        "money_date": null,
        "money_date_display": ""
      }
    ]
  }
}
```

## GET /api/ops

Trust & Ops: per processed event cost (this run and with no cache, USD), cost per person, run
seconds, `steps[]` (with RM labels), `verification` (values proposed / kept / rejected per section)
and `rejections[]` (who, what, value, reason in plain words). `target_usd` is the per-event budget.

```json
{
  "target_usd": 2.0,
  "events": [
    {
      "event": {
        "id": "sedemac_ipo",
        "company": "SEDEMAC Mechatronics Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "cost_usd": 0.00142,
      "fresh_cost_usd": 0.02685,
      "per_person_usd": 7.5e-05,
      "fresh_per_person_usd": 0.001413,
      "model_calls": 32,
      "cached_share": 0.969,
      "people": 19,
      "run_seconds": 19.3,
      "run_at": "2026-11-15T09:51:35Z",
      "steps": [
        {
          "step": "locate",
          "label": "Find the right pages",
          "seconds": 6.78,
          "calls": 0,
          "cached": 0,
          "cost_usd": 0
        },
        {
          "step": "extract",
          "label": "Read the tables",
          "seconds": 11.74,
          "calls": 10,
          "cached": 9,
          "cost_usd": 0.00142
        }
      ],
      "verification": {
        "sections": [
          {
            "section": "Selling shareholders",
            "proposed": 92,
            "kept": 90,
            "rejected": 2
          },
          {
            "section": "Average cost of shares",
            "proposed": 78,
            "kept": 78,
            "rejected": 0
          }
        ],
        "proposed": 305,
        "kept": 295,
        "rejected": 10
      },
      "rejections": [
        {
          "who": "Xponentia Opportunities Fund II",
          "what": "Role",
          "value": "Investor Selling Shareholders",
          "reason": "The role heading was not above this name",
          "section": "Selling shareholders"
        },
        {
          "who": "Xponentia Opportunities Limited",
          "what": "Role",
          "value": "Investor Selling Shareholders",
          "reason": "The role heading was not above this name",
          "section": "Selling shareholders"
        }
      ]
    }
  ],
  "totals": {
    "events": 16,
    "fresh_cost_usd": 0.206335,
    "max_fresh_cost_usd": 0.02685,
    "avg_fresh_cost_usd": 0.012896,
    "proposed": 1169,
    "kept": 1035,
    "rejected": 115
  },
  "recent_runs": [
    {
      "event_id": "hd_fire_protect_limited_ipo_202610",
      "started_at": "2026-11-15T10:20:26Z",
      "seconds": 15.133,
      "cost_usd": 0.000437,
      "status": "ok",
      "error": null
    },
    {
      "event_id": "automobile_corporation_of_goa_limited_buyback_202610",
      "started_at": "2026-11-15T10:17:04Z",
      "seconds": 0.561,
      "cost_usd": 0.0,
      "status": "ok",
      "error": null
    }
  ]
}
```

## POST /api/events/from-links

Body `{"urls": ["https://..."]}` (up to 6). Returns a proposal per link (document type, event type,
company, with the quotes they were read from; `how` is `rules` or `model`; `error` explains an
unreadable link) and a `suggested` company and event type. It downloads the first pages of each
link, so it can take a few seconds.

```json
{
  "proposals": [
    {
      "url": "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf",
      "doc_type": "rhp",
      "event_type": "ipo",
      "label": "red herring prospectus",
      "type_quote": "RED HERRING PROSPECTUS Dated February 25, 2026 Please read Section 32 of the Companies Act, 2013 100% Book Built",
      "company": "SEDEMAC MECHATRONICS LIMITED",
      "company_quote": "PUBLIC OFFER OF UP TO 8,043,300 EQUITY SHARES OF FACE VALUE OF ₹10 EACH (“EQUITY SHARES”) OF SEDEMAC MECHATRONICS LIMITED (“COMPANY”) FOR CASH AT A PRICE OF ₹[●] PER EQUITY SHARE (INCLUDING A SHARE PREMIUM OF ₹[●]",
      "how": "rules",
      "error": null
    }
  ],
  "suggested": {
    "company": "SEDEMAC MECHATRONICS LIMITED",
    "event_type": "ipo"
  }
}
```

Also returned (added for the Events screen): `existing_event_id`, the id of an event already in the app
with one of these links (or the same company, type and month), else `null`. The UI then offers
"Process now / Open event" instead of creating a duplicate.

## POST /api/events

Body: an event spec `{"event_id": "lowercase_slug", "event_type": "ipo|buyback|ofs_stock_exchange",
"company": "...", "documents": [{"url": "https://...", "doc_type": "rhp|prospectus|letter_of_offer|public_announcement|announcement|news", "note": "optional"}]}`.
Writes `events/<event_id>.json`, then call run. Success (captured with a temporary events folder):

```json
{
  "status": 200,
  "body": {
    "event_id": "acme_widgets_ipo_202611",
    "created": true
  }
}
```

Id already used, and an invalid id:

```json
{
  "status": 409,
  "body": {
    "detail": "An event with this id already exists"
  }
}
```

```json
{
  "status": 422,
  "body": {
    "detail": "event_id: Value error, event_id must be a lowercase slug"
  }
}
```

## POST /api/events/{id}/run → GET /api/jobs/{job_id}/stream

`POST /api/events/{id}/run` starts processing (or returns the job already running for that event):

```json
{
  "job_id": "84e215aec468",
  "event_id": "vectras_ipo",
  "state": "running",
  "steps": [
    {
      "step": "locate",
      "label": "Find the right pages"
    },
    {
      "step": "extract",
      "label": "Read the tables"
    },
    {
      "step": "people",
      "label": "Match people and families"
    },
    {
      "step": "rank",
      "label": "Rank who to call"
    },
    {
      "step": "brief",
      "label": "Write call briefs"
    },
    {
      "step": "report",
      "label": "Assemble the call list"
    }
  ],
  "stream_url": "/api/jobs/84e215aec468/stream"
}
```

`GET /api/jobs/{job_id}/stream` is Server-Sent Events (`new EventSource(url)`): one `data:` JSON per
step start / done / failed, then a final `{state: "complete"|"failed", reason}`; the stream then
closes. On failure the event's previous call list is restored, so just refetch. While a job runs the
event's `status` is `processing`. The examples below were captured from the real endpoints with
`run.py` replaced by a stand-in script that prints run.py's exact progress lines (a real run takes
10 to 90 s and replays the model cache). Comment lines `: keep-alive` are sent while a step runs.

```text
data: {"step": "locate", "label": "Find the right pages", "state": "start", "index": 1, "total": 6, "at": 0.0}
data: {"step": "locate", "label": "Find the right pages", "state": "done", "index": 1, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 1, "cached": 1, "at": 0.2}
data: {"step": "extract", "label": "Read the tables", "state": "start", "index": 2, "total": 6, "at": 0.2}
data: {"step": "extract", "label": "Read the tables", "state": "done", "index": 2, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 1, "cached": 1, "at": 0.4}
data: {"step": "people", "label": "Match people and families", "state": "start", "index": 3, "total": 6, "at": 0.4}
data: {"step": "people", "label": "Match people and families", "state": "done", "index": 3, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 1, "cached": 1, "at": 0.6}
data: {"step": "rank", "label": "Rank who to call", "state": "start", "index": 4, "total": 6, "at": 0.6}
data: {"step": "rank", "label": "Rank who to call", "state": "done", "index": 4, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 1, "cached": 1, "at": 0.8}
data: {"step": "brief", "label": "Write call briefs", "state": "start", "index": 5, "total": 6, "at": 0.8}
data: {"step": "brief", "label": "Write call briefs", "state": "done", "index": 5, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 1, "cached": 1, "at": 1.0}
data: {"step": "report", "label": "Assemble the call list", "state": "start", "index": 6, "total": 6, "at": 1.0}
data: {"step": "report", "label": "Assemble the call list", "state": "done", "index": 6, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 1, "cached": 1, "at": 1.2}
data: {"state": "complete", "reason": null, "seconds": 1.2, "cost_usd": 0.0, "at": 1.2}
```

A failed run (stand-in script: a document download fails while reading the tables):

```text
data: {"step": "locate", "label": "Find the right pages", "state": "start", "index": 1, "total": 6, "at": 0.0}
data: {"step": "locate", "label": "Find the right pages", "state": "done", "index": 1, "total": 6, "seconds": 0.2, "cost_usd": 0.0, "calls": 0, "cached": 0, "at": 0.2}
data: {"step": "extract", "label": "Read the tables", "state": "start", "index": 2, "total": 6, "at": 0.2}
data: {"step": "extract", "label": "Read the tables", "state": "failed", "at": 0.2}
data: {"state": "failed", "reason": "A document could not be downloaded while reading the tables. The previous call list is kept.", "at": 0.2}
```

`GET /api/jobs/{job_id}` (polling fallback; events cut to 3):

```json
{
  "job_id": "84e215aec468",
  "state": "complete",
  "events": [
    {
      "step": "locate",
      "label": "Find the right pages",
      "state": "start",
      "index": 1,
      "total": 6,
      "at": 0.0
    },
    {
      "step": "locate",
      "label": "Find the right pages",
      "state": "done",
      "index": 1,
      "total": 6,
      "seconds": 0.2,
      "cost_usd": 0.0,
      "calls": 1,
      "cached": 1,
      "at": 0.2
    },
    {
      "state": "complete",
      "reason": null,
      "seconds": 1.2,
      "cost_usd": 0.0,
      "at": 1.2
    }
  ]
}
```

### Agent events and the trace (additive)

Since the agent trace (`tools/trace.py`), a step `done` event also carries `agent` (the step name),
`why` (what decided it ran) and `runs_on` (`"code"` or the model ids that answered, e.g.
`"code + anthropic/claude-haiku-5.5"`). Between step events the stream carries **agent events**
for every agent or code sub-step. They have **no `step` and no `state` key**, so a consumer
that only knows step events skips them:

```text
data: {"type": "agent", "parent": "extract", "phase": "start", "agent": "verify_waca", "label": "Verify: average cost of shares", "why": "every value must sit inside a quote found on its cited page", "given": "22 quotes on 5 pages", "runs_on": "code", "doing": "checking 22 quotes on their pages", "at": 41.2}
data: {"type": "agent", "parent": "extract", "phase": "done", "agent": "verify_waca", "label": "Verify: average cost of shares", "status": "ok", "returns": {"proposed": 22, "kept": 22, "rejected": 0, "citations_corrected": 0}, "ms": 125.5, "runs_on": "code", "calls": 0, "cached_calls": 0, "cached": 0, "fresh_calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "at": 41.3}
data: {"type": "agent", "parent": "brief", "phase": "progress", "agent": "brief", "doing": "writing brief 3 of 5", "done": 2, "total": 5, "at": 66.0}
```

`GET /api/events/{id}/trace` returns how the last run built the list (404 before the first
run): `{version, event_id, run_id, started_at, source: "live" | "rebuilt from logs", total_ms,
totals: {calls, cached_calls, fresh_calls, tokens_in, tokens_out, cost_usd, ms}, cost_log:
{calls, cached_calls, cost_usd}, balanced, steps: [record], agents: [record]}`. A record is
`{name, kind: "step"|"agent", step, label, why, given, returns, runs_on, status, ms, start_ms?,
order, calls, cached_calls, fresh_calls, failed_calls, unpriced_calls, tokens_in, tokens_out,
cost_usd, model_s}`. Every cost-log row of the run belongs to exactly one agent record, so
`totals` equals `cost_log` (`balanced: true`). A run from before traces existed is rebuilt from
`timeline.json`, the outputs and the cost log (one record per model agent and per code step).

`GET /api/events/{id}/runs` lists the event's runs (`outputs/runs.csv`): `{event_id, count,
runs: [{run_id, started_at, status, full, seconds, calls, cached_calls, cached_share,
cost_usd}], first, latest, saved_vs_first: {cost_usd, seconds} | null}`. `first` and `latest`
are the earliest and the last full run (`run.py --step all`); a step-only rerun is not full.

## POST /api/ask

Body `{"q": "promoters with cash in hand above 50 crore"}`. The model only turns the question into
a fixed filter (`event_type, role_contains, tier, min_cr, max_cr, timing_status, confidence,
company`); code applies it to the call items, so every person and number shown is stored data. A
numeric bound is kept only if that number is written in the question. `interpreted_by`:
`assistant` (model), `rules` (model unavailable, word rules), `keyword` (name/company/role search).
Show `chips` as "Interpreted as" chips; `people` are call items in call order. The filter is applied to each sale,
then one holder's repeat sales at a company are folded into one item (as in `/api/today`); `count` counts the
folded items.

Model unavailable (rules path):

```json
{
  "question": "promoters with cash in hand above 50 crore",
  "filters": {
    "role_contains": "promoter",
    "tier": "cash_now",
    "min_cr": 50.0
  },
  "chips": [
    "Role: Promoter",
    "Cash in hand",
    "≥ ₹50.00 Cr"
  ],
  "people": [
    {
      "id": "zetwerk_manufacturing_businesses_limited_ipo_202610/p_amrit_pratik_acharya",
      "event": {
        "id": "zetwerk_manufacturing_businesses_limited_ipo_202610",
        "company": "Zetwerk Manufacturing Businesses Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_amrit_pratik_acharya",
        "name": "Amrit Pratik Acharya",
        "role": "Promoter Selling Shareholders",
        "holder_type": "person"
      },
      "tier": "cash_now",
      "tier_label": "Cash in hand",
      "amount": {
        "value_cr": 214.88,
        "low_cr": 214.88,
        "display": "₹214.88 Cr",
        "detail": "₹214.88 crore",
        "kind": "cash",
        "estimate": false,
        "reason": null,
        "source": "proceeds"
      },
      "timing": {
        "label": "Listing was due 23 Oct 2026 (23 days ago); listing notice not yet seen",
        "status": "due_past",
        "date_iso": "2026-10-23",
        "past": true
      },
      "confidence": {
        "level": "medium",
        "reason": "Name verified in the seller table; No verified pre-offer holding",
        "reasons": [
          "Name verified in the seller table"
        ]
      },
      "why": "Sells 14,230,672 shares in the offer for sale",
      "brief_first_line": "Amrit Pratik Acharya, a Promoter Selling Shareholder, is due proceeds from selling 14,230,672 shares in the offer for sale.",
      "household": null,
      "household_id": null,
      "rank": 1,
      "score": 120.3328,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "position": 1
    }
  ],
  "count": 4,
  "interpreted_by": "rules",
  "explanation": "Interpreted as: Role: Promoter · Cash in hand · ≥ ₹50.00 Cr. 4 match."
}
```

Model path (model stubbed to return `{"tier": "unlock", "role_contains": "promoter"}`):

```json
{
  "question": "which promoters just got their shares unlocked?",
  "filters": {
    "role_contains": "promoter",
    "tier": "unlock"
  },
  "chips": [
    "Role: Promoter",
    "Shares just unlocked"
  ],
  "people": [
    {
      "id": "sedemac_ipo/p_mallika_r_iyer",
      "event": {
        "id": "sedemac_ipo",
        "company": "SEDEMAC Mechatronics Limited",
        "type": "ipo",
        "type_label": "IPO"
      },
      "person": {
        "id": "p_mallika_r_iyer",
        "name": "Mallika R Iyer",
        "role": "Promoter Group",
        "holder_type": "person"
      },
      "tier": "unlock",
      "tier_label": "Shares just unlocked",
      "amount": {
        "value_cr": 166.9,
        "low_cr": 166.9,
        "display": "₹166.90 Cr",
        "detail": "₹166.90 crore (estimate, valued at offer price)",
        "kind": "shares",
        "estimate": true,
        "reason": null,
        "source": "retained"
      },
      "timing": {
        "label": "Shares unlocked 9 Sep 2026 (67 days ago)",
        "status": "unlocked",
        "date_iso": "2026-09-09",
        "past": true
      },
      "confidence": {
        "level": "medium",
        "reason": "Not in the seller table; Holdings agree across 2 sections (promoter holdings, shareholding pattern)",
        "reasons": [
          "Not in the seller table"
        ]
      },
      "why": "Holds 1,234,500 shares before the offer; not selling in it",
      "brief_first_line": "Mallika R Iyer, Promoter Group, holds 1,234,500 shares before the offer and is not selling in it.",
      "household": null,
      "household_id": null,
      "rank": 1,
      "score": 58.415,
      "flags": [],
      "rm": {
        "status": "to_call",
        "follow_up": null,
        "note": ""
      },
      "position": 13
    }
  ],
  "count": 6,
  "interpreted_by": "assistant",
  "explanation": "Interpreted as: Role: Promoter · Shares just unlocked. 6 match."
}
```

## GET / PUT /api/rm/{event_id}/{person_id}

`status`: `to_call | called | follow_up | not_now | not_a_fit`. PUT body `{status?, note?, follow_up_date?}`;
omitted fields keep their value, `follow_up_date: ""` clears it. Stored in `api/state/rm.sqlite`
(`RM_STATE_PATH` overrides). Every call item also carries `rm: {status, follow_up, note}`.

PUT:

```json
{
  "event_id": "sedemac_ipo",
  "person_id": "p_manish_sharma",
  "status": "follow_up",
  "note": "Asked to call back after the board meeting",
  "follow_up_date": "2026-11-20",
  "updated_at": "2026-11-15T13:49:24Z"
}
```

GET:

```json
{
  "event_id": "sedemac_ipo",
  "person_id": "p_manish_sharma",
  "status": "follow_up",
  "note": "Asked to call back after the board meeting",
  "follow_up_date": "2026-11-20",
  "updated_at": "2026-11-15T13:49:24Z"
}
```

GET for someone never touched:

```json
{
  "event_id": "sedemac_ipo",
  "person_id": "p_mallika_r_iyer",
  "status": "to_call",
  "note": "",
  "follow_up_date": null,
  "updated_at": null
}
```

Bad status:

```json
{
  "status": 422,
  "body": {
    "detail": "status must be one of to_call, called, follow_up, not_now, not_a_fit"
  }
}
```

## GET /api/export/calls.csv

CRM export, one row per callable person in call order: stable ids, numeric ₹ crore (blank when
unknown), ISO dates, tier, RM status. First lines:

```csv
call_id,event_id,company,event_type,person_id,name,role,tier,amount_cr,amount_kind,amount_is_estimate,amount_text,money_date,timing,confidence,why,rm_status,follow_up_date,note
hd_fire_protect_limited_ipo_202610/p_kusum_harish_dharamshi,hd_fire_protect_limited_ipo_202610,HD Fire Protect Limited,ipo,p_kusum_harish_dharamshi,KUSUM HARISH DHARAMSHI,,cash_now,468.85,cash,no,₹468.85 crore,2026-10-21,Listing was due 21 Oct 2026 (25 days ago); listing notice not yet seen,medium,"Sells 17,300,800 shares in the offer for sale",to_call,,
paras_healthcare_limited_ipo_202610/p_dharminder_kumar_nagar,paras_healthcare_limited_ipo_202610,Paras Healthcare Limited,ipo,p_dharminder_kumar_nagar,Dr. Dharminder Kumar Nagar,,cash_now,300.00,cash,no,₹300.00 crore,2026-10-28,Listing was due 28 Oct 2026 (18 days ago); listing notice not yet seen,medium,"Sells 4,329,004 Equity Shares in the offer for sale",to_call,,
```

---
# v3a (2026-11-16): person trail and public enrichment

- `GET /api/people/{event_id}/{person_id}/trail` (view) -> `{event, person: {id, name}, run_id, generated_from: [file], steps: [...]}`.
  Steps, in order, each `{key, title, summary, status: "ok"|"warn"|"info"|"none", ...}`:
  `documents` (documents[{label,url,source_url,cached,pages}]), `pages` (sections[{section,label,why,pages[{pdf_index,printed_page,score,terms,used,doc_label}]}]),
  `quotes` (groups[{section,label,model,cached,calls,rows[{field,label,value,quote,evidence,page_corrected}]}]; `evidence` is the usual evidence object),
  `checks` (applied[], passed[], rejected[{label,value,section,reason}], conflicts[]), `identity` (names, merges, family, strong_model_checks, other_filings),
  `money` (amounts and timing_detail, same shapes as the call card), `rank` (tier, rank, score, parts[{label,value,note}], later, reasons),
  `brief` (written_by, model, prompt_version, attempts, placeholders, template_lines, lines), `enrichment` (linkedin, web, requests), `cost` (cost_usd, fresh_usd, calls, seconds, run).
  Built from outputs/<event>/{locate,extract,people,ranked,briefs,cost,trace}.json and the stored enrichment record; no model or network call.
- `GET /api/enrichment/status` (view) -> `{linkedin_enabled, web_enabled, token_configured, month, cap, used, remaining, requests, records, error, ready}`
  for the Sources page row (requests used / cap, LinkedIn switch). The token itself is never returned.
- `GET /api/people/{e}/{p}/enrichment` (view) -> `{record, running, estimate: {kinds: {linkedin|web: {allowed, reason, requests, cached, worst_case}}, total, cap, used, remaining, over_cap, month}, eligibility, status, web_label}`.
  `record.linkedin` = `{state: found|none|error|off, candidates: [{name, headline, city, positions, education, profile_url, fetched_at, match: likely|unconfirmed, reason}], fetched_at, error, requests}`;
  `record.web` = `{state, rows: [{title, source, date, url, label, fetched_at}], ...}`.
- `POST /api/people/{e}/{p}/enrichment` (edit_rm) `{kinds: ["linkedin","web"], confirmed_requests: n, refresh: true}` -> 202 `{started, kinds, requests_estimated}`;
  409 when confirmed_requests is below the server's own worst-case count, the monthly cap could be crossed, the holder is an organisation, or a lookup is already running. Poll the GET route until `running` is null.
## Admin (role admin, permission `ops`): pipeline console, health, accuracy

All of these answer 401 without a session and 403 for rm and viewer.

### GET /api/admin/events

`{count, events: [{event_id, company, event_type, type_label, supported, processed, people_count, running, last_run: {run_id, ended_at, status, total_cost_usd} | null}], steps: [{step, label}]}`

### POST /api/admin/run

Body `{event_id, step: "all"|"locate"|"extract"|"people"|"rank"|"brief"|"report", person_id?: string, fresh: boolean, confirm_token?: string}`.
`person_id` only with step `brief` (writes that person's brief and keeps the rest). `fresh: true` runs with an empty model
cache (a temp `LLM_CACHE_DIR`, removed after), so it costs money: without a `confirm_token` the answer is
`{needs_confirm: true, estimate: {low, high, seconds_low, seconds_high, breakdown, basis}, confirm_token, expires_at, message}` and nothing runs;
send the token back (same body) to start. The token is the chat's HMAC confirm token (kind `admin_run`, 10 minutes, once).
Started: `{needs_confirm: false, job_id, event_id, state, step, fresh, stream_url, log_url}`. 422 for an unsupported event,
unknown step, or a person not on the call list; 403 for a bad, expired or reused token.

### GET /api/jobs/{job_id}/stream (existing) and GET /api/admin/jobs/{job_id}/log

The first sends step events (single-step runs send one step, `index 1 of 1`). The second is SSE of the run's own output:
`data: {"line": "..."}` per line, ending with `data: {"state": "complete"|"failed"}`. `GET /api/admin/jobs` lists the latest jobs.

### GET /api/admin/events/{id}/history

`{event_id, runs: [{run_id, started_at, ended_at, wall_s, calls, cached_calls, cost_usd, status, error, snapshot}], diff}` (newest first;
from outputs/runs.csv). `diff` is the same as `GET /api/admin/events/{id}/diff?older=&newer=`:
`{event_id, runs_with_snapshot, older, newer, available, added: [{person_id, name, group, tier, amount}], removed: [...], changed: [{person_id, name, changes: [{field: amount|tier|list|rank, before, after}]}], unchanged}`.
When a run finishes, run.py saves `outputs/<event>/runs/<run_id>.json` (a copy of ranked.json); the diff compares the last two.
`available: false` until two runs have a snapshot.

### Data freshness (additive fields)

Every evidence ref (call card, event facts) gains `fetched_at` (UTC ISO or null), `age_days` and `stale` (older than `STALE_AFTER_DAYS`, default 14).
`GET /api/people/{e}/{p}` gains `freshness` and `GET /api/events/{id}` gains `freshness`:
`{documents: [{doc_sha, label, fetched_at, age_days, stale, stale_after_days}], oldest_fetched_at, newest_fetched_at, stale, stale_after_days}`;
each item of an event's `docs` also carries `fetched_at`, `age_days`, `stale`.

### GET /api/ops/health

`{checked_at, stale_after_days, running, scheduler: {available, ...}, sources: {refreshed_at, sources: [{id, name, status: ok|blocked|failed|disabled, items, reason, url}]},
caches: [{key, label, files, bytes}], spend: {date, today, all_time: {calls, cached_calls, paid_calls, cost_usd, cache_hit_rate}, daily_cap_usd, daily_cap_used, event_budget_usd, budget_mode, provider_cache: {hit_rate}},
brightdata: {available, requests, cap, used_share}, failed_runs: [{event_id, company, run_id, at, reason, running}]}`.
`scheduler` and `brightdata` use guarded imports (`api.scheduler`, `tools.brightdata`): `{available: false, reason}` when the module is not part of the build.
Retry on a failed run is `POST /api/admin/run` with `{event_id, step: "all", fresh: false}`.

### GET /api/ops/accuracy and POST /api/ops/accuracy/run

`{result: null}` until the first run, else `{result: {ran_at, overall: {people, fully_right, value_fields, hits, wrong, missing, invented, hit_rate}, fields: [{field, label, value_fields, hit, wrong, missing, blank_ok, invented, hit_rate}], events: [{event_id, people, value_fields, hits, hit_rate}], events_missing, misses: [{person_id, event_id, name, field, label, outcome: wrong|missing|invented, gold, pipeline, pages: [{label, url, cached, quote}]}]}}`.
The POST runs `eval.check_people` now (no model call) and stores `outputs/eval_people.json`. Each miss's `pages` link to the cached PDF page the gold read the value from.

### Production mode (APP_ENV=production)

`GET /api/auth/config` (public) -> `{production, demo_accounts}`; `demo_accounts` lists the demo emails the login page may offer.
`/api/auth/me` also returns `production`. No demo users are seeded unless `DEMO_ACCOUNTS=1`, and then all five, including the admin; a demo
email not offered is refused at sign-in (401). The first admin comes from ADMIN_EMAIL + ADMIN_PASSWORD. `events/example*.json` and events with a non-http(s) document link are excluded from every listing.
---
# v3c additions (2026-11-16): head of RMs, review queue, watchlists, model switcher

Roles: `admin`, `head` (new), `rm`, `viewer`. New permissions in `/api/auth/me`: `team`, `review` (admin + head). A head can
do everything an RM does; `ops` stays admin only. A head demo user (`head@finsight.demo`, `demo1234`) is seeded only when
`APP_ENV` is not production (no demo user is seeded in production).

- `rm_state` statuses add `meeting_booked` and `won`. `PUT /api/rm/{e}/{p}` accepts `won_amount_cr` (required the first time a
  row becomes `won`, 422 otherwise); rows now also carry `updated_by`, `first_called_at`, `won_amount_cr`.
- `GET /api/team` (team) -> `{as_of, total, rms: [{email, name, role, assigned, calls, meetings, won, won_cr,
  followups_due, days_to_first_call|null, days_samples}], event_types: [{event_type, type_label, ...same counts}],
  unassigned_calls}`. A lead belongs to the RM it is assigned to, else to whoever logged its outcome.
- `GET /api/team/rms` (edit_rm) -> `{rms: [{email, name, role}]}`; `GET /api/assignments` -> `{assignments: {"event/person":
  {rm_email, rm_name, assigned_by, assigned_at}}}`; `PUT /api/assignments/{e}/{p}` `{rm_email|null}` (team).
- `GET /api/review` (review) -> `{open, decided, items: [{id, kind: pair|holder|low, event, person_ids, names, title, why,
  pipeline, by, actions: [{action: confirm|reject|merge, label, value?}], decision: {label, by, at, action}|null, link?}]}`;
  `POST /api/review/decide` `{id, action}`; `DELETE /api/review?id=` (undo). Decisions are stored in the database and in
  `outputs/overrides.json`; `api/store.load_events()` applies that file to every event (hide / merge-hide / relabel), so every
  view shows the decision at once. Person cards gain `reviewed: [{label, by, at}]`.
- `GET /api/watch` -> `{follows: [{kind: person|company, key, label, origin_event_id, created_at}]}`; `POST /api/watch`
  `{kind, event_id, person_id?}`; `DELETE /api/watch?kind=&key=`.
- `GET /api/alerts` -> `{unread, items: [{id, kind: new|lockin|block|amount, title, detail, link, created_at, read}]}`
  (worked out from current data on every call); `POST /api/alerts/read` `{ids|null}`.
- Chat: `GET /api/chat/models` -> `{models: [{id, label, note, input_per_m, output_per_m, cache_read_per_m|null}], default_fast,
  default_strong, priced_from}`; `POST /api/chat` accepts `model` (allow-listed id; kept for the conversation; messages carry
  `meta.chat_model`); `POST /api/chat/compare` `{question, models: [a, b]}` -> `{question, results: [{model, text, cards,
  blocked|null, cost_usd, tokens, models_used, seconds}]}` (throwaway conversations; spending actions are reported as blocked).
