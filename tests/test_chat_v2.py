"""Tier-1 checks for chat v2 (api/CHAT_CONTRACT.md v2): memory and focus binding, time windows, call scripts,
compression, verified streaming, prompt-cache accounting, exports. No network, no API key: every model entry point
is replaced, and a test that needs model words gets a stand-in that returns fixed text. No names are written
here: people come from the stored data (the top of today's queue)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, timedelta

import pytest

HOME_CHIPS = {"Who came into money this week?", "Cash in hand above ₹50 Cr",
              "Process a new IPO from a link", "Upcoming money dates", "Process a new filing from a link"}


def _events(reply) -> list[tuple[str, dict]]:
    out = []
    for block in reply.text.split("\n\n"):
        lines = [line for line in block.split("\n") if line]
        if len(lines) >= 2 and lines[0].startswith("event: ") and lines[1].startswith("data: "):
            out.append((lines[0][7:], json.loads(lines[1][6:])))
    return out


def _of(events, kind):
    return [data for name, data in events if name == kind]


def _text(events) -> str:
    return "".join(d["delta"] for d in _of(events, "text"))


@pytest.fixture()
def chat(as_role, tmp_path, monkeypatch):
    """Clients per role, isolated cost log and model cache; any model call fails the test unless stood in."""
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    from api.chat import llm as chat_llm
    from tools import llm as tools_llm

    def no_model(*args, **kwargs):
        raise AssertionError("a model was called")

    monkeypatch.setattr(chat_llm, "call", no_model)
    monkeypatch.setattr(tools_llm, "llm_call", no_model)
    monkeypatch.setattr(tools_llm, "llm_stream", no_model)
    return as_role


class Talk:
    """One conversation over HTTP."""

    def __init__(self, client):
        self.client, self.cid = client, None

    def send(self, **body) -> list[tuple[str, dict]]:
        events = _events(self.client.post("/api/chat", json={"conversation_id": self.cid, **body}))
        assert not _of(events, "error"), _of(events, "error")
        self.cid = _of(events, "meta")[0]["conversation_id"]
        return events


def _model_refuses(monkeypatch):
    """The provider fails (as tools.llm reports it): the code template must take over."""
    from api.chat import llm as chat_llm
    from tools.llm import LLMError

    def refuse(*args, **kwargs):
        raise LLMError("model unavailable in tests")

    monkeypatch.setattr(chat_llm, "call", refuse)


def _top(client) -> dict:
    return client.get("/api/today?limit=1").json()["items"][0]


def _script_standin(monkeypatch, calls: list):
    """The strong model writing a script: placeholders, plus a digit it should not have typed."""
    from api.chat import llm as chat_llm

    def write(step, model, messages, schema, version, turn_id):
        calls.append({"step": step, "messages": messages})
        assert step == "script"
        return ({"opening": ["Hello {first_name}, congratulations on the {company} {event}."],
                 "why_now": ["{tier}: {amount}. {timing}.", "They made 999 crore, maybe."],
                 "questions": ["What are your plans?", "Who else advises you?", "What matters most this year?"],
                 "objections": [{"objection": "I have an advisor.", "answer": "A second view costs nothing."}],
                 "message": [], "next_step": ["Book a meeting within 3 days."]}, 0.0, 1)

    monkeypatch.setattr(chat_llm, "call", write)


# ---------- focus binding ----------

def test_script_for_the_call_after_a_person_turn_binds_to_that_person(chat, monkeypatch):
    client = chat("rm")
    top = _top(client)
    name, amount = top["person"]["name"], top["amount"]["display"]
    talk = Talk(client)
    first = talk.send(message=f"What money does {name} have?")
    assert _of(first, "focus")[0]["focus"][0]["person_id"] == top["person"]["id"]

    calls: list = []
    _script_standin(monkeypatch, calls)
    events = talk.send(message="ready me a script for the call")
    assert not _of(events, "clarify")
    scripts = [c for c in _of(events, "cards") if c["kind"] == "script"]
    assert len(scripts) == 1 and scripts[0]["person"]["person_id"] == top["person"]["id"]
    lines = [line for section in scripts[0]["sections"] for line in section["lines"]]
    assert any(amount in line for line in lines)  # code filled {amount} from the call card
    assert not any("999" in line or " 3 days" in line for line in lines)  # digits the model typed are gone
    assert [s["heading"] for s in scripts[0]["sections"]][:3] == ["Opening", "Why now (for you, not to read out)",
                                                                  "Three questions"]
    assert len(calls) == 1 and calls[0]["messages"][0]["content"].startswith("# Who you are")

    # "its about <first name> only": still that person, no clarify, and the script is reused at $0.
    given = next(w for w in name.replace(".", " ").split() if len(w) >= 3 and w.lower() not in ("dr", "mr", "mrs"))
    again = talk.send(message=f"its about the {given.lower()} only")
    assert not _of(again, "clarify")
    reused = [c for c in _of(again, "cards") if c["kind"] == "script"]
    assert [c["person"]["person_id"] for c in reused] == [top["person"]["id"]] and reused[0]["written_by"] == "reused"
    assert any(amount in line for section in reused[0]["sections"] for line in section["lines"])  # refilled
    assert len(calls) == 1 and _of(again, "done")[0]["total_cost_usd"] == 0

    # A new request about the same person writes a new script (no stale reuse).
    talk.send(message="write a new call script, shorter please")
    assert len(calls) == 2

    # A pronoun binds too: a WhatsApp draft for "her" is about the same person.
    from api.chat import script as script_mod
    monkeypatch.setattr(script_mod, "write", lambda *a, **k: (script_mod.template_draft("whatsapp"), 0.0, 0))
    draft = talk.send(message="draft a whatsapp to her")
    card = [c for c in _of(draft, "cards") if c["kind"] == "script"][0]
    assert card["channel"] == "whatsapp" and card["person"]["person_id"] == top["person"]["id"]
    assert not any(amount in line for s in card["sections"] for line in s["lines"])  # no amount to the client


def test_script_with_no_one_in_focus_asks_among_real_people_never_home_chips(chat, monkeypatch):
    _model_refuses(monkeypatch)
    client = chat("rm")
    talk = Talk(client)
    listed = talk.send(message="Cash in hand above ₹1 Cr")
    shown = [i["person"]["id"] for c in _of(listed, "cards") if c["kind"] == "people" for i in c["items"]]
    assert shown
    events = talk.send(message="ready me a script for the call")
    ask = _of(events, "clarify")[0]
    assert ask["options"] and all(o["value"].startswith("script:") for o in ask["options"])
    assert not {o["label"] for o in ask["options"]} & HOME_CHIPS
    assert {o["value"].split("/")[1].split("|")[0] for o in ask["options"]} <= set(shown)
    picked = talk.send(choice=ask["options"][0]["value"])  # model refused here: written by the code template
    assert [c["kind"] for c in _of(picked, "cards")] == ["script"]


def test_unclear_message_offers_actions_on_the_focus(chat, monkeypatch):
    from api.chat import llm as chat_llm

    client = chat("rm")
    top = _top(client)
    talk = Talk(client)
    talk.send(message=f"What money does {top['person']['name']} have?")
    monkeypatch.setattr(chat_llm, "call", lambda *a, **k: ({
        "intent": "unclear", "multi_step": False, "about_focus": True, "channel": None, "clarify_question": None,
        "entities": {k: None for k in ("person_name", "company", "event_type", "tier", "role_contains", "min_cr",
                                       "max_cr", "link")}}, 0.0, 1))
    ask = _of(talk.send(message="hmm, what now"), "clarify")[0]
    assert not {o["label"] for o in ask["options"]} & HOME_CHIPS
    assert any(o["value"].startswith("script:") and top["person"]["id"] in o["value"] for o in ask["options"])


# ---------- time windows ----------

def test_this_week_with_no_matches_says_so_and_claims_no_stale_row(chat, monkeypatch):
    monkeypatch.setenv("AURELIA_AS_OF", "2031-06-18")  # long after every stored money date
    from api.chat import windows

    week = windows.parse("this week", date(2031, 6, 18))
    events = Talk(chat("rm")).send(message="Who came into money this week?")
    text = _text(events)
    assert text.startswith("No one came into money this week") and "days ago" in text
    for card in _of(events, "cards"):
        assert "outside" in card["title"].lower()
        assert all(not week.contains(i["timing"]["date_iso"]) for i in card["items"])
    assert _of(events, "done")[0]["verifier"]["removed"] == []  # the day counts are facts, not guesses


def test_a_window_with_matches_lists_only_rows_inside_it(chat, monkeypatch):
    client = chat("rm")
    dated = next(i for i in client.get("/api/today?limit=50").json()["items"] if i["timing"].get("date_iso"))
    when = date.fromisoformat(dated["timing"]["date_iso"])
    monkeypatch.setenv("AURELIA_AS_OF", (when + timedelta(days=2)).isoformat())
    events = Talk(client).send(message="Who came into money in the last 3 days?")
    cards = [c for c in _of(events, "cards") if c["kind"] == "people"]
    assert cards and all(when - timedelta(days=3) <= date.fromisoformat(i["timing"]["date_iso"]) <= when + timedelta(days=2)
                         for i in cards[0]["items"])
    assert "came into money in the last 3 days" in _text(events)


# ---------- compression ----------

def test_compression_output_has_no_unverified_digit(chat, monkeypatch):
    from api.chat import llm as chat_llm
    from api.chat import memory

    monkeypatch.setattr(memory, "HISTORY_COMPRESS_TOKENS", 40)
    monkeypatch.setattr(memory, "KEEP_TURNS", 1)
    client = chat("rm")
    top = _top(client)
    talk = Talk(client)
    for question in ("Who came into money this week?", f"What money does {top['person']['name']} have?",
                     "Cash in hand above ₹1 Cr"):
        talk.send(message=question)
    seen = []

    def summarise(step, model, messages, schema, version, turn_id):
        seen.append(step)
        return ({"summary": f"The RM looked at {top['person']['name']} with {top['amount']['display']} and "
                            "a made-up ₹999.99 Cr total.", "entities": [top["person"]["name"]],
                 "open_questions": ["Call 77 people?"]}, 0.0001, 1)

    monkeypatch.setattr(chat_llm, "call", summarise)
    events = talk.send(message="Who came into money this week?")
    context = _of(events, "context")[0]
    assert seen == ["compress"] and context["compressed"] is True
    assert context["history_tokens_after"] < context["history_tokens_before"]
    state = memory.load(talk.cid)
    record = state["compressions"][-1]
    assert record["by"] == "model" and "999.99" not in state["summary"] and "₹999.99 Cr" in record["removed"]
    assert top["amount"]["display"] in state["summary"]  # a number the turns really showed may stay
    assert not any("77" in q for q in state["open_questions"])
    assert record["tokens_saved"] > 0


# ---------- verified streaming ----------

def test_streamed_sentences_never_contain_an_unverified_digit(chat, monkeypatch):
    from api.chat import agent, router, verifier
    from api.chat.turn import Turn
    from tools import llm as tools_llm

    client = chat("rm")
    top = _top(client)
    amount = top["amount"]["display"]  # e.g. "₹468.85 Cr": split the stream inside it
    cut = amount.index(".") + 1 if "." in amount else len(amount) // 2
    deltas = [f"Call {top['person']['name']} first: {amount[:cut]}", f"{amount[cut:]} in hand. Dr. Rao has ₹7",
              "7.7 Cr too", ". That is all"]

    def fake_stream(*args, **kwargs):
        yield from deltas

    monkeypatch.setattr(tools_llm, "llm_stream", fake_stream)
    data = {"top": [{"name": top["person"]["name"], "amount": amount}]}
    turn = Turn({"email": "rm@aurelia.demo", "role": "rm"}, "c", "who first?")
    events = list(agent.answer(turn, "who first?", "today", data, router.Route("today", by="model")))
    texts = [d for kind, d in events if kind == "text"]
    allowed = verifier.numbers_in(data)
    assert texts[-1] == {"delta": "", "final": True}
    for piece in texts:
        assert verifier.numbers_in(piece["delta"]) <= allowed, piece
    joined = "".join(t["delta"] for t in texts)
    assert amount in joined and "77.7" not in joined and "Dr. Rao" in joined


def test_sentence_splitter_waits_for_whitespace_and_skips_abbreviations():
    from api.chat.stream import Sentences

    feeder = Sentences()
    assert feeder.feed("Sold for ₹468.") == []
    assert feeder.feed("85 Cr. Dr. Asha is ne") == ["Sold for ₹468.85 Cr."]
    assert feeder.feed("xt. ") == ["Dr. Asha is next."]
    assert feeder.flush() == []


# ---------- stable prefix ----------

def test_stable_prefix_comes_first_is_byte_identical_and_long_enough(chat, monkeypatch):
    from api.chat import llm as chat_llm
    from api.chat import prompts

    sent = []

    def route(step, model, messages, schema, version, turn_id):
        sent.append(messages)
        return ({"intent": "help", "multi_step": False, "about_focus": False, "channel": None, "clarify_question": None,
                 "entities": {k: None for k in ("person_name", "company", "event_type", "tier", "role_contains",
                                                "min_cr", "max_cr", "link")}}, 0.0, 1)

    monkeypatch.setattr(chat_llm, "call", route)
    from tools import llm as tools_llm

    def stream(*args, **kwargs):
        sent.append(args[1])
        yield "Ask me who came into money."

    client = chat("rm")
    monkeypatch.setattr(tools_llm, "llm_stream", stream)
    talk = Talk(client)
    talk.send(message="anything good lately")
    talk.send(message="and otherwise")
    assert len(sent) == 4  # route + write, twice
    assert all(m[0] == {"role": "system", "content": prompts.STABLE_PREFIX} for m in sent)
    assert sent[0][2]["content"] != sent[2][2]["content"]  # what changes comes after the prefix
    assert len(prompts.STABLE_PREFIX) >= 4 * 1100  # comfortably past the 1,024-token cache minimum
    assert not re.search(r"\d{2,}", prompts.STABLE_PREFIX)  # no dates or counts that would change


# ---------- cost log: cached tokens without touching pipeline behaviour ----------

def test_cost_log_gains_cache_columns_and_old_rows_stay_readable(tmp_path, monkeypatch):
    from pydantic import BaseModel

    import tools.llm as llm

    log = tmp_path / "cost_log.csv"
    monkeypatch.setenv("COST_LOG_PATH", str(log))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    old_header = "timestamp,run_id,event_id,person_id,agent_name,model,input_tokens,output_tokens,cost_usd,charged_usd,latency_s,cached,params,status,error"
    log.write_text(old_header + "\n2026-01-01T00:00:00Z,r,e,,extract_x,m,10,5,0.000001,,0.1,false,,ok,\n", encoding="utf-8")

    class Answer(BaseModel):
        ok: bool

    monkeypatch.setitem(llm.PRICES, "openai/gpt-6-luna", (0.10, 0.50))
    monkeypatch.setitem(llm.PRICES, "plain-model", (1.0, 2.0))
    llm.register_schema("cache_answer", Answer)
    monkeypatch.setattr(llm, "_post_chat", lambda model, messages: (
        '{"ok": true}', 2000, 10, 0.00004, "OpenAI", "", (1900, 64)))
    llm.llm_call("chat:route", [{"role": "user", "content": "x"}], "cache_answer", "v", event_id="chat-t",
                 model="openai/gpt-6-luna")
    with log.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys())[-2:] == ["cached_input_tokens", "cache_write_tokens"]
    assert rows[0]["agent_name"] == "extract_x" and rows[0]["cached_input_tokens"] == ""  # old row padded
    assert rows[1]["cached_input_tokens"] == "1900" and rows[1]["cache_write_tokens"] == "64"
    expected = (36 * 0.10 + 1900 * 0.01 + 64 * 0.125 + 10 * 0.50) / 1_000_000
    assert abs(float(rows[1]["cost_usd"]) - expected) < 1e-6  # the log keeps six decimals
    assert llm._cost_usd("plain-model", 100, 50) == llm._cost_usd("plain-model", 100, 50, 90, 5)  # unchanged
    assert llm.saved_by_cache("openai/gpt-6-luna", 1900, 64) == pytest.approx((1900 * 0.09 - 64 * 0.025) / 1e6)
    # The cache key is the same function of the same inputs as before.
    raw = json.dumps(["m", "v", "s", [{"a": 1}]], ensure_ascii=False, sort_keys=True)
    assert llm._cache_key("m", "v", "s", [{"a": 1}]) == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_llm_stream_logs_usage_and_caches_the_text(tmp_path, monkeypatch):
    import tools.llm as llm

    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    monkeypatch.setitem(llm.PRICES, "openai/gpt-6.1-terra", (1.0, 5.0))
    posts = []

    def fake(model, messages, max_tokens):
        posts.append(model)
        yield "params", "-temp,reasoning_off"
        yield "delta", "Hello "
        yield "delta", "there."
        yield "usage", {"prompt_tokens": 1500, "completion_tokens": 3, "cost": 0.0001,
                        "prompt_tokens_details": {"cached_tokens": 1408, "cache_write_tokens": 0}}

    monkeypatch.setattr(llm, "_stream_chat", fake)
    messages = [{"role": "user", "content": "hi"}]
    assert "".join(llm.llm_stream("chat:write", messages, "v", "chat-t", model="openai/gpt-6.1-terra")) == "Hello there."
    assert "".join(llm.llm_stream("chat:write", messages, "v", "chat-t", model="openai/gpt-6.1-terra")) == "Hello there."
    assert posts == ["openai/gpt-6.1-terra"]  # the second came from the cache
    with (tmp_path / "cost_log.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["cached_input_tokens"] == "1408" and rows[0]["charged_usd"] == "0.000100"
    assert rows[1]["cached"] == "true" and rows[1]["input_tokens"] == "0"


# ---------- exports, search, ops ----------

def test_export_md_and_callpack_contain_no_secrets_and_no_model(chat, monkeypatch):
    _model_refuses(monkeypatch)
    client = chat("rm")
    top = _top(client)
    talk = Talk(client)
    estimate = _of(talk.send(choice=f"deep:{top['event']['id']}/{top['person']['id']}"), "estimate")[0]
    assert estimate["confirm_token"]
    talk.send(message="ready me a script for the call")  # model refused: template, still a script card
    text = client.get(f"/api/chat/conversations/{talk.cid}/export.md").text
    for secret in (estimate["confirm_token"], estimate["confirm_token"][:24], "test-secret", "rm@aurelia.demo",
                   "demo1234", "sk-or-", "password"):
        assert secret not in text
    assert f"Deep dive on {top['person']['name']}" in text and "Cost estimate for" in text and "*Opening*" in text
    pack = client.get(f"/api/people/{top['event']['id']}/{top['person']['id']}/callpack.md")
    assert pack.status_code == 200 and "## Call script" in pack.text and top["amount"]["display"] in pack.text
    assert "test-secret" not in pack.text and estimate["confirm_token"] not in pack.text


def test_search_meta_and_ops_tokens(chat):
    client = chat("rm")
    top = _top(client)
    talk = Talk(client)
    talk.send(message=f"What money does {top['person']['name']} have?")
    word = top["person"]["name"].split()[-1].lower()
    found = client.get(f"/api/chat/conversations?q={word}").json()
    assert [c["id"] for c in found] == [talk.cid] and found[0]["messages"] == 2 and found[0]["cost_usd"] == 0
    assert client.get("/api/chat/conversations?q=zzzqqq").json() == []
    stored = client.get(f"/api/chat/conversations/{talk.cid}").json()
    meta = stored["messages"][1]["meta"]
    assert {"models", "tokens_in", "tokens_out", "cached_in", "cost_usd", "context_tokens", "compressed", "focus"} <= set(meta)
    assert meta["focus"][0]["person_id"] == top["person"]["id"]
    report = chat("admin").get("/api/ops/tokens").json()
    assert {"questions", "avg_cost_usd", "cache_hit_rate", "cached_tokens", "saved_usd_by_cache", "compressions",
            "tokens_saved_by_compression", "by_model"} <= set(report)
    assert report["questions"] >= 1


def test_a_spelled_out_count_is_checked_like_a_digit():
    from api.chat.verifier import verify

    text, removed = verify("All five have medium confidence; the other two are unsure. No one else.", {"unsure": 2},
                           words=True)
    assert "five" not in text and "two" in text and "No one" in text and removed == ["five"]


def test_scripts_keep_spelled_out_words_and_past_windows_stop_today():
    from api.chat import script, windows

    assert script.fill("If there is no reply in two days, follow up.", {})[0] == "If there is no reply in two days, follow up."
    today = date(2026, 11, 15)
    came = windows.parse("who came into money this month", today)
    assert came.end == today and came.words == "this month so far"
    due = windows.parse("who has money dates this month", today)
    assert due.end == date(2026, 11, 30)
    assert windows.parse("who is due money in the next 10 days", today).tense(today) == "mixed"
