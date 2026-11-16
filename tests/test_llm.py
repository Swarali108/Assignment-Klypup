"""Cache and price checks for llm_call. No network and no API key."""

from __future__ import annotations

import csv
import json

import pytest
from pydantic import BaseModel

import tools.llm as llm
from tools.costs import summarise
from tools.llm import LLMError, llm_call

MESSAGES = [{"role": "user", "content": "Return the filing name only."}]


class FilingName(BaseModel):
    name: str


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    monkeypatch.setenv("RUN_ID", "run-1")
    monkeypatch.delenv("ALLOW_UNPRICED", raising=False)
    llm.PRICES.clear()
    llm.SCHEMAS.clear()
    llm.PRICES["test-model"] = (1.0, 2.0)
    llm.register_schema("filing_name", FilingName)
    yield
    llm.PRICES.clear()
    llm.SCHEMAS.clear()


def _read_costs(tmp_path):
    with (tmp_path / "cost_log.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _patch_model(monkeypatch, text='{"name": "Acme Ltd"}', input_tokens=100, output_tokens=50):
    calls = {"n": 0}

    def fake_post(model, messages):
        calls["n"] += 1
        return text, input_tokens, output_tokens

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    return calls


def test_second_call_is_cached_and_costs_zero(tmp_path, isolated, monkeypatch):
    calls = _patch_model(monkeypatch)
    first = llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-1", model="test-model")
    second = llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-1", model="test-model")

    assert calls["n"] == 1
    assert first == {"name": "Acme Ltd"}
    assert second == {"name": "Acme Ltd"}

    rows = _read_costs(tmp_path)
    assert rows[0]["cached"] == "false"
    assert float(rows[0]["cost_usd"]) == pytest.approx((100 * 1.0 + 50 * 2.0) / 1_000_000)
    assert rows[1]["cached"] == "true"
    assert rows[1]["cost_usd"] == "0.000000"
    assert rows[1]["input_tokens"] == "0"
    assert rows[1]["latency_s"] != ""

    summary = summarise("run-1")
    assert summary["calls"] == 2
    assert summary["cached_calls"] == 1
    assert summary["cost_usd"] == pytest.approx(float(rows[0]["cost_usd"]))
    assert summary["per_event"]["evt-1"]["calls"] == 2
    assert summary["per_person"][0]["person_id"] == "(none)"


def test_prompt_version_change_misses_the_cache(isolated, monkeypatch):
    calls = _patch_model(monkeypatch)
    llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-1", model="test-model")
    llm_call("extractor", MESSAGES, "filing_name", "v2", "evt-1", model="test-model")
    assert calls["n"] == 2
    llm_call("extractor", MESSAGES, "filing_name", "v2", "evt-1", model="test-model")
    assert calls["n"] == 2


def test_unpriced_model_raises_unless_allowed(isolated, monkeypatch):
    calls = _patch_model(monkeypatch)
    with pytest.raises(LLMError, match="not-priced"):
        llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-1", model="not-priced")
    assert calls["n"] == 0

    monkeypatch.setenv("ALLOW_UNPRICED", "1")
    parsed = llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-1", model="not-priced")
    assert calls["n"] == 1
    assert parsed == {"name": "Acme Ltd"}


def test_schema_retries_once_then_caches(tmp_path, isolated, monkeypatch):
    class Person(BaseModel):
        name: str
        shares: int | None

    llm.register_schema("person", Person)
    calls = {"n": 0}

    def fake_post(model, messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"name": 1}', 10, 10
        return '{"name": "A", "shares": null}', 8, 4

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    monkeypatch.setenv("RUN_ID", "run-2")
    parsed = llm_call("extractor", MESSAGES, "person", "v1", "evt-1", person_id="p1", model="test-model")
    assert calls["n"] == 2
    assert parsed == {"name": "A", "shares": None}
    again = llm_call("extractor", MESSAGES, "person", "v1", "evt-1", person_id="p1", model="test-model")
    assert calls["n"] == 2
    assert again == {"name": "A", "shares": None}
    rows = _read_costs(tmp_path)
    assert rows[-1]["cached"] == "true"
    assert rows[-1]["cost_usd"] == "0.000000"


def test_failed_call_logs_status_and_error(tmp_path, isolated, monkeypatch):
    def fake_post(model, messages):
        raise llm.LLMError("HTTP down")

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    with pytest.raises(LLMError, match="HTTP down"):
        llm_call("extractor", MESSAGES, "filing_name", "v-err", "evt-1", model="test-model")
    rows = _read_costs(tmp_path)
    assert rows[0]["status"] == "error"
    assert rows[0]["error"] == "HTTP down"
    assert rows[0]["cached"] == "false"


def test_temp_env_request_and_charged_usd(tmp_path, isolated, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_API_KEY=sk-test\n"
        "LLM_BASE_URL=https://openrouter.ai/api/v1\n"
        "LLM_MODEL=anthropic/claude-haiku-5.5\n"
        "LLM_MODEL_STRONG=anthropic/claude-sonnet-5.5\n",
        encoding="utf-8",
    )
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_MODEL_STRONG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    llm.load_env()
    assert llm.LLM_MODEL == "anthropic/claude-haiku-5.5"
    assert llm.LLM_MODEL_STRONG == "anthropic/claude-sonnet-5.5"
    assert llm.LLM_BASE_URL == "https://openrouter.ai/api/v1"
    llm.PRICES["anthropic/claude-haiku-5.5"] = (1.0, 2.0)
    _pin_capabilities(monkeypatch, {"temperature", "response_format"})

    state = {
        "body": {
            "provider": "Anthropic",
            "choices": [{"message": {"content": '{"name": "Acme Ltd"}'}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "cost": 0.0015},
        }
    }
    captured = _install_fake_openai(monkeypatch, state)
    llm_call("extractor", MESSAGES, "filing_name", "v9", "evt-1")
    state["body"] = {
        "choices": [{"message": {"content": '{"name": "Acme Ltd"}'}}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }
    llm_call("extractor", MESSAGES, "filing_name", "v10", "evt-1")

    client = captured["client"]
    assert client["base_url"] == "https://openrouter.ai/api/v1"
    assert client["api_key"] == "sk-test"
    created = captured["create"]
    assert created["temperature"] == 0
    assert created["response_format"] == {"type": "json_object"}
    assert created["extra_body"] == {"provider": {"require_parameters": True}}
    assert created["model"] == "anthropic/claude-haiku-5.5"
    assert "usage" not in created

    rows = _read_costs(tmp_path)
    assert rows[0]["charged_usd"] == "0.001500"
    assert rows[0]["cost_usd"] == "0.000008"
    assert "charged_usd" in rows[0]
    assert list(rows[0]).index("charged_usd") == list(rows[0]).index("cost_usd") + 1
    assert rows[1]["charged_usd"] == ""
    assert rows[1]["cost_usd"] == "0.000008"
    assert rows[0]["params"] == "temp,json_object,-reasoning"
    assert rows[1]["params"] == "temp,json_object,-reasoning"


def test_ping_prints_provider_tokens_and_both_costs(tmp_path, isolated, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_API_KEY=sk-test\nLLM_MODEL=anthropic/claude-haiku-5.5\n",
        encoding="utf-8",
    )
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    llm.load_env()
    _pin_capabilities(monkeypatch, {"temperature", "response_format", "max_tokens"})
    state = {
        "body": {
            "provider": "Anthropic",
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.0002},
        }
    }
    captured = _install_fake_openai(monkeypatch, state)
    assert llm.main(["--ping"]) == 0
    assert captured["create"]["max_tokens"] == 5
    assert captured["create"]["temperature"] == 0
    printed = capsys.readouterr().out
    assert "model: anthropic/claude-haiku-5.5" in printed
    assert "provider: Anthropic" in printed
    assert "input_tokens: 3" in printed
    assert "output_tokens: 2" in printed
    assert "cost_usd: " in printed
    assert "charged_usd: 0.000200" in printed
    assert "params: temp,json_object,-reasoning" in printed


def test_drops_unsupported_temperature(tmp_path, isolated, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    _pin_capabilities(monkeypatch, {"response_format"})
    captured = _install_fake_openai(monkeypatch, _ok_body())
    llm_call("extractor", MESSAGES, "filing_name", "v-temp", "evt-1", model="test-model")
    assert "temperature" not in captured["create"]
    assert captured["create"]["response_format"] == {"type": "json_object"}
    assert captured["create"]["extra_body"] == {"provider": {"require_parameters": True}}
    assert "-temp" in _read_costs(tmp_path)[0]["params"]
    assert "reasoning_off" not in _read_costs(tmp_path)[0]["params"]


def test_structured_outputs_sends_json_schema(tmp_path, isolated, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    _pin_capabilities(monkeypatch, {"structured_outputs"})
    captured = _install_fake_openai(monkeypatch, _ok_body())
    llm_call("extractor", MESSAGES, "filing_name", "v-schema", "evt-1", model="test-model")
    response_format = captured["create"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "filing_name"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == FilingName.model_json_schema()
    assert "json_schema" in _read_costs(tmp_path)[0]["params"]
    assert "reasoning" not in captured["create"]["extra_body"]


def test_empty_capabilities_parse_json_without_format(tmp_path, isolated, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    _pin_capabilities(monkeypatch, set())
    captured = _install_fake_openai(monkeypatch, _ok_body())
    parsed = llm_call("extractor", MESSAGES, "filing_name", "v-empty", "evt-1", model="test-model")
    assert parsed == {"name": "Acme Ltd"}
    assert "temperature" not in captured["create"]
    assert "response_format" not in captured["create"]
    assert captured["create"]["extra_body"] == {"provider": {"require_parameters": True}}
    assert _read_costs(tmp_path)[0]["params"] == "-temp,-json,-reasoning"


def test_reasoning_off_only_when_supported(tmp_path, isolated, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    current = {"names": {"reasoning"}}
    monkeypatch.setattr(llm, "model_capabilities", lambda model: set(current["names"]))
    captured = _install_fake_openai(monkeypatch, _ok_body())
    llm_call("extractor", MESSAGES, "filing_name", "v-reason", "evt-1", model="test-model")
    assert captured["create"]["extra_body"]["reasoning"] == {"enabled": False}
    assert "reasoning_off" in _read_costs(tmp_path)[0]["params"]
    current["names"] = {"response_format"}
    llm_call("extractor", MESSAGES, "filing_name", "v-plain", "evt-1", model="test-model")
    assert "reasoning" not in captured["create"]["extra_body"]
    assert "reasoning_off" not in _read_costs(tmp_path)[1]["params"]


def test_model_capabilities_uses_cache_and_empty_on_failure(tmp_path, isolated, monkeypatch, caplog):
    catalog = {"fetched_at": llm.time.time(), "models": {"m-1": ["temperature", "reasoning"]}}
    cache = tmp_path / "llm" / "models.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(catalog), encoding="utf-8")

    def fail_fetch(url, max_age_days=1):
        raise AssertionError(url)

    monkeypatch.setattr(llm, "fetch", fail_fetch)
    assert llm.model_capabilities("m-1") == {"temperature", "reasoning"}
    assert llm.model_capabilities("missing") == set()

    cache.unlink()

    def fail_fetch(url, max_age_days=1):
        raise OSError("down")

    monkeypatch.setattr(llm, "fetch", fail_fetch)
    with caplog.at_level("WARNING"):
        assert llm.model_capabilities("m-1") == set()
    assert "down" in caplog.text


def _pin_capabilities(monkeypatch, names: set[str]) -> None:
    monkeypatch.setattr(llm, "model_capabilities", lambda model: set(names))


def _ok_body() -> dict:
    return {
        "body": {
            "choices": [{"message": {"content": '{"name": "Acme Ltd"}'}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }
    }


def _install_fake_openai(monkeypatch, state: dict) -> dict:
    """A stand-in OpenAI client. create() records kwargs and returns state['body']."""
    import sys
    import types

    captured: dict = {}

    class APIStatusError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class FakeRaw:
        def __init__(self):
            self.text = json.dumps(state["body"])

    class FakeCompletions:
        def __init__(self):
            self.with_raw_response = self

        def create(self, **kwargs):
            captured["create"] = kwargs
            return FakeRaw()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = FakeChat()

    module = types.ModuleType("openai")
    module.OpenAI = FakeOpenAI
    module.APIStatusError = APIStatusError
    module.APIConnectionError = APIConnectionError
    monkeypatch.setitem(sys.modules, "openai", module)
    return captured
