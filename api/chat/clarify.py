"""Clarifying questions with clickable options. Code only.

v2 rule: options are always the real candidates (the people who could be meant, from the conversation's focus,
the last list shown, a name search, or today's call queue) or actions on the person being discussed; never
the generic home suggestions.

An option's value says exactly what to do next, so the follow-up needs no model:
  lookup:<full name>                  look this person up by name
  person:<event_id>/<person_id>       show this person's call card
  deep:<event_id>/<person_id>         deep dive on this person (estimate first)
  script:<event_id>/<person_id>|<ch>  call script (ch=call) or message draft (whatsapp | email)
  process:<event_id>                  estimate processing this event
  ask:<text>                          ask this question
"""

from __future__ import annotations

import re

from api import store, views
from api.chat import tools
from config.chat import CANDIDATES_MAX

MAX_OPTIONS = CANDIDATES_MAX


def value_for(then: str, event_id: str, person_id: str, name: str) -> str:
    """The option value for doing `then` with this person. then: lookup | person | deep | script:<channel>."""
    if then.startswith("script"):
        channel = then.partition(":")[2] or "call"
        return f"script:{event_id}/{person_id}|{channel}"
    if then == "deep":
        return f"deep:{event_id}/{person_id}"
    if then == "person":
        return f"person:{event_id}/{person_id}"
    return f"lookup:{name}"


def _verb(then: str) -> str:
    if then.startswith("script"):
        channel = then.partition(":")[2] or "call"
        return {"call": "Who is the call with", "whatsapp": "Who is the WhatsApp message for",
                "email": "Who is the email for"}[channel]
    return {"deep": "Whose money should I trace", "person": "Who do you mean"}.get(then, "Whose money should I look up")


def which_person(name: str, identities: list[dict], then: str = "lookup") -> dict:
    """'3 people match “Sharma”. Which one?' with one option per person."""
    options = []
    for identity in identities[:MAX_OPTIONS]:
        first = identity["appearances"][0]
        role = first["role"] or "Holder"
        label = f"{identity['name']} · {role}, {first['company']} · {first['amount']}"
        # A plain lookup shows the exact person picked (not a second name search), so the card can draw it as a person.
        options.append({"label": label, "value": value_for("person" if then == "lookup" else then, first["event_id"],
                                                           first["person_id"], identity["name"])})
    more = f" (showing {MAX_OPTIONS})" if len(identities) > MAX_OPTIONS else ""
    return {"question": f"{len(identities)} people match “{name}”{more}. Which one do you mean?",
            "options": options, "allow_free_text": True}


def _entity_label(entity: dict) -> str:
    card = tools.person_card(entity["event_id"], entity["person_id"]).get("cards") or []
    item = (card[0]["items"][0] if card and card[0].get("items") else None)
    if item:
        return f"{item['person']['name']} · {item['event']['company']} · {item['amount']['display']}"
    return f"{entity['label']} · {entity.get('company') or ''}".rstrip(" ·")


def among(entities: list[dict], then: str, why: str | None = None) -> dict:
    """Pick one of these remembered people (the focus or the last list)."""
    options = [{"label": _entity_label(e), "value": value_for(then, e["event_id"], e["person_id"], e["label"])}
               for e in entities[:MAX_OPTIONS] if e.get("kind") == "person"]
    question = why or f"{_verb(then)}? These are the people we have been looking at."
    return {"question": question, "options": options, "allow_free_text": True}


def need_person(then: str) -> dict:
    """The question names no one and nothing is in focus: offer the top people in the call queue."""
    queue = tools.today(limit=4)["cards"][0]["items"]
    options = []
    for item in queue[:4]:
        options.append({"label": f"{item['person']['name']} · {item['event']['company']} · {item['amount']['display']}",
                        "value": value_for(then, item["event"]["id"], item["person"]["id"], item["person"]["name"])})
    return {"question": f"{_verb(then)}? Pick someone from today's list or type a name.",
            "options": options, "allow_free_text": True}


def _wanted_type(question: str) -> str | None:
    """The event type the RM named ("process a new IPO"), so the list offers that kind and not another."""
    text = (question or "").lower()
    for word, event_type in (("ipo", "ipo"), ("buyback", "buyback"), ("buy-back", "buyback"),
                             ("offer for sale", "ofs_stock_exchange"), ("block deal", "block_deal")):
        if re.search(rf"\b{re.escape(word)}\b", text):
            return event_type
    return None


def need_event(question: str = "") -> dict:
    """'Process' with no link or event: offer events that are not processed yet (of the type asked for), and ask
    for a link."""
    wanted = _wanted_type(question)
    options = []
    for event in store.load_events():
        spec = event["spec"]
        if event["processed"] or spec.event_type not in store.SUPPORTED_TYPES:
            continue
        if wanted and spec.event_type != wanted:
            continue
        options.append({"label": f"{spec.company} · {views.type_label(spec.event_type)} (not processed yet)",
                        "value": f"process:{spec.event_id}"})
    kind = f" for the {views.type_label(wanted)}" if wanted else ""
    return {"question": f"Paste the link to the filing{kind} (a red herring prospectus, prospectus or letter of offer)"
                        + (", or pick an event that is not processed yet." if options else "."),
            "options": options[:MAX_OPTIONS], "allow_free_text": True}


def focus_actions(entity: dict) -> list[dict]:
    """What the RM can do next with the person in focus."""
    eid, pid, name = entity["event_id"], entity["person_id"], entity["label"]
    return [{"label": f"Call script for {name}", "value": value_for("script:call", eid, pid, name)},
            {"label": f"What money does {name} have?", "value": value_for("person", eid, pid, name)},
            {"label": f"Deep dive on {name}", "value": value_for("deep", eid, pid, name)},
            {"label": f"WhatsApp draft for {name}", "value": value_for("script:whatsapp", eid, pid, name)}]


def unclear(question: str | None, state: dict | None = None) -> dict:
    """The model could not tell what was asked: offer what fits this conversation.

    With a person in focus: actions on that person. With a list shown: those people. Otherwise the top people
    in today's queue. Never the home suggestions.
    """
    state = state or {}
    people = [e for e in state.get("focus") or [] if e.get("kind") == "person"]
    if people:
        options = focus_actions(people[0])
        for other in people[1:3]:
            options.append({"label": f"About {other['label']} instead",
                            "value": value_for("person", other["event_id"], other["person_id"], other["label"])})
        return {"question": question or f"I did not quite follow. Is this about {people[0]['label']}?",
                "options": options[:MAX_OPTIONS], "allow_free_text": True}
    listed = [e for e in state.get("candidates") or [] if e.get("kind") == "person"]
    if listed:
        found = among(listed, "person", question or "I did not quite follow. Is it about one of these people?")
        return found
    found = need_person("person")
    return {**found, "question": question or "I did not quite follow. Is it about one of today's top calls?"}


def no_match(name: str, then: str = "lookup") -> dict:
    """Nobody by that name: suggest checking the spelling, offer today's top people."""
    found = need_person(then)
    return {**found, "question": f"I could not find “{name}” in any processed event. Check the spelling, or pick someone:"}
