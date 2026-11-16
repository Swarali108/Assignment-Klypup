"""The only place that calls a model. Calls go to OpenRouter through the OpenAI SDK.

Cache key is sha256 of [model, prompt_version, schema_name, messages]. A hit
logs cost 0 and does not use the network. A model missing from PRICES raises
unless ALLOW_UNPRICED=1. An unpriced call must not continue quietly.

cost_usd is the estimate from PRICES. charged_usd is usage.cost from the
response when OpenRouter sends it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from tools import costs as costlog
from tools.costs import append_row
from tools.fetch import fetch
from tools.runlog import current_run_id

LOGGER = logging.getLogger(__name__)

# USD per 1,000,000 tokens, as (input, output). None means the rate is not filled in.
# Model page: https://openrouter.ai/anthropic/claude-haiku-5.5
# Date checked: 2026-11-13
# Fill each tuple from that page before a real run. Do not guess a rate.
PRICES: dict[str, tuple[float | None, float | None]] = {
    "anthropic/claude-haiku-5.5": (0.10, 0.50),
    # Source: GET https://openrouter.ai/api/v1/models, fetched 2026-11-13T14:32:06Z through
    # tools/fetch.py. data[].pricing for this id: prompt 0.000002, completion 0.00001 per token.
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),
    # Control tower chat models. OpenRouter /models fetched 2026-11-15 (cache/fetch, fetched_at
    # 2026-11-15T09:36:29Z): data[].pricing prompt / completion per token, prompts under 272K tokens.
    "openai/gpt-6-luna": (0.10, 0.50),  # prompt 0.0000001, completion 0.0000005
    "openai/gpt-6.1-terra": (1.00, 5.00),  # prompt 0.000001, completion 0.000005
    # Chat model switcher (v3). Same cached OpenRouter /models JSON (cache/fetch, fetched_at 2026-11-15T09:36:29Z),
    # data[].pricing prompt / completion per token. Prices checked 2026-11-16 against that file.
    "deepseek/deepseek-v4.1-flash": (0.0507, 0.2028),  # prompt 0.0000000507, completion 0.0000002028
    "z-ai/glm-5.3-flash": (0.0399, 0.0784),  # prompt 0.0000000399, completion 0.0000000784
    "qwen/qwen3.8-flash": (0.15, 0.47),  # prompt 0.00000015, completion 0.00000047
}

# Prompt-cache rates, USD per 1,000,000 tokens, as (cache read, cache write). Only models listed here have
# cached tokens priced apart; every other model's cost estimate is exactly what it was before.
# Source: GET https://openrouter.ai/api/v1/models, fetched 2026-11-15T17:19Z, data[].pricing
# input_cache_read / input_cache_write per token (prompts under 272K tokens).
# How OpenRouter reports it (checked 2026-11-15, and confirmed by two live calls per model that day):
#   https://openrouter.ai/docs/guides/best-practices/prompt-caching : OpenAI caching is automatic, "minimum
#   prompt size of 1024 tokens"; GPT-5.6 and later charge cache writes at 1.25x input, reads at a fraction.
#   https://openrouter.ai/docs/cookbook/administration/usage-accounting : usage.prompt_tokens_details has
#   cached_tokens (read from the cache) and cache_write_tokens (written to it).
#   https://openrouter.ai/docs/api-reference/streaming : a Chat Completions stream ends with one extra chunk
#   that carries the usage object (cost included) just before [DONE]; stream_options is not needed.
#   https://developers.openai.com/api/docs/guides/prompt-caching : the whole rendered prefix must match, so
#   stable content goes first. Live check: a different response_format schema is a full miss, so a prefix
#   hits per (model, schema).
CACHE_PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-6-luna": (0.01, 0.125),  # input_cache_read 0.00000001, input_cache_write 0.000000125
    "openai/gpt-6.1-terra": (0.05, 1.25),  # input_cache_read 0.00000005, input_cache_write 0.00000125
}

ROOT = Path(__file__).resolve().parents[1]
# https://openrouter.ai/docs/guides/routing/provider-selection
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# The same prompt should not vary between runs. A provider that rejects this field errors clearly.
TEMPERATURE = 0
SCHEMAS: dict[str, type[BaseModel]] = {}
# llm_call sets this before _post_chat. Stand-ins used by tests take (model, messages) only.
_ACTIVE_SCHEMA: str | None = None
# Ping stays short. max_tokens is the output cap on Chat Completions.
# https://openrouter.ai/docs/api_reference/parameters
PING_MAX_TOKENS = 5

# append_row writes only costs.COLUMNS. charged_usd sits beside the estimate.
# params records which request fields were sent. A leading "-" means it was dropped.
if "charged_usd" not in costlog.COLUMNS:
    costlog.COLUMNS.insert(costlog.COLUMNS.index("cost_usd") + 1, "charged_usd")
if "params" not in costlog.COLUMNS:
    costlog.COLUMNS.append("params")
# cached_input_tokens / cache_write_tokens: prompt tokens read from / written to the provider's prompt cache
# (blank when the provider did not say). Appended last, so older rows stay readable by position.
for _column in ("status", "error", "cached_input_tokens", "cache_write_tokens"):
    if _column not in costlog.COLUMNS:
        costlog.COLUMNS.append(_column)

# GET {LLM_BASE_URL}/models. data[].supported_parameters needs no key.
# https://openrouter.ai/docs/api-reference/models/get-models
MODELS_CACHE_SECONDS = 24 * 60 * 60


class LLMError(Exception):
    """The model call failed, the price is missing, or the schema failed twice."""


def load_env() -> None:
    """Load the project .env. A variable already in the environment is left as it is.

    Called once when this module is imported. Tests point ROOT at a temp directory
    and call it again.
    """
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MODEL_STRONG
    load_dotenv(ROOT / ".env")
    LLM_API_KEY = _env("LLM_API_KEY")
    LLM_BASE_URL = _env("LLM_BASE_URL") or DEFAULT_BASE_URL
    LLM_MODEL = _env("LLM_MODEL")
    LLM_MODEL_STRONG = _env("LLM_MODEL_STRONG")


def model_capabilities(model: str) -> set[str]:
    """Return supported_parameters for this model id.

    The list is GET {LLM_BASE_URL}/models, cached at cache/llm/models.json for
    24 hours. A failed call returns an empty set so the request sends no
    optional field.
    """
    catalog = _models_catalog()
    values = catalog.get(model, [])
    if not isinstance(values, list):
        return set()
    return {item for item in values if isinstance(item, str)}


def register_schema(schema_name: str, model: type[BaseModel]) -> None:
    """Register a pydantic model so llm_call can validate schema_name."""
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise TypeError("schema must be a pydantic BaseModel subclass.")
    SCHEMAS[schema_name] = model


def llm_call(
    agent_name: str,
    messages: list,
    schema_name: str,
    prompt_version: str,
    event_id: str,
    person_id: str | None = None,
    model: str | None = None,
) -> dict:
    """Call the model, or return the cached JSON for this exact request.

    A schema failure is retried once with the error appended. Both attempts are
    logged. Only a valid response is cached, under the original messages.
    Returns the parsed JSON object.
    """
    if schema_name not in SCHEMAS:
        raise LLMError(f"No pydantic schema registered as {schema_name!r}.")
    resolved_model = _resolve_model(model)
    _require_price(resolved_model)
    original = json.loads(json.dumps(list(messages)))
    key = _cache_key(resolved_model, prompt_version, schema_name, original)
    run_id = current_run_id()

    started = time.perf_counter()
    cached = _read_cache(key)
    if cached is not None:
        _log(
            agent_name=agent_name,
            event_id=event_id,
            person_id=person_id or "",
            run_id=run_id,
            model=resolved_model,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            charged_usd=None,
            latency_s=round(time.perf_counter() - started, 3),
            cached=True,
        )
        return json.loads(json.dumps(cached["parsed"]))

    global _ACTIVE_SCHEMA
    previous_schema = _ACTIVE_SCHEMA
    _ACTIVE_SCHEMA = schema_name
    try:
        return _call_and_validate(
            agent_name, event_id, person_id, run_id, resolved_model, key, original, schema_name
        )
    finally:
        _ACTIVE_SCHEMA = previous_schema


# Schema name used in the cache key of a streamed plain-text call (no JSON schema is sent).
STREAM_SCHEMA = "__text_stream__"


def llm_stream(
    agent_name: str,
    messages: list,
    prompt_version: str,
    event_id: str,
    person_id: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
):
    """Stream plain text from the model: yields text deltas as they arrive. One cost-log row per call.

    Same cache as llm_call (key: model, prompt_version, STREAM_SCHEMA, messages): a hit yields the whole stored
    text at once, logs cost 0 and uses no network. No response_format is sent, so the reply is prose. Usage
    (tokens, cost, cached tokens) arrives in the stream's last chunk (see the CACHE_PRICES notes). The text is
    cached only when the stream finished cleanly. Raises LLMError on any failure (after logging it).
    """
    resolved_model = _resolve_model(model)
    _require_price(resolved_model)
    original = json.loads(json.dumps(list(messages)))
    key = _cache_key(resolved_model, prompt_version, STREAM_SCHEMA, original)
    run_id = current_run_id()
    started = time.perf_counter()
    cached = _read_cache(key)
    if cached is not None:
        _log(agent_name=agent_name, event_id=event_id, person_id=person_id or "", run_id=run_id,
             model=resolved_model, input_tokens=0, output_tokens=0, cost_usd=0.0, charged_usd=None,
             latency_s=round(time.perf_counter() - started, 3), cached=True)
        yield str(cached.get("text") or "")
        return
    parts: list[str] = []
    usage: dict = {}
    params = ""
    try:
        for kind, value in _stream_chat(resolved_model, original, max_tokens):
            if kind == "params":
                params = value
            elif kind == "delta":
                parts.append(value)
                yield value
            elif kind == "usage":
                usage = value
    except LLMError as exc:
        _log(agent_name=agent_name, event_id=event_id, person_id=person_id or "", run_id=run_id,
             model=resolved_model, input_tokens=None, output_tokens=None, cost_usd=None, charged_usd=None,
             latency_s=round(time.perf_counter() - started, 3), cached=False, params=params or getattr(exc, "params", ""),
             status="error", error=str(exc))
        raise
    input_tokens = _as_int(usage.get("prompt_tokens"))
    output_tokens = _as_int(usage.get("completion_tokens"))
    cache = cache_tokens(usage)
    _log(agent_name=agent_name, event_id=event_id, person_id=person_id or "", run_id=run_id, model=resolved_model,
         input_tokens=input_tokens, output_tokens=output_tokens,
         cost_usd=_cost_usd(resolved_model, input_tokens, output_tokens, *cache), charged_usd=_charged_usd(usage),
         latency_s=round(time.perf_counter() - started, 3), cached=False, params=params + ",stream",
         cached_input_tokens=cache[0], cache_write_tokens=cache[1])
    _write_cache(key, {"parsed": None, "text": "".join(parts)})


def _stream_chat(model: str, messages: list, max_tokens: int | None):
    """POST chat/completions with stream: true; yields ("params", str), ("delta", text) and ("usage", dict).

    Lines starting with ":" are OpenRouter keep-alive comments and are skipped. A chunk with a top-level
    "error" (or finish_reason "error") is a mid-stream failure and raises.
    https://openrouter.ai/docs/api-reference/streaming
    """
    try:
        from openai import APIConnectionError, APIStatusError, OpenAI
    except ImportError as exc:
        raise LLMError("The openai package is not installed. No request was sent.") from exc
    client = OpenAI(api_key=_api_key(), base_url=_base_url(), timeout=120)
    kwargs, params = _chat_request(model, messages, None, max_tokens)
    kwargs.pop("response_format", None)  # prose, not JSON
    params = ",".join(token for token in params.split(",") if token not in ("json_object", "json_schema", "-json"))
    yield "params", params
    raw = _create_completion(client, APIStatusError, APIConnectionError, {**kwargs, "stream": True})
    http = getattr(raw, "http_response", raw)
    for line in http.iter_lines():
        if not line or line.startswith(":") or not line.startswith("data: "):
            continue
        body = line[6:].strip()
        if body == "[DONE]":
            break
        try:
            chunk = json.loads(body)
        except json.JSONDecodeError:
            continue
        if chunk.get("error"):
            raise LLMError(f"Model stream failed. {str(chunk['error'])[:300]}")
        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason") == "error":
                raise LLMError("Model stream failed.")
            text = (choice.get("delta") or {}).get("content")
            if isinstance(text, str) and text:
                yield "delta", text
        if isinstance(chunk.get("usage"), dict):
            yield "usage", chunk["usage"]


def _call_and_validate(
    agent_name: str,
    event_id: str,
    person_id: str | None,
    run_id: str,
    resolved_model: str,
    key: str,
    original: list,
    schema_name: str,
) -> dict:
    """Call, validate, and retry once. Only a valid parse is cached."""
    parsed: dict | None = None
    text = ""
    outgoing = original
    for attempt in range(2):
        call_started = time.perf_counter()
        params = ""
        try:
            text, input_tokens, output_tokens, charged_usd, _provider, params, cache = _unpack(
                _post_chat(resolved_model, outgoing), with_cache=True
            )
        except LLMError as exc:
            _log(
                agent_name=agent_name,
                event_id=event_id,
                person_id=person_id or "",
                run_id=run_id,
                model=resolved_model,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                charged_usd=None,
                latency_s=round(time.perf_counter() - call_started, 3),
                cached=False,
                params=getattr(exc, "params", ""),
                status="error",
                error=str(exc),
            )
            raise
        latency_s = round(time.perf_counter() - call_started, 3)
        status = "ok"
        error = ""
        failure = ""
        try:
            parsed = _validate(schema_name, text)
        except (ValidationError, json.JSONDecodeError) as exc:
            parsed = None
            failure = str(exc)
            if attempt == 1:
                status = "error"
                error = f"Schema {schema_name!r} failed twice. {exc}"
        _log(
            agent_name=agent_name,
            event_id=event_id,
            person_id=person_id or "",
            run_id=run_id,
            model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=_cost_usd(resolved_model, input_tokens, output_tokens, *cache),
            charged_usd=charged_usd,
            latency_s=latency_s,
            cached=False,
            params=params,
            status=status,
            error=error,
            cached_input_tokens=cache[0],
            cache_write_tokens=cache[1],
        )
        if status == "error":
            raise LLMError(error)
        if parsed is not None:
            break
        outgoing = original + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        "That response failed validation: "
                        + failure
                        + ". Return one JSON object matching the schema."
                    ),
                },
            ]
    if parsed is None:
        raise LLMError(f"Schema {schema_name!r} failed twice.")
    _write_cache(key, {"parsed": parsed, "text": text})
    return parsed


def main(argv: list[str] | None = None) -> int:
    """Run python -m tools.llm --ping. One short call, then print the usage."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--ping"]:
        print("Usage: python -m tools.llm --ping")
        return 2
    try:
        _ping()
    except LLMError as exc:
        print(str(exc))
        return 1
    return 0


def _ping() -> None:
    """Send one JSON ping with LLM_MODEL and at most PING_MAX_TOKENS output tokens.

    The price table is not required. This call only checks that the key and URL work.
    """
    model = _resolve_model(None)
    messages = [{"role": "user", "content": 'Reply with {"ok":true}'}]
    started = time.perf_counter()
    _text, input_tokens, output_tokens, charged, provider, params = _unpack(
        _post_chat(model, messages, max_tokens=PING_MAX_TOKENS)
    )
    cost = _cost_usd(model, input_tokens, output_tokens)
    _log(
        agent_name="ping",
        event_id="ping",
        person_id="",
        run_id=current_run_id(),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        charged_usd=charged,
        latency_s=round(time.perf_counter() - started, 3),
        cached=False,
        params=params,
    )
    print(f"model: {model}")
    print(f"provider: {provider or ''}")
    print(f"input_tokens: {_blank_number(input_tokens)}")
    print(f"output_tokens: {_blank_number(output_tokens)}")
    print(f"cost_usd: {_format_usd(cost)}")
    print(f"charged_usd: {_format_usd(charged)}")
    print(f"params: {params}")


def _resolve_model(model: str | None) -> str:
    """Use the argument, or LLM_MODEL from the environment when the argument is empty."""
    if model and model.strip():
        return model.strip()
    from_env = _env("LLM_MODEL")
    if not from_env:
        raise LLMError("No model. Pass model= or set LLM_MODEL. No request was sent.")
    return from_env


def _require_price(model: str) -> None:
    """Stop before any request when this model has no rate and ALLOW_UNPRICED is not 1."""
    if _rates(model) is not None:
        return
    if os.environ.get("ALLOW_UNPRICED", "").strip() == "1":
        return
    raise LLMError(
        f"No price for model {model!r}. Add it to PRICES in tools/llm.py, "
        "or set ALLOW_UNPRICED=1 for this run. No request was sent."
    )


def _rates(model: str) -> tuple[float, float] | None:
    """Return the price tuple, or None when the model or either rate is missing."""
    rates = PRICES.get(model)
    if rates is None:
        return None
    input_rate, output_rate = rates
    if input_rate is None or output_rate is None:
        return None
    return float(input_rate), float(output_rate)


def _cache_key(model: str, prompt_version: str, schema_name: str, messages: list) -> str:
    """Hash the request. A new prompt version or model is a cache miss."""
    raw = json.dumps(
        [model, prompt_version, schema_name, messages],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate(schema_name: str, text: str) -> dict:
    """Parse one JSON object and check it against the registered schema."""
    data = json.loads(_extract_json(text))
    parsed = SCHEMAS[schema_name].model_validate(data)
    return parsed.model_dump()


def _llm_cache_dir() -> Path:
    override = os.environ.get("LLM_CACHE_DIR", "").strip()
    path = Path(override) if override else ROOT / "cache" / "llm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_cache(key: str) -> dict | None:
    path = _llm_cache_dir() / f"{key}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache(key: str, payload: dict) -> None:
    path = _llm_cache_dir() / f"{key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _models_catalog() -> dict:
    """Return model id -> supported_parameters. Empty when the GET fails."""
    cached = _read_models_cache()
    if cached is not None:
        return cached
    url = _base_url().rstrip("/") + "/models"
    try:
        path, _meta = fetch(url, max_age_days=1)
        payload = json.loads(path.read_text(encoding="utf-8"))
        catalog = _catalog_from_payload(payload)
    except Exception as exc:
        LOGGER.warning("Model list failed for %s: %s", url, exc)
        return {}
    _write_models_cache(catalog)
    return catalog


def _catalog_from_payload(payload: object) -> dict[str, list[str]]:
    """Pull supported_parameters off each model. A bad body is a failure.

    A model whose reasoning.mandatory is true also gets "reasoning_mandatory:<effort>",
    where <effort> is the last (lowest) of its reasoning.supported_efforts.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise LLMError("Model list had no data array.")
    catalog: dict[str, list[str]] = {}
    for item in payload["data"]:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        params = item.get("supported_parameters")
        if isinstance(model_id, str) and isinstance(params, list):
            catalog[model_id] = [name for name in params if isinstance(name, str)] + _mandatory_reasoning(item)
    return catalog


def _mandatory_reasoning(item: dict) -> list[str]:
    """["reasoning_mandatory:<lowest effort>"] when the catalog says reasoning cannot be off."""
    reasoning = item.get("reasoning")
    if not isinstance(reasoning, dict) or reasoning.get("mandatory") is not True:
        return []
    efforts = [effort for effort in reasoning.get("supported_efforts") or [] if isinstance(effort, str)]
    return [f"reasoning_mandatory:{efforts[-1] if efforts else ''}"]


def _read_models_cache() -> dict | None:
    """Return the catalog when cache/llm/models.json is younger than 24 hours."""
    path = _llm_cache_dir() / "models.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched = float(data["fetched_at"])
        models = data["models"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if not isinstance(models, dict) or time.time() - fetched >= MODELS_CACHE_SECONDS:
        return None
    return models


def _write_models_cache(catalog: dict) -> None:
    """Store the catalog with the time it was fetched."""
    path = _llm_cache_dir() / "models.json"
    payload = {"fetched_at": time.time(), "models": catalog}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _chat_request(
    model: str,
    messages: list,
    schema_name: str | None,
    max_tokens: int | None,
) -> tuple[dict, str]:
    """Build Chat Completions kwargs from the model's supported parameters.

    require_parameters stays true, so a field we send is not ignored.
    https://openrouter.ai/docs/guides/routing/provider-selection
    """
    supported = model_capabilities(model)
    kwargs: dict = {"model": model, "messages": messages}
    tokens: list[str] = []
    if "temperature" in supported:
        kwargs["temperature"] = TEMPERATURE
        tokens.append("temp")
    else:
        tokens.append("-temp")
    response_format, format_token = _response_format(schema_name, supported)
    tokens.append(format_token)
    if response_format is not None:
        kwargs["response_format"] = response_format
    extra: dict = {"provider": {"require_parameters": True}}
    mandatory = sorted(name for name in supported if name.startswith("reasoning_mandatory:"))
    if mandatory:
        # The catalog marks reasoning.mandatory: "enabled false" is a 400. Ask for the
        # lowest effort the model lists instead.
        effort = mandatory[0].split(":", 1)[1]
        extra["reasoning"] = {"effort": effort} if effort else {}
        tokens.append(f"reasoning_{effort or 'default'}")
    elif "reasoning" in supported:
        # Chat Completions turns thinking off with reasoning.enabled false.
        # https://openrouter.ai/docs/cookbook/evaluate-and-optimize/model-migrations/opus-5
        # reasoning.effort "none" also disables it. Models marked reasoning.mandatory
        # reject "none", so this client sends enabled false.
        # https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
        extra["reasoning"] = {"enabled": False}
        tokens.append("reasoning_off")
    else:
        tokens.append("-reasoning")
    kwargs["extra_body"] = extra
    if max_tokens is not None and "max_tokens" in supported:
        kwargs["max_tokens"] = max_tokens
    return kwargs, ",".join(tokens)


def _response_format(schema_name: str | None, supported: set[str]) -> tuple[dict | None, str]:
    """json_schema, else json_object, else no format field.

    Chat Completions json_schema:
    https://openrouter.ai/docs/guides/features/structured-outputs
    json_object:
    https://openrouter.ai/docs/api_reference/parameters
    """
    if "structured_outputs" in supported and schema_name in SCHEMAS:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": SCHEMAS[schema_name].model_json_schema(),
            },
        }, "json_schema"
    if "response_format" in supported:
        return {"type": "json_object"}, "json_object"
    return None, "-json"


def _post_chat(
    model: str,
    messages: list,
    max_tokens: int | None = None,
    schema_name: str | None = None,
) -> tuple:
    """One Chat Completions call. Returns text, tokens, charged USD, provider, params.

    charged USD is None when the body has no usage.cost. A 3-tuple from an older
    stand-in is still accepted by _unpack.
    """
    try:
        from openai import APIConnectionError, APIStatusError, OpenAI
    except ImportError as exc:
        raise LLMError("The openai package is not installed. No request was sent.") from exc

    client = OpenAI(api_key=_api_key(), base_url=_base_url(), timeout=120)
    if schema_name is None:
        schema_name = _ACTIVE_SCHEMA
    kwargs, params = _chat_request(model, messages, schema_name, max_tokens)
    try:
        raw = _create_completion(client, APIStatusError, APIConnectionError, kwargs)
    except LLMError as exc:
        exc.params = params
        raise
    payload = _response_body(raw)
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        error = LLMError("Model response had no message content.")
        error.params = params
        raise error from exc
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
    if usage is None:
        return text, None, None, None, _provider_name(payload), params, (None, None)
    return (
        text,
        _as_int(usage.get("prompt_tokens", usage.get("input_tokens"))),
        _as_int(usage.get("completion_tokens", usage.get("output_tokens"))),
        _charged_usd(usage),
        _provider_name(payload),
        params,
        cache_tokens(usage),
    )


def cache_tokens(usage: dict) -> tuple[int | None, int | None]:
    """(cached_tokens, cache_write_tokens) from usage.prompt_tokens_details; None when not reported."""
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details")
    if not isinstance(details, dict):
        return None, None
    return _as_int(details.get("cached_tokens")), _as_int(details.get("cache_write_tokens"))


def saved_by_cache(model: str, cached_tokens: int | None, write_tokens: int | None) -> float:
    """USD the prompt cache saved on one call: reads at the cache rate instead of full input, minus the write
    premium (writes cost more than plain input). 0 for a model with no cache rates. Can be negative on the
    call that first writes a prefix."""
    rates, cache = _rates(model), CACHE_PRICES.get(model)
    if rates is None or cache is None:
        return 0.0
    read_rate, write_rate = cache
    saved = (cached_tokens or 0) * (rates[0] - read_rate) - (write_tokens or 0) * (write_rate - rates[0])
    return saved / 1_000_000


def _create_completion(client, api_status_error, api_connection_error, kwargs: dict):
    """POST chat/completions with the kwargs _chat_request built.

    usage.cost is returned on every response. The old usage.include flag is
    deprecated and has no effect, so it is not sent.
    https://openrouter.ai/docs/cookbook/administration/usage-accounting
    """
    try:
        return client.chat.completions.with_raw_response.create(**kwargs)
    except api_status_error as exc:
        detail = _error_detail(exc)
        code = getattr(exc, "status_code", "")
        raise LLMError(f"Model HTTP {code}. {detail}") from exc
    except api_connection_error as exc:
        raise LLMError(f"Model request failed. {exc}") from exc


def _response_body(raw) -> dict:
    """Read the JSON body. The SDK's typed object drops OpenRouter's usage.cost."""
    if isinstance(raw, dict):
        return raw
    text = getattr(raw, "text", None)
    if isinstance(text, str) and text.strip():
        return json.loads(text)
    http = getattr(raw, "http_response", None)
    http_text = getattr(http, "text", None)
    if isinstance(http_text, str) and http_text.strip():
        return json.loads(http_text)
    raise LLMError("Model response had no JSON body.")


def _provider_name(payload: dict) -> str | None:
    """Return a provider name when the body includes one.

    A top-level string is used as-is. Otherwise the selected endpoint inside
    openrouter_metadata is used. That object is present only when the request
    opted in with X-OpenRouter-Metadata. This client does not send that header.
    https://openrouter.ai/docs/guides/routing/routers/router-metadata
    """
    direct = payload.get("provider")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    meta = payload.get("openrouter_metadata")
    if not isinstance(meta, dict):
        return None
    endpoints = meta.get("endpoints")
    if not isinstance(endpoints, dict):
        return None
    available = endpoints.get("available")
    if not isinstance(available, list):
        return None
    for item in available:
        if isinstance(item, dict) and item.get("selected") is True and isinstance(item.get("provider"), str):
            return item["provider"].strip() or None
    return None


def _charged_usd(usage: dict) -> float | None:
    """usage.cost is the amount charged to the account. Missing means blank, not zero."""
    if "cost" not in usage:
        return None
    return _as_float(usage.get("cost"))


def _error_detail(exc: Exception) -> str:
    """First 500 characters of an HTTP error body, for the log line."""
    response = getattr(exc, "response", None)
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text[:500]
    return str(exc)[:500]


def _unpack(result: tuple, with_cache: bool = False) -> tuple:
    """Normalise a chat result. A 3-tuple has no charged amount and no provider.

    with_cache adds a seventh element, (cached_tokens, cache_write_tokens), (None, None) when absent.
    """
    text = result[0]
    input_tokens = result[1] if len(result) > 1 else None
    output_tokens = result[2] if len(result) > 2 else None
    charged = result[3] if len(result) > 3 else None
    provider = result[4] if len(result) > 4 else None
    params = result[5] if len(result) > 5 else ""
    if not with_cache:
        return text, input_tokens, output_tokens, charged, provider, params
    cache = result[6] if len(result) > 6 and isinstance(result[6], tuple) else (None, None)
    return text, input_tokens, output_tokens, charged, provider, params, cache


def _as_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _as_float(value: object) -> float | None:
    """Accept a JSON number. Anything else is treated as missing."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _extract_json(text: str) -> str:
    """Strip a markdown fence if the model added one. The schema check still decides."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cached_tokens: int | None = None,
              write_tokens: int | None = None) -> float | None:
    """Return the PRICES estimate, or None when tokens or prices are missing.

    For a model in CACHE_PRICES, cached and written prompt tokens are priced at their own rates; any other
    model (and any call with no cache counts) is priced exactly as before.
    """
    if input_tokens is None or output_tokens is None:
        return None
    rates = _rates(model)
    if rates is None:
        return None
    input_rate, output_rate = rates
    cache = CACHE_PRICES.get(model)
    if cache is None or (not cached_tokens and not write_tokens):
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    cached, written = cached_tokens or 0, write_tokens or 0
    plain = max(input_tokens - cached - written, 0)
    return (plain * input_rate + cached * cache[0] + written * cache[1] + output_tokens * output_rate) / 1_000_000


def _api_key() -> str:
    """The OpenRouter key. Raise before any request when it is missing."""
    key = _env("LLM_API_KEY")
    if not key:
        raise LLMError("LLM_API_KEY is missing. Add it to .env. No request was sent.")
    return key


def _base_url() -> str:
    """LLM_BASE_URL, or the OpenRouter default when the variable is empty."""
    return _env("LLM_BASE_URL") or DEFAULT_BASE_URL


def _env(name: str) -> str:
    """One trimmed environment variable. Empty when it is unset."""
    return os.environ.get(name, "").strip()


def _prepare_cost_log() -> None:
    """Add charged_usd and params to an existing header so new rows line up."""
    path = costlog.cost_log_path()
    if not path.is_file() or path.stat().st_size == 0:
        return
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return
    header = rows[0]
    changed = False
    if "charged_usd" not in header and "cost_usd" in header:
        index = header.index("cost_usd") + 1
        header.insert(index, "charged_usd")
        for row in rows[1:]:
            if len(row) == len(header) - 1:
                row.insert(index, "")
        changed = True
    if "params" not in header:
        header.append("params")
        for row in rows[1:]:
            if len(row) == len(header) - 1:
                row.append("")
        changed = True
    for name in ("status", "error", "cached_input_tokens", "cache_write_tokens"):
        if name in header:
            continue
        header.append(name)
        for row in rows[1:]:
            if len(row) == len(header) - 1:
                row.append("")
        changed = True
    if not changed:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def _log(
    agent_name: str,
    event_id: str,
    person_id: str,
    run_id: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float | None,
    charged_usd: float | None,
    latency_s: float,
    cached: bool,
    params: str = "",
    status: str = "ok",
    error: str = "",
    cached_input_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> None:
    """Append one call. cost_usd is the estimate. charged_usd is blank when no usage.cost arrived.

    params lists the fields that were sent. A token with a leading "-" was left out.
    status is "error" when the call failed. error is the message, otherwise blank.
    """
    _prepare_cost_log()
    append_row(
        {
            "timestamp": _now(),
            "run_id": run_id,
            "event_id": event_id,
            "person_id": person_id,
            "agent_name": agent_name,
            "model": model,
            "input_tokens": "" if input_tokens is None else input_tokens,
            "output_tokens": "" if output_tokens is None else output_tokens,
            "cost_usd": _format_usd(cost_usd),
            "charged_usd": _format_usd(charged_usd),
            "latency_s": f"{latency_s:.3f}",
            "cached": "true" if cached else "false",
            "params": params,
            "status": status,
            "error": error,
            "cached_input_tokens": "" if cached_input_tokens is None else cached_input_tokens,
            "cache_write_tokens": "" if cache_write_tokens is None else cache_write_tokens,
        }
    )


def _format_usd(value: float | None) -> str:
    """Six decimal places, or blank when the amount was not reported."""
    if value is None:
        return ""
    return f"{value:.6f}"


def _blank_number(value: int | None) -> str:
    """Print a token count, or nothing when the response omitted it."""
    if value is None:
        return ""
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


LLM_API_KEY = ""
LLM_BASE_URL = DEFAULT_BASE_URL
LLM_MODEL = ""
LLM_MODEL_STRONG = ""
load_env()


if __name__ == "__main__":
    raise SystemExit(main())
