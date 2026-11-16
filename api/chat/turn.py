"""One chat turn's running record: steps, spend per model, cards, and the SSE events it yields.

Every function that does work is a generator that yields (event_type, data) pairs; `result = yield from ...`
passes values back. Turn keeps what the history needs (steps, cards, text, estimate) as they are emitted.
"""

from __future__ import annotations

import time
import uuid


class Turn:
    """State of one answer being built."""

    def __init__(self, user: dict, conversation_id: str, message: str):
        self.user, self.conversation_id, self.message = user, conversation_id, message
        self.id = uuid.uuid4().hex[:12]
        self.started = time.perf_counter()
        self.steps: list[dict] = []
        self.cards: list[dict] = []
        self.text = ""
        self.estimate: dict | None = None
        self.clarify: dict | None = None
        self.usage: dict[str, dict] = {}
        self.spent = 0.0
        self.extra: dict = {}
        # v2 memory: the conversation state, the stored messages before this one, and the context text
        self.state: dict = {}
        self.prior: list[dict] = []
        self.context = ""
        self.context_info: dict = {}
        self.focus_set: list[dict] | None = None  # a handler that knows who the turn is about sets this

    # ----- spend -----
    def add_cost(self, model: str | None, cost: float, calls: int) -> None:
        """Count a model's calls and spend toward this turn."""
        if not model or (not calls and not cost):
            return
        row = self.usage.setdefault(model, {"model": model, "calls": 0, "cost_usd": 0.0})
        row["calls"] += calls
        row["cost_usd"] = round(row["cost_usd"] + cost, 6)
        self.spent = round(self.spent + cost, 6)

    # ----- steps -----
    def begin(self, label: str, model: str | None = None, detail: str | None = None):
        """Start a step: yields its 'running' event, returns its record."""
        step = {"id": f"s{len(self.steps) + 1}", "label": label, "status": "running", "model": model,
                "cost_usd": 0.0, "ms": 0, "detail": detail, "_t": time.perf_counter()}
        self.steps.append(step)
        yield "step", self._public(step)
        return step

    def end(self, step: dict, status: str = "done", detail: str | None = None, cost: float = 0.0,
            calls: int = 0, model: str | None = None):
        """Finish a step: yields its final event."""
        step["status"], step["ms"] = status, int((time.perf_counter() - step.pop("_t", time.perf_counter())) * 1000)
        if model:
            step["model"] = model
        step["cost_usd"] = round(cost, 6)
        if detail is not None:
            step["detail"] = detail
        self.add_cost(step["model"], cost, calls)
        yield "step", self._public(step)

    def note(self, label: str, status: str = "done", detail: str | None = None, model: str | None = None,
             cost: float = 0.0, ms: int = 0):
        """A step that is already finished (a stop reason, a skipped branch)."""
        step = {"id": f"s{len(self.steps) + 1}", "label": label, "status": status, "model": model,
                "cost_usd": round(cost, 6), "ms": ms, "detail": detail}
        self.steps.append(step)
        yield "step", dict(step)

    @staticmethod
    def _public(step: dict) -> dict:
        return {k: v for k, v in step.items() if not k.startswith("_")}

    # ----- output -----
    def card(self, card: dict):
        """Emit one card."""
        self.cards.append(card)
        yield "cards", card

    def say(self, text: str):
        """Stream already-verified prose sentence by sentence; the last event has final: true."""
        from api.chat.stream import split

        for sentence in split(text):
            yield from self.sentence(sentence)
        yield from self.final()

    def sentence(self, sentence: str):
        """Emit one verified sentence."""
        delta = sentence + " "
        self.text += delta
        yield "text", {"delta": delta, "final": False}

    def final(self):
        """Close the streamed prose (the stored text is stripped when the message is saved)."""
        yield "text", {"delta": "", "final": True}

    def done_event(self) -> dict:
        """The closing 'done' payload."""
        return {"total_cost_usd": round(self.spent, 6), "models": list(self.usage.values()),
                "seconds": round(time.perf_counter() - self.started, 2), **self.extra}

    def public_steps(self) -> list[dict]:
        return [self._public(s) for s in self.steps]
