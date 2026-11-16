"""Build gallery/stub fixtures in the API contract shape (api/CONTRACT.md) from real pipeline outputs.
Amounts, shares, prices and dates are read from outputs/. Hand-written: the confidence reasons,
"why now", event statuses for processing/failed/not-supported demo cards, and new_events_this_week.
If a CONTRACT.md path is given, its example call card, events and ask answer are used verbatim.
Run from the repo root:
  .venv/bin/python web/scripts/make_fixtures.py [path/to/api/CONTRACT.md]"""
import hashlib, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
MONTHS = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def load(ev, name):
    return json.loads((OUT / ev / name).read_text())

def cr(text):
    m = re.search(r"₹([\d,]+\.?\d*) crore", text or "")
    return float(m.group(1).replace(",", "")) if m else None

def first_date(text):
    m = re.search(r"(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})", text or "")
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m else None

def tier_of(p):
    k = (p.get("trigger") or {}).get("kind")
    if p["timing_status"] == "in_hand" or k == "proceeds" or p["timing_display"].startswith("in hand"):
        return "cash_now", "Cash in hand"
    if p["timing_status"] == "unlocked" and float(p["money_now_crore"] or 0) > 0:
        return "unlock", "Shares just unlocked"
    return "holding", "Holds shares"

def timing_of(p):
    raw = p["timing_display"]
    label = raw.split(" (")[0].replace("pre-Offer capital: ", "").replace("Minimum Promoters' Contribution: ", "")
    label = label[0].upper() + label[1:]
    status = {"in_hand": "in_hand", "unlocked": "unlocked", "after_date": "past"}.get(p["timing_status"], "unknown")
    if "locked until" in raw:
        status = "locked"
    if p["timing_status"] == "unknown":
        label = "Timing not printed in the filing"
    d = first_date(raw)
    return {"label": label, "status": status, "date_iso": d, "past": bool(d and d < "2026-11-15")}

CONF_REASON = {
    "high": "Name, shares and price all read from the same filing table",
    "medium": "Shares verified; amount is valued at the offer price",
    "low": "Only part of the holding could be matched to a table row",
}

def item(ev, company, etype, p, brief, household=None):
    tier, tier_label = tier_of(p)
    value = cr(p["amount_display"])
    shares = "shares, not cash" in p["amount_display"]
    reason = None
    if value is None:
        reason = "The notice prints one total for all sellers, not each seller's own shares"
    est = "estimate" in p["amount_display"] or "up to" in p["amount_display"].lower()
    return {
        "id": f"{ev}/{p['person_id']}",
        "event": {"id": ev, "company": company, "type": etype, "type_label": {"ipo": "IPO", "ofs": "Offer for sale", "buyback": "Buyback"}[etype]},
        "person": {"id": p["person_id"], "name": p["name_as_printed"],
                   "role": None if p.get("role_as_printed") in (None, "None") else p["role_as_printed"],
                   "holder_type": p["holder_type"]},
        "tier": tier, "tier_label": tier_label,
        "amount": {"value_cr": value, "low_cr": value, "display": (f"₹{value:,.2f} Cr" if value is not None else "Amount not disclosed"),
                   "detail": p["amount_display"] if value is not None else None,
                   "kind": "shares" if shares else "cash", "estimate": est, "reason": reason,
                   "source": "retained" if shares else "proceeds"},
        "timing": timing_of(p),
        "confidence": {"level": p["confidence"], "reason": CONF_REASON[p["confidence"]], "reasons": [CONF_REASON[p["confidence"]]]},
        "why": p["why_money"][0].upper() + p["why_money"][1:],
        "brief_first_line": (brief or {}).get("lines", [""])[0],
        "household_id": household,
        "rank": p["rank"],
        "flags": [],
        "rm": {"status": "to_call", "follow_up": None, "note": ""},
    }

def event_items(ev, company, etype, limit=None):
    ranked = load(ev, "ranked.json")
    briefs = {b["person_id"]: b for b in load(ev, "briefs.json")["briefs"]}
    people = {q["person_id"]: q for q in load(ev, "people.json")["people"]}
    rows = []
    for p in ranked["callable"][:limit]:
        fg = (people.get(p["person_id"]) or {}).get("family_group") or {}
        rows.append(item(ev, company, etype, p, briefs.get(p["person_id"]), fg.get("id")))
    return rows

sed = event_items("sedemac_ipo", "SEDEMAC Mechatronics", "ipo")
spn = event_items("spacenet_ofs", "Spacenet Enterprises India", "ofs")

# household: Manish Sharma + Priyanka Manish Sharma (family_3 in people.json)
manish = next(r for r in sed if r["person"]["id"] == "p_manish_sharma")
priyanka = next(r for r in sed if r["person"]["id"] == "p_priyanka_manish_sharma")
def member(r):
    return {"id": r["id"], "name": r["person"]["name"], "role": r["person"]["role"], "tier": r["tier"], "amount": r["amount"]}
hh = {"id": "sedemac_ipo:family_3", "label": "Sharma household", "reason": "'Priyanka Manish Sharma' contains 'Manish Sharma'",
      "members": [member(manish), member(priyanka)], "printed_members": ["Manish Sharma", "Priyanka Manish Sharma"]}
household = dict(manish, household=hh, household_id=hh["id"], members=[member(priyanka)],
                 household_total_cr=None)

solo = [r for r in sed if r["household_id"] != "family_3"]
today = [r for r in solo if r["tier"] == "cash_now"][:3] + [household] + [r for r in solo if r["tier"] == "unlock"][:2] + [r for r in solo if r["tier"] == "holding"][:1] + spn[:1]
summary = {
    "people_to_call": len([r for r in sed + spn]),
    "cash_now_cr": round(sum(r["amount"]["value_cr"] or 0 for r in sed if r["tier"] == "cash_now"), 2),
    "new_events_this_week": 3, "events_processed": 16, "as_of": "2026-11-15", "as_of_display": "15 Nov 2026",
}

# person card: Manish Sharma, every number from briefs.json fields / people.json evidence
mp = next(q for q in load("sedemac_ipo", "people.json")["people"] if q["person_id"] == "p_manish_sharma")
mb = next(b for b in load("sedemac_ipo", "briefs.json")["briefs"] if b["person_id"] == "p_manish_sharma")
RHP = "https://www.icicisecurities.com/Upload/ArticleAttachments/SEDEMAC%20MECHATRONICS%20LIMITED%20-%20RHP.pdf"
sha = hashlib.sha256(RHP.encode()).hexdigest()
def ev_ref(e):
    return {"doc_sha": hashlib.sha256(e["source_url"].encode()).hexdigest(), "doc_label": "Red herring prospectus" if e["source_url"] == RHP else "Allotment notice",
            "pdf_index": e["pdf_index"], "printed_page": e["printed_page"] or None, "quote": e["quote"], "url": e["source_url"] + f"#page={e['pdf_index']}"}
evs = {e["field"] + ":" + e["section"]: ev_ref(e) for e in mp["evidence"]}
price_ev = ev_ref(load("sedemac_ipo", "people.json")["price_basis"]["inputs"][0]["evidence"][0])
f = mb["fields"]
def working(s):
    m = re.search(r"\(([^()]*(?:\([^()]*\))?[^()]*= ₹[\d.,]+ crore)\)", s)
    return m.group(1) if m else None
person = {
    "event": {"id": "sedemac_ipo", "company": "SEDEMAC Mechatronics", "type": "ipo"},
    "person": manish["person"], "tier": manish["tier"], "tier_label": manish["tier_label"],
    "amount": manish["amount"], "timing": manish["timing"], "confidence": manish["confidence"],
    "why_now": "Offer proceeds have been in hand since listing; the remaining shares unlock in two stages.",
    "brief": mb["lines"],
    "amounts": [
        {"key": "proceeds", "label": "Proceeds from the sale", "value_cr": cr(f["proceeds"]), "display": f"₹{cr(f['proceeds']):,.2f} Cr",
         "working": working(f["proceeds"]), "estimate": True, "inputs": [
             {"label": "Shares offered", "value": mp["shares_offered"], "evidence": [evs["shares_offered:selling_shareholders"]]},
             {"label": "Offer price", "value": f"₹{int(load('sedemac_ipo', 'people.json')['price_basis']['high']):,}", "evidence": [price_ev]}]},
        {"key": "gain", "label": "Gain before costs and tax", "value_cr": cr(f["gain"]), "display": f"₹{cr(f['gain']):,.2f} Cr",
         "working": working(f["gain"]), "estimate": True, "inputs": [
             {"label": "Average cost per share", "value": "₹" + mp["waca_per_share"], "evidence": [evs["waca_per_share:waca"]]}]},
        {"key": "retained", "label": "Shares kept, at offer price", "value_cr": cr(f["retained"]), "display": f"₹{cr(f['retained']):,.2f} Cr",
         "working": working(f["retained"]), "estimate": True, "inputs": [
             {"label": "Shares held before the offer", "value": mp["shares_held_pre_offer"], "evidence": [evs["shares_held_pre_offer:promoter_holding"]]}]},
    ],
    "household": [{"id": priyanka["person"]["id"], "name": priyanka["person"]["name"], "role": priyanka["person"]["role"],
                   "reason": "Shares the name Manish Sharma", "amount": priyanka["amount"]}],
    "flags": ["Employee-portion shares sold at a discount, so actual proceeds are slightly lower"],
    "rm": {"status": "to_call", "note": "", "follow_up_date": None, "updated_at": None},
}
evidence_sample = evs["shares_offered:selling_shareholders"]

tl = load("sedemac_ipo", "timeline.json")
cost = load("sedemac_ipo", "cost.json")["totals"]
events = [
    {"id": "sedemac_ipo", "company": "SEDEMAC Mechatronics", "type": "ipo", "status": "ready", "status_reason": None,
     "people_count": len(sed), "cash_cr": summary["cash_now_cr"], "listing_date": "2026-03-11",
     "cost_usd": cost["cost_usd"], "run_seconds": round(tl["total_s"], 1),
     "doc": [{"sha": sha, "label": "Red herring prospectus", "scanned": False}, {"sha": price_ev["doc_sha"], "label": "Allotment notice", "scanned": False}]},
    {"id": "spacenet_ofs", "company": "Spacenet Enterprises India", "type": "ofs", "status": "ready", "status_reason": None,
     "people_count": len(spn), "cash_cr": None, "listing_date": None, "doc": []},
    {"id": "genus_power_infrastructure_limited_buyback_202610", "company": "Genus Power Infrastructures", "type": "buyback", "status": "scanned",
     "status_reason": "Scanned filing: text not readable yet", "people_count": 0, "cash_cr": None, "listing_date": None, "doc": [{"sha": "", "label": "Buyback announcement", "scanned": True}]},
    {"id": "paras_healthcare_limited_ipo_202610", "company": "Paras Healthcare", "type": "ipo", "status": "processing", "status_reason": None,
     "people_count": 0, "cash_cr": None, "listing_date": None, "doc": []},
    {"id": "tonbo_imaging_india_limited_ipo_202610", "company": "Tonbo Imaging India", "type": "ipo", "status": "failed",
     "status_reason": "The prospectus link stopped responding, so the last good call list is kept", "people_count": 0, "cash_cr": None, "listing_date": None, "doc": []},
    {"id": "esop_example", "company": "Example ESOP buyback", "type": "buyback", "status": "not_supported",
     "status_reason": "Employee stock buybacks are not covered yet", "people_count": 0, "cash_cr": None, "listing_date": None, "doc": []},
]
steps = [{"step": s["step"], "seconds": round(s["seconds"], 2), "cost_usd": s["cost_usd"]} for s in tl["steps"]]

# --- contract shape for the hand-assembled card and events ---
person["brief"] = {"lines": mb["lines"], "written_by": "assistant"}
person["id"] = manish["id"]; person["household"] = hh; person["household_id"] = hh["id"]
person["why"] = manish["why"]; person["brief_first_line"] = manish["brief_first_line"]
for a, k in zip(person["amounts"], ["proceeds", "gain", "retained"]):
    a["short"] = a["display"]; a["display"] = f[k].split(" (")[0]; a["status"] = "computed"; a["reason"] = None; a["caveats"] = []
person["household"] = hh
person.pop("flags", None); person["flags"] = []
for e in events:
    e["docs"] = [{"doc_sha": d["sha"], "label": d["label"], "url": f"/api/docs/{d['sha']}.pdf", "scanned": d["scanned"],
                  "scanned_label": "Scanned filing: text not readable yet" if d["scanned"] else None} for d in e.pop("doc")]
    e["empty_reason"] = e["status_reason"] if e["people_count"] == 0 else None
    e["type_label"] = {"ipo": "IPO", "ofs": "Offer for sale", "buyback": "Buyback"}[e["type"]]
ask = None

# --- prefer the API's own documented examples when the contract is available ---
if len(sys.argv) > 1 and pathlib.Path(sys.argv[1]).exists():
    c = pathlib.Path(sys.argv[1]).read_text()
    def ex(h):
        sec = c[c.index(h):]; sec = sec[:sec.index("\n## ", 5)]
        return [json.loads(m) for m in re.findall(r"```json\n(.*?)\n```", sec, re.S)]
    person = ex("## GET /api/people/{event_id}")[0]
    api_events = ex("## GET /api/events\n")[0]["events"]
    events = api_events + [e for e in events if e["status"] in ("processing", "failed", "not_supported")]
    ask = ex("## POST /api/ask")[0]
    evidence_sample = next(i["evidence"][0] for a in person["amounts"] for i in a["inputs"] if i["evidence"])

out = {"summary": summary, "today": today, "person": person, "evidence": evidence_sample, "events": events, "steps": steps, "ask": ask}
dst = ROOT / "web/lib/fixtures.json"
dst.write_text(json.dumps(out, indent=1, ensure_ascii=False))
print("wrote", dst, len(today), "today items;", [r["person"]["name"] + ":" + r["tier"] for r in today])
print(person["amounts"])
