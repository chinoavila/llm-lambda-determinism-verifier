"""Tests del cliente LLM: config, balanceo, transporte inyectable y outcomes."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pipeline.llm import ConfigError, NoModelAvailable, load_config, with_run_params
from pipeline.llm.balancer import Balancer, build_balancer
from pipeline.llm.config import LLMConfig, parse_config
from pipeline.llm.ratelimit import parse_duration
from pipeline.llm.transport import HttpRequest, HttpResponse, TransportError

ENV = {"GROQ_API_KEY": "secret-key"}
MESSAGES = [{"role": "user", "content": "Respondé en JSON."}]


def config_data(**balancer: Any) -> dict[str, Any]:
    settings = {
        "reserve_tokens": 1000,
        "min_remaining_requests": 1,
        "max_wait_seconds": 30,
        "max_transport_retries": 2,
        "backoff_base_seconds": 1.0,
        "request_timeout_seconds": 10,
        **balancer,
    }
    endpoint = {"base_url": "https://api.test/v1/", "api_key_env": "GROQ_API_KEY"}
    return {
        "balancer": settings,
        "endpoints": [
            {**endpoint, "name": "big", "model": "m-big", "priority": 1, "params": {"temperature": 0}},
            {**endpoint, "name": "small", "model": "m-small", "priority": 2},
        ],
    }


def config(**balancer: Any) -> LLMConfig:
    return parse_config(config_data(**balancer), ENV)


def ok(model: str = "m", headers: dict[str, str] | None = None) -> HttpResponse:
    body = {
        "model": model,
        "choices": [{"message": {"content": '{"a": 1}'}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 42},
    }
    return HttpResponse(200, headers or {}, json.dumps(body).encode())


def status(code: int, headers: dict[str, str] | None = None, body: object = None) -> HttpResponse:
    return HttpResponse(code, headers or {}, json.dumps(body or {}).encode())


Reply = HttpResponse | Exception


class FakeTransport:
    def __init__(self, replies: list[Reply] | Callable[[HttpRequest], Reply]) -> None:
        self.replies = replies
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        reply = self.replies(request) if callable(self.replies) else self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def balancer(cfg: LLMConfig, transport: FakeTransport, t: FakeTime) -> Balancer:
    return Balancer(cfg, transport, clock=t.clock, sleep=t.sleep)


# --- config ---------------------------------------------------------------


def test_config_resolves_key_from_env_and_hides_it() -> None:
    cfg = config()
    assert cfg.endpoints[0].api_key == "secret-key"
    assert cfg.endpoints[0].base_url == "https://api.test/v1"
    assert "secret-key" not in repr(cfg)


def test_config_missing_key_env_fails() -> None:
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        parse_config(config_data(), {})


def test_config_rejects_reserved_params() -> None:
    data = config_data()
    data["endpoints"][0]["params"] = {"response_format": {"type": "text"}}
    with pytest.raises(ConfigError, match="response_format"):
        parse_config(data, ENV)


def test_endpoint_without_key_is_allowed() -> None:
    data = config_data()
    del data["endpoints"][0]["api_key_env"]
    assert parse_config(data, ENV).endpoints[0].api_key is None


def test_shipped_llm_toml_is_valid() -> None:
    cfg = load_config(Path(__file__).parents[1] / "llm.toml", ENV)
    assert [e.priority for e in cfg.endpoints] == [1, 2, 3]


# --- ratelimit ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("7.66s", 7.66), ("2m59.56s", 179.56), ("500ms", 0.5), ("1h", 3600.0), ("12", 12.0)],
)
def test_parse_duration(value: str, seconds: float) -> None:
    assert parse_duration(value) == pytest.approx(seconds)


@pytest.mark.parametrize("value", ["", "abc", "5x", "s"])
def test_parse_duration_rejects_garbage(value: str) -> None:
    assert parse_duration(value) is None


# --- llamadas -------------------------------------------------------------


def test_complete_sends_json_object_and_keeps_raw() -> None:
    t, transport = FakeTime(), FakeTransport([ok()])
    b = balancer(config(), transport, t)
    with b.acquire() as assignment:
        call = assignment.complete(MESSAGES)

    assert call.outcome == "ok"
    assert call.endpoint == "big"
    assert call.content == '{"a": 1}'
    assert call.usage == {"total_tokens": 42}
    assert call.raw_response is not None and json.loads(call.raw_response)["model"] == "m"
    req = transport.requests[0]
    assert req.url == "https://api.test/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer secret-key"
    assert req.body is not None
    body = json.loads(req.body)
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "m-big" and body["temperature"] == 0
    assert "messages" not in call.request_params


def test_json_validate_failed_is_recorded_not_retried() -> None:
    err = {"error": {"code": "json_validate_failed", "failed_generation": "no json"}}
    t, transport = FakeTime(), FakeTransport([status(400, body=err)])
    with balancer(config(), transport, t).acquire() as assignment:
        call = assignment.complete(MESSAGES)
    assert call.outcome == "generation_failed"
    assert call.raw_response is not None and "failed_generation" in call.raw_response
    assert len(transport.requests) == 1


def test_other_4xx_is_request_error() -> None:
    t, transport = FakeTime(), FakeTransport([status(401)])
    with balancer(config(), transport, t).acquire() as assignment:
        assert assignment.complete(MESSAGES).outcome == "request_error"


def test_429_waits_and_retries_same_model() -> None:
    t, transport = FakeTime(), FakeTransport([status(429, {"retry-after": "5"}), ok()])
    with balancer(config(), transport, t).acquire() as assignment:
        call = assignment.complete(MESSAGES)
    assert call.outcome == "ok" and call.endpoint == "big"
    assert t.sleeps == [5.0]
    assert [a.status for a in call.attempts] == [429, 200]
    assert call.attempts[0].waited_seconds == 5.0


def test_429_beyond_max_wait_is_quota_exhausted_and_switches_next_case() -> None:
    t, transport = FakeTime(), FakeTransport([status(429, {"retry-after": "3600"}), ok()])
    b = balancer(config(), transport, t)
    with b.acquire() as assignment:
        assert assignment.complete(MESSAGES).outcome == "quota_exhausted"
    assert t.sleeps == []
    with b.acquire() as assignment:
        assert assignment.endpoint.name == "small"


def test_transport_errors_retry_with_backoff_then_give_up() -> None:
    replies: list[Reply] = [TransportError("timeout"), status(503), status(502)]
    t, transport = FakeTime(), FakeTransport(replies)
    with balancer(config(max_transport_retries=2), transport, t).acquire() as assignment:
        call = assignment.complete(MESSAGES)
    assert call.outcome == "transport_error"
    assert t.sleeps == [1.0, 2.0]
    assert [a.status for a in call.attempts] == [None, 503, 502]


def test_transport_error_then_success() -> None:
    t, transport = FakeTime(), FakeTransport([TransportError("reset"), ok()])
    with balancer(config(), transport, t).acquire() as assignment:
        assert assignment.complete(MESSAGES).outcome == "ok"


# --- balanceo -------------------------------------------------------------


def test_low_remaining_tokens_moves_new_cases_to_next_model() -> None:
    low = {"x-ratelimit-remaining-tokens": "500", "x-ratelimit-reset-tokens": "20s"}
    t, transport = FakeTime(), FakeTransport([ok(headers=low)])
    b = balancer(config(), transport, t)
    with b.acquire() as assignment:
        assignment.complete(MESSAGES)
    with b.acquire() as assignment:
        assert assignment.endpoint.name == "small"
    t.now = 21.0  # pasó el reset del TPM
    with b.acquire() as assignment:
        assert assignment.endpoint.name == "big"


def test_run_params_fix_model_and_temperature() -> None:
    cfg = with_run_params(config(), model="m-small", temperature=0.7)
    assert [e.name for e in cfg.endpoints] == ["small"]
    t, transport = FakeTime(), FakeTransport([ok()])
    with balancer(cfg, transport, t).acquire() as assignment:
        call = assignment.complete(MESSAGES)
    assert call.model == "m-small" and call.request_params["temperature"] == 0.7
    assert with_run_params(config(), temperature=0).endpoints[1].params == {"temperature": 0}
    assert with_run_params(config()) == config()
    with pytest.raises(ConfigError, match="m-otro"):
        with_run_params(config(), model="m-otro")


def test_fixed_model_never_falls_back_to_another() -> None:
    t, transport = FakeTime(), FakeTransport([status(429, {"retry-after": "3600"})])
    b = balancer(with_run_params(config(), model="m-big"), transport, t)
    with b.acquire() as assignment:
        assert assignment.complete(MESSAGES).outcome == "quota_exhausted"
    with pytest.raises(NoModelAvailable):  # el único modelo sigue en cooldown: se corta, no cambia
        b.acquire()


def test_active_assignments_reserve_tokens() -> None:
    headers = {"x-ratelimit-remaining-tokens": "2500", "x-ratelimit-reset-tokens": "30s"}
    t, transport = FakeTime(), FakeTransport([ok(headers=headers)])
    b = balancer(config(), transport, t)
    first = b.acquire()
    first.complete(MESSAGES)
    second = b.acquire()  # 2500 - 1000*1 >= 1000
    third = b.acquire()  # 2500 - 1000*2 < 1000
    assert (first.endpoint.name, second.endpoint.name, third.endpoint.name) == ("big", "big", "small")


def test_acquire_fails_when_nothing_frees_up_within_max_wait() -> None:
    t, transport = FakeTime(), FakeTransport([status(429, {"retry-after": "600"})] * 2)
    b = balancer(config(), transport, t)
    for _ in range(2):
        with b.acquire() as assignment:
            assignment.complete(MESSAGES)
    with pytest.raises(NoModelAvailable):
        b.acquire()


# --- health check ---------------------------------------------------------


def models_reply(ids: list[str]) -> Callable[[HttpRequest], Reply]:
    def reply(request: HttpRequest) -> Reply:
        assert request.method == "GET" and request.url.endswith("/models")
        return status(200, body={"data": [{"id": i} for i in ids]})

    return reply


def test_health_check_excludes_unlisted_models() -> None:
    b = build_balancer(config(), FakeTransport(models_reply(["m-small"])))
    assert b.available_endpoints() == ["small"]


def test_health_check_excludes_endpoint_with_bad_key() -> None:
    with pytest.raises(NoModelAvailable):
        build_balancer(config(), FakeTransport(lambda _: status(401)))


def test_health_check_excludes_unreachable_endpoint() -> None:
    with pytest.raises(NoModelAvailable):
        build_balancer(config(), FakeTransport(lambda _: TransportError("refused")))


def test_wait_for_quota_waits_instead_of_giving_up() -> None:
    t, transport = FakeTime(), FakeTransport([status(429, {"retry-after": "3600"}), ok()])
    cfg = with_run_params(config(), model="m-big", wait_for_quota=True)
    with balancer(cfg, transport, t).acquire() as assignment:
        call = assignment.complete(MESSAGES)
    assert call.outcome == "ok" and t.sleeps == [3600.0]
