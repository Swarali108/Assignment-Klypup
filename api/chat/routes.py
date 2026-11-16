"""HTTP routes for the control tower chat (api/CHAT_CONTRACT.md, v1 + v2). Mounted by api/main.py.

v2 adds: conversation search (?q=), export.md, a person's callpack.md and /api/ops/tokens. None of the GET
routes calls a model or spends money.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from api import auth
from api.chat import agent, exports, history, ops, script, tokens, tools

router = APIRouter()


class FocusIn(BaseModel):
    """One entity in the "Talking about" chip."""

    kind: str
    event_id: str
    person_id: str | None = None
    label: str = ""


class ChatIn(BaseModel):
    """POST /api/chat body."""

    conversation_id: str | None = None
    message: str = ""
    confirm_token: str | None = None
    choice: str | None = None
    focus: list[FocusIn] | None = None  # v2: the chip as the RM edited it (null = keep the server's focus)
    model: str | None = None  # v3: a model from the allow-list for this conversation (GET /api/chat/models)


def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/api/chat")
def chat(body: ChatIn, user: dict = auth.VIEW_USER) -> StreamingResponse:
    """One message in, server-sent events out. A confirm token is checked here, before anything runs (403)."""
    confirmed = None
    if body.confirm_token:
        try:
            confirmed = tokens.read(body.confirm_token, user["email"])
        except tokens.TokenError as exc:
            raise HTTPException(403, str(exc))
        allowed, reason = tokens.can_confirm(user["role"], float(confirmed.get("hi") or 0))
        if not allowed:
            raise HTTPException(403, reason)

    def stream():
        for kind, data in agent.respond(user, body.conversation_id, body.message, body.choice, confirmed,
                                         [f.model_dump() for f in body.focus] if body.focus is not None else None,
                                         body.model):
            yield _sse(kind, data)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.get("/api/chat/models")
def chat_models(user: dict = auth.VIEW_USER) -> dict:
    """The model switcher's allow-list with prices (USD per 1M tokens, from tools/llm.PRICES) and the defaults."""
    from config import chat as cfg
    from tools.llm import CACHE_PRICES, PRICES

    models = []
    for model_id, label, note in cfg.ALLOWED_MODELS:
        price = PRICES.get(model_id)
        if not price or price[0] is None:
            continue  # never offer a model whose price is not filled in
        models.append({"id": model_id, "label": label, "note": note, "input_per_m": price[0], "output_per_m": price[1],
                       "cache_read_per_m": (CACHE_PRICES.get(model_id) or (None,))[0]})
    return {"models": models, "default_fast": cfg.fast_model(), "default_strong": cfg.strong_model(),
            "priced_from": "OpenRouter /models, fetched 2026-11-15"}


class CompareIn(BaseModel):
    """POST /api/chat/compare body: one question, two models."""

    question: str
    models: list[str]


def _run_once(user: dict, question: str, model: str) -> dict:
    """One question on one model in a throwaway conversation (deleted afterwards). Never runs a confirmed action."""
    import time

    started, text, cards, done, blocked, conversation_id = time.perf_counter(), [], [], {}, None, None
    for kind, data in agent.respond(user, None, question, None, None, None, model):
        if kind == "meta":
            conversation_id = data["conversation_id"]
        elif kind == "text":
            text.append(data.get("delta") or "")
        elif kind == "cards":
            cards.append(data)
        elif kind == "done":
            done = data
        elif kind == "estimate":
            blocked = "This question spends money and needs a confirm, so the comparison did not run it."
        elif kind == "clarify":
            blocked = data.get("question") or "The assistant asked a question back."
        elif kind == "error":
            blocked = data.get("message")
    cached = False
    if conversation_id:
        stored = [m for m in history.messages(conversation_id) if m["role"] == "assistant"]
        meta = (stored[-1].get("meta") or {}) if stored else {}
        # Every model call came from the local answer cache: a saved copy of an earlier answer, not a fresh run.
        cached = bool(meta.get("local_cache_hits")) and not meta.get("provider_calls")
        history.delete(conversation_id, user["email"])
    return {"model": model, "cached": cached, "text": " ".join(" ".join(text).split()), "cards": cards, "blocked": blocked,
            "cost_usd": done.get("total_cost_usd", 0.0), "tokens": done.get("tokens"),
            "models_used": done.get("models", []), "seconds": round(time.perf_counter() - started, 2)}


@router.post("/api/chat/compare")
def compare(body: CompareIn, user: dict = auth.ASK_USER) -> dict:
    """The same question on two allow-listed models side by side, with each one's cost and wall-clock latency.
    Nothing is saved to the history; estimates are shown as blocked, never confirmed."""
    from concurrent.futures import ThreadPoolExecutor

    from config.chat import allowed_ids

    question = (body.question or "").strip()[:2000]
    chosen = body.models[:2]
    if not question or len(chosen) != 2 or len(set(chosen)) != 2 or any(m not in allowed_ids() for m in chosen):
        raise HTTPException(422, "Give one question and two different models from the list")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda m: _run_once(user, question, m), chosen))
    return {"question": question, "results": results}


@router.get("/api/chat/conversations")
def conversations(q: str | None = None, user: dict = auth.VIEW_USER) -> list[dict]:
    """This user's conversations, newest first: [{id, title, updated_at, messages, cost_usd}]. q searches titles
    and message text."""
    return history.list_for(user["email"], q)


@router.get("/api/chat/conversations/{conversation_id}")
def conversation(conversation_id: str, user: dict = auth.VIEW_USER) -> dict:
    """One conversation with its messages (404 when it is not this user's)."""
    found = history.get(conversation_id, user["email"])
    if found is None:
        raise HTTPException(404, "No such conversation")
    return found


@router.delete("/api/chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: dict = auth.VIEW_USER) -> dict:
    """Delete one of this user's conversations."""
    if not history.delete(conversation_id, user["email"]):
        raise HTTPException(404, "No such conversation")
    return {"deleted": True}


def _markdown(text: str, filename: str) -> PlainTextResponse:
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/api/chat/conversations/{conversation_id}/export.md")
def export_conversation(conversation_id: str, user: dict = auth.VIEW_USER) -> PlainTextResponse:
    """The whole thread as a Markdown report (answers, cards as tables, sources as links, per-turn cost)."""
    found = history.get(conversation_id, user["email"])
    if found is None:
        raise HTTPException(404, "No such conversation")
    return _markdown(exports.conversation_md(found), f"conversation-{conversation_id[:8]}.md")


@router.get("/api/people/{event_id}/{person_id}/callpack.md")
def callpack(event_id: str, person_id: str, user: dict = auth.VIEW_USER) -> PlainTextResponse:
    """Call card + brief + call script + evidence links. The script is this user's latest one for the person
    (from their chats), else a code template ($0)."""
    mine = [history.get(c["id"], user["email"]) or {} for c in history.list_for(user["email"])]
    text = exports.callpack_md(event_id, person_id, exports.latest_script(mine, event_id, person_id))
    if text is None:
        raise HTTPException(404, "No such person")
    return _markdown(text, f"callpack-{person_id[:40]}.md")


@router.get("/api/people/{event_id}/{person_id}/callscript")
def callscript(event_id: str, person_id: str, user: dict = auth.VIEW_USER) -> dict:
    """The call script the print page shows: this user's latest one for the person (the same card the chat showed),
    else the code template. {script: card, source: "chat"|"template"}. $0."""
    found = tools.person_card(event_id, person_id)
    if not found["cards"]:
        raise HTTPException(404, "No such person")
    mine = [history.get(c["id"], user["email"]) or {} for c in history.list_for(user["email"])]
    earlier = exports.latest_script(mine, event_id, person_id)
    if earlier:
        return {"script": earlier, "source": "chat"}
    card = found["cards"][0]["items"][0]
    made, _removed = script.card_for(card, script.template_draft("call"), "call", "template")
    return {"script": made, "source": "template"}


@router.get("/api/ops/tokens", dependencies=[auth.OPS])
def ops_tokens() -> dict:
    """Chat token economics: questions, average cost, provider cache hit rate and savings, compressions."""
    return ops.tokens_report()
