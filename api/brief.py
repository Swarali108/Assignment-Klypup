"""The daily brief and "since your last visit": GET /api/me/brief, POST /api/me/brief/shown, GET /api/me/since.

A short brief for the first sign-in of each local day, stored per user and per date in the database.
The cheap chat model writes 3 to 5 bullets that contain only {placeholders}; this module fills every placeholder
from the data (people, amounts, dates), so the model never types a number or a name. A bullet that carries a
digit, an unknown placeholder or an unknown topic is thrown away; with no key, a failure, or too few good bullets
the same bullets come from fixed templates. Nothing here reads from memory.

Routes (a session is needed; refresh needs the admin role):
  GET  /api/me/brief?day=YYYY-MM-DD[&refresh=1]  the day's brief (cached per user per day) + whether it was shown
  POST /api/me/brief/shown {day}                 remember it was shown, so the sheet opens once a day
  GET  /api/me/since                             {last_visit, new_events, new_people} for the home date line

"Last visit" is the start of this user's previous session: a gap of more than 30 minutes between two calls
starts a new one (user_seen keeps the current and the previous start).
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api import auth, db, prefs, rm_state, store, views

router = APIRouter()

MODEL = "openai/gpt-6-luna"
MODEL_SHORT = "gpt-6-luna"
PROMPT_VERSION = "brief-v1"
SESSION_GAP = timedelta(minutes=30)
FALLBACK_DAYS = 7  # no earlier visit on record: "new" means the last week
SOON_DAYS = 7

TABLES = (
    """CREATE TABLE IF NOT EXISTS user_brief (
        email TEXT NOT NULL, day TEXT NOT NULL, payload TEXT NOT NULL, shown INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, PRIMARY KEY (email, day))""",
    """CREATE TABLE IF NOT EXISTS user_seen (
        email TEXT PRIMARY KEY, current_start TEXT NOT NULL, last_seen TEXT NOT NULL, previous_start TEXT)""",
)
_ready: set[str] = set()
_lock = threading.Lock()


def _ensure() -> None:
    """Create this module's tables once per database."""
    key = db._key()
    if key in _ready:
        return
    with _lock:
        if key in _ready:
            return
        with db.connect() as conn:
            for statement in TABLES:
                conn.execute(statement)
        _ready.add(key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------- last visit ----------

def touch(email: str) -> datetime | None:
    """Record a visit now; return when the previous session started (None on the very first visit)."""
    _ensure()
    now = _now()
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM user_seen WHERE email = %s", (email,))
        if not rows:
            conn.execute("INSERT INTO user_seen (email, current_start, last_seen, previous_start) VALUES (%s, %s, %s, NULL) ON CONFLICT (email) DO NOTHING",
                         (email, _iso(now), _iso(now)))
            return None
        row = rows[0]
        last = _parse(row["last_seen"])
        if last is None or now - last > SESSION_GAP:
            conn.execute("UPDATE user_seen SET previous_start = current_start, current_start = %s, last_seen = %s WHERE email = %s",
                         (_iso(now), _iso(now), email))
            return _parse(row["current_start"])
        conn.execute("UPDATE user_seen SET last_seen = %s WHERE email = %s", (_iso(now), email))
        return _parse(row["previous_start"])


def _stamps(events: list[dict]) -> dict[str, datetime]:
    """event_id -> when it came in: the day discovery first saw it (same basis as "new this week"), else its file time."""
    out: dict[str, datetime] = {}
    for event in events:
        if not event["processed"]:
            continue
        first = str((event["raw"].get("discovery") or {}).get("first_seen") or "")[:10]
        try:
            out[event["spec"].event_id] = datetime.fromisoformat(first).replace(tzinfo=timezone.utc)
            continue
        except ValueError:
            pass
        try:
            path = store.OUTPUTS_DIR / event["spec"].event_id / "people.json"
            out[event["spec"].event_id] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
    return out


def coverage_key(coverage: dict | None) -> str:
    """A stable text for an RM's coverage (event types + minimum ticket); a changed key means the brief is stale."""
    coverage = coverage or {}
    return json.dumps({"types": sorted(coverage.get("event_types") or []), "min": coverage.get("min_ticket_cr") or None})


def fits_coverage(item: dict, coverage: dict | None) -> bool:
    """The same test as the web app's fitsCoverage: event type, then the minimum ticket. No coverage: everything fits."""
    coverage = coverage or {}
    types = coverage.get("event_types") or []
    # A Today slot that folds a holder's repeat sales fits when any of its trades does.
    kinds = {item["event"]["type"], *(t["event"]["type"] for t in item.get("trades") or [])}
    if types and not kinds & set(types):
        return False
    minimum = coverage.get("min_ticket_cr")
    return not (minimum and max(item["amount"]["value_cr"] or 0, item.get("trades_total_cr") or 0) < minimum)


def since_figures(events: list[dict], items: list[dict], previous: datetime | None, coverage: dict | None = None) -> dict:
    """{last_visit, label, new_events, new_people, new_event_names}: call lists written after the last visit.
    With a coverage, only people (and the events that hold them) inside it are counted."""
    # No earlier visit: the last 7 days counted from the app's date (day granularity, the same basis as the Today KPI).
    cutoff = previous or datetime.combine(views.as_of() - timedelta(days=FALLBACK_DAYS), datetime.min.time(), timezone.utc)
    stamps = _stamps(events)
    fresh = {eid for eid, stamp in stamps.items() if stamp >= cutoff} if previous is None else {eid for eid, stamp in stamps.items() if stamp > cutoff}
    covered = [i for i in items if fits_coverage(i, coverage)] if coverage else items
    people = sum(1 for i in covered if i["event"]["id"] in fresh)
    if coverage:
        fresh &= {i["event"]["id"] for i in covered}
    companies = []
    for event in events:
        if event["spec"].event_id in fresh and event["spec"].company not in companies:
            companies.append(event["spec"].company)
    return {"last_visit": _iso(previous) if previous else None, "since_known": previous is not None,
            "new_events": len(fresh), "new_people": people, "new_event_names": companies[:3]}


# ---------- the facts (all numbers and names come from here) ----------

def _cr(value: float | None, approx: bool = False) -> str:
    text = views.cr_text(Decimal(str(value))) if value is not None else ""
    return f"about {text}" if approx and text else text


def _proper(name: str | None) -> str:
    """A name as printed; an ALL-CAPS name is title-cased."""
    text = (name or "").strip()
    return text.title() if text and text == text.upper() else text


def _nice_day(iso: str) -> str:
    return views.nice_date(iso)


def _new_sentence(since: dict, previous: datetime) -> str:
    """'3 new money events since your last visit on 12 Nov, with 5 new people to call.' (counts from the data)."""
    events, people = since["new_events"], since["new_people"]
    return (f"{events} new money {'event' if events == 1 else 'events'} since your last visit on "
            f"{_nice_day(previous.date().isoformat())}, with {people} new {'person' if people == 1 else 'people'} to call.")


def gather(email: str, role: str, previous: datetime | None) -> dict:
    """{topic: {"values": {placeholder: text}, "link": path}} for every topic that has something to say."""
    events, rm = store.load_events(), rm_state.all_states()
    coverage = prefs.get_preferences(email)
    has_coverage = bool(coverage.get("event_types") or coverage.get("min_ticket_cr"))
    everyone = views.all_items(events, rm)
    items = [i for i in everyone if fits_coverage(i, coverage)] if has_coverage else everyone
    queue = [i for i in views.today_queue(events, rm) if fits_coverage(i, coverage)] if has_coverage else views.today_queue(events, rm)
    perms = auth.permissions_for(role)
    today = views.as_of()
    facts: dict[str, dict] = {}

    since = since_figures(events, everyone, previous, coverage if has_coverage else None)
    # "New since your last visit" is written by code, never by the model, and only when there is a last visit to compare with.
    if previous is not None and since["new_events"]:
        facts["new"] = {"link": "/events", "values": {"text": _new_sentence(since, previous)}}

    open_queue = [i for i in queue if i["rm"]["status"] in ("to_call", "follow_up")]
    cash = [i for i in open_queue if views.bucket(i) == "cash_now"] or open_queue
    top, names = [], set()
    for item in cash:  # the same person in two events is one call
        key = _proper(item["person"]["name"]).lower()
        if key not in names:
            names.add(key)
            top.append(item)
    top = top[:3]
    if top:
        values: dict[str, str] = {"call_count": str(len(top))}
        for n, item in enumerate(top, 1):
            amount = item["amount"]
            values[f"call{n}_name"] = _proper(item["person"]["name"])
            values[f"call{n}_amount"] = amount["display"] if amount["value_cr"] is not None else "an amount not yet disclosed"
            values[f"call{n}_company"] = item["event"]["company"]
        facts["calls"] = {"link": "/today", "values": values}

    horizon = (today + timedelta(days=SOON_DAYS)).isoformat()
    soon = [i for i in items if i["timing"].get("date_iso") and today.isoformat() < i["timing"]["date_iso"] <= horizon]
    if soon:
        known = [i["amount"]["value_cr"] for i in soon if i["amount"]["value_cr"] is not None]
        first = min(i["timing"]["date_iso"] for i in soon)
        approx = any(i["amount"].get("estimate") or i["amount"]["kind"] == "shares" for i in soon if i["amount"]["value_cr"] is not None)
        facts["soon"] = {"link": "/calendar", "values": {
            "soon_people": str(len(soon)), "soon_first": _nice_day(first),
            "soon_amount": _cr(round(sum(known), 2), approx) if known else "amounts not yet disclosed"}}

    try:
        from api import watch

        unread = [a for a in watch.alerts(email)["items"] if not a["read"]]
    except Exception:  # the watchlist is optional here
        unread = []
    if unread:
        facts["watch"] = {"link": "/", "values": {"watch_count": str(len(unread)), "watch_first": unread[0]["title"]}}

    if perms["review"]:
        from api import overrides

        open_review = sum(1 for i in overrides.queue(events) if not i["decision"])
        if open_review:
            facts["review"] = {"link": "/review", "values": {"review_count": str(open_review)}}

    if perms["ops"]:
        try:
            from api import ops_health

            spend = ops_health.spend()
            cap = spend.get("daily_cap_usd")
            if cap:
                facts["spend"] = {"link": "/ops/health", "values": {
                    "spend_today": f"${spend['today']['cost_usd']:.2f}", "spend_cap": f"${cap:.2f}"}}
        except Exception:
            pass
    return {"facts": facts, "since": since}


# ---------- the words ----------

TEMPLATES = {
    "new": "{text}",
    "calls": "Call first: {call1_name} ({call1_amount}, {call1_company}).",
    "soon": "{soon_people} people have money moving in the next 7 days, {soon_amount}; the first date is {soon_first}.",
    "watch": "{watch_count} updates on names you follow, starting with: {watch_first}.",
    "review": "{review_count} items are waiting in the review queue.",
    "spend": "Model spend today is {spend_today} against a {spend_cap} daily cap.",
}
HINTS = {
    "calls": "the top people to call today, cash in hand first (call1 is the most important; call2 and call3 may be missing)",
    "soon": "money moving in the next 7 days",
    "watch": "news on names the person follows",
    "review": "items waiting for the person's review",
    "spend": "model spend today against the daily cap",
}
ORDER = ("calls", "new", "soon", "watch", "review", "spend")


class _Bullet(BaseModel):
    topic: str
    text: str = Field(description="One short sentence using only {placeholders} for names, amounts, dates and counts.")


class DailyBrief(BaseModel):
    """What the model returns: bullets, each tied to one topic."""

    bullets: list[_Bullet]


def _placeholders(topic: str, facts: dict) -> list[str]:
    return list(facts[topic]["values"])


def _template(topic: str, facts: dict) -> str:
    """The fixed sentence for a topic; the calls line names as many of the top three as there are."""
    if topic != "calls":
        return TEMPLATES[topic]
    count = int(facts["calls"]["values"].get("call_count") or 1)
    parts = [f"{{call{n}_name}} ({{call{n}_amount}})" for n in range(1, count + 1)]
    return "Call first: " + ", ".join(parts[:-1]) + (" and " if count > 1 else "") + parts[-1] + "."


def _fill(text: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), text)


def _valid(bullet: dict, facts: dict) -> bool:
    """A bullet is kept only when its topic exists, every placeholder is one of that topic's, and it has no digit."""
    topic, text = bullet.get("topic"), str(bullet.get("text") or "")
    if topic not in facts or not text or len(text) > 240:
        return False
    names = re.findall(r"\{(\w+)\}", text)
    if any(n not in facts[topic]["values"] for n in names):
        return False
    bare = re.sub(r"\{\w+\}", "", text)
    return not re.search(r"\d|₹|\$|\{|\}", bare)


def _write_with_model(facts: dict, turn_id: str) -> tuple[list[dict], float]:
    """Bullets (topic + placeholder text) and the real cost in USD. Raises on any model failure."""
    from api.chat import llm

    topics = [t for t in ORDER if t in facts]
    lines = "\n".join(f"- {t}: {HINTS[t]}. Placeholders: " + ", ".join("{" + p + "}" for p in _placeholders(t, facts))
                      for t in topics)
    system = ("You write the morning brief for a private-bank relationship manager. Reply as JSON "
              '{"bullets":[{"topic":"...","text":"..."}]}. Write 3 to 5 bullets, at most one per topic, in the order given. '
              "Each is one plain sentence of at most 22 words. Names, amounts, dates and counts MUST be written only as "
              "the {placeholders} listed for that topic; never type a digit, a rupee or dollar sign, or a name yourself. "
              "Use only the placeholders listed for the bullet's own topic. No emoji, no jargon, no greeting.")
    user = f"Topics available today:\n{lines}"
    parsed, cost, _calls = llm.call("brief", MODEL, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                    DailyBrief, PROMPT_VERSION, turn_id)
    return [b for b in parsed.get("bullets") or [] if isinstance(b, dict)], cost


CODE_ONLY = ("new",)  # topics whose sentence is built in code from the data, never by the model


def compose(facts: dict, turn_id: str) -> tuple[list[dict], str, float]:
    """(bullets [{topic, text, link}], written_by, cost_usd): the model's bullets, else the templates.
    The "new since your last visit" line is always the code's own sentence."""
    model_facts = {t: v for t, v in facts.items() if t not in CODE_ONLY}
    topics = [t for t in ORDER if t in model_facts]
    bullets: list[dict] = []
    written_by, cost = "code", 0.0
    if topics:
        try:
            raw, cost = _write_with_model(model_facts, turn_id)
            seen: set[str] = set()
            for b in raw:
                if _valid(b, model_facts) and b["topic"] not in seen:
                    seen.add(b["topic"])
                    bullets.append({"topic": b["topic"], "text": _fill(b["text"], model_facts[b["topic"]]["values"])})
            if len(bullets) >= min(3, len(topics)):
                written_by = MODEL_SHORT
                bullets = bullets[:4]
            else:
                bullets = []
        except Exception:
            bullets, cost = [], 0.0
    if not bullets:
        written_by = "code"
        bullets = [{"topic": t, "text": _fill(_template(t, model_facts), model_facts[t]["values"])} for t in topics][:4]
    for topic in CODE_ONLY:
        if topic in facts:
            bullets.append({"topic": topic, "text": _fill(_template(topic, facts), facts[topic]["values"])})
    bullets.sort(key=lambda b: ORDER.index(b["topic"]))
    for b in bullets:
        b["link"] = facts[b["topic"]]["link"]
    return bullets, written_by, round(cost, 6)


def build(email: str, role: str, previous: datetime | None, day: str) -> dict:
    """The brief payload for one user and day (not yet stored)."""
    found = gather(email, role, previous)
    bullets, written_by, cost = compose(found["facts"], f"brief-{day}-{email}")
    top = found["facts"].get("calls", {}).get("values", {})
    ask = "Walk me through today's brief: who should I call first, and why now?"
    if top.get("call1_name"):
        ask = f"Walk me through today's brief. Why is {top['call1_name']} worth a call first?"
    return {"day": day, "coverage_key": coverage_key(prefs.get_preferences(email)), "bullets": bullets, "written_by": written_by, "model": MODEL if written_by != "code" else None,
            "cost_usd": cost, "ask_prompt": ask, "since": found["since"], "as_of": views.as_of().isoformat(),
            "generated_at": _iso(_now())}


# ---------- storage and routes ----------

def _valid_day(day: str) -> str:
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(422, "day must be YYYY-MM-DD")
    return day


@router.get("/api/me/brief")
def get_brief(day: str, refresh: int = Query(0), user: dict = auth.VIEW_USER) -> dict:
    """The brief for this user's local day, written once and kept; ?refresh=1 (admin) writes it again."""
    _valid_day(day)
    if refresh and user["role"] != "admin":
        raise HTTPException(403, "Only an admin can rewrite the brief")
    previous = touch(user["email"])
    with db.connect() as conn:
        rows = conn.query("SELECT payload, shown FROM user_brief WHERE email = %s AND day = %s", (user["email"], day))
    if rows and not refresh:
        stored = json.loads(rows[0]["payload"])
        # A brief written for another coverage is stale: write it again (the "already shown today" flag is kept).
        if stored.get("coverage_key") == coverage_key(prefs.get_preferences(user["email"])):
            return {**stored, "shown": bool(rows[0]["shown"]), "cached": True}
    payload = build(user["email"], user["role"], previous, day)
    shown = int(rows[0]["shown"]) if rows else 0
    with db.connect() as conn:
        conn.execute("DELETE FROM user_brief WHERE email = %s AND day = %s", (user["email"], day))
        conn.execute("INSERT INTO user_brief (email, day, payload, shown, created_at) VALUES (%s, %s, %s, %s, %s)",
                     (user["email"], day, json.dumps(payload), shown, _iso(_now())))
    return {**payload, "shown": bool(shown), "cached": False}


class ShownIn(BaseModel):
    """POST /api/me/brief/shown body."""

    day: str


@router.post("/api/me/brief/shown")
def mark_shown(body: ShownIn, user: dict = auth.VIEW_USER) -> dict:
    """The sheet was opened for this day; it will not open by itself again today."""
    _ensure()
    with db.connect() as conn:
        conn.execute("UPDATE user_brief SET shown = 1 WHERE email = %s AND day = %s", (user["email"], _valid_day(body.day)))
    return {"ok": True}


@router.get("/api/me/since")
def get_since(user: dict = auth.VIEW_USER) -> dict:
    """What changed since this user's previous visit: {last_visit, since_known, new_events, new_people}."""
    previous = touch(user["email"])
    events = store.load_events()
    return since_figures(events, views.all_items(events, rm_state.all_states()), previous)
