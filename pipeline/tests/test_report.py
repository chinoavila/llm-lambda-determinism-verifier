"""Tests de pipeline/report.py y de POST /api/runs/{id}/report, con un balanceador falso."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pipeline.llm import LLMCall, NoModelAvailable, Outcome
from pipeline.report import METHODOLOGY, OBSERVATIONS, Reporter, build_messages, parse_report
from pipeline.server import Paths, make_server
from pipeline.store import StoreError

EVIDENCE = {"run": {"run_id": "r1", "repetitions": 1}, "pass_by_group": {"treatment": {"pass": 3, "fail": 1}}}


def valid_report(**over: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "title": "Reporte de la corrida r1",
        "abstract": "Resumen.",
        "sections": [{"heading": "Resultados", "paragraphs": ["El Tratamiento acierta 3 de 4 generaciones."]}],
        "observations": [{"number": n, "status": "no_concluyente", "text": "Sin evidencia."} for n in range(1, OBSERVATIONS + 1)],
        "limitations": ["Una sola repetición."],
        "conclusions": ["Revisar el diseño."],
    }
    return {**report, **over}


class FakeAssignment:
    def __init__(self, calls: list[Sequence[Mapping[str, str]]], content: str | None, outcome: Outcome) -> None:
        self.calls, self.content, self.outcome = calls, content, outcome

    def complete(self, messages: Sequence[Mapping[str, str]]) -> LLMCall:
        self.calls.append(messages)
        return LLMCall(
            outcome=self.outcome,
            endpoint="fake",
            base_url="http://fake",
            model="fake-model",
            request_params={"model": "fake-model"},
            content=self.content,
            finish_reason="stop",
            usage={"total_tokens": 10},
            raw_response="{}",
            attempts=(),
            duration_seconds=0.1,
        )


class FakeBalancer:
    def __init__(self, content: str | None, outcome: Outcome = "ok", fail: bool = False) -> None:
        self.calls: list[Sequence[Mapping[str, str]]] = []
        self.content, self.outcome, self.fail = content, outcome, fail

    @contextmanager
    def acquire(self) -> Iterator[FakeAssignment]:
        if self.fail:
            raise NoModelAvailable("pool vacío")
        yield FakeAssignment(self.calls, self.content, self.outcome)


@pytest.fixture()
def out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    (out / "r1.jsonl").write_text("", encoding="utf-8")
    return out


def reporter(out: Path, balancer: FakeBalancer, methodology: Path = METHODOLOGY) -> Reporter:
    return Reporter(out, methodology=methodology, balancer=lambda: balancer, now=lambda: datetime(2026, 10, 7, 12, tzinfo=UTC))


# --- prompt y validación ------------------------------------------------------------


def test_methodology_covers_the_observations_and_references() -> None:
    text = METHODOLOGY.read_text(encoding="utf-8")
    for n in range(1, OBSERVATIONS + 1):
        assert f"\n{n}. " in text
    for author in ("Cherednichenko", "Mündler", "Zhang"):
        assert author in text


def test_build_messages_includes_methodology_and_evidence() -> None:
    system, user = build_messages("r1", EVIDENCE, "Bases X")
    assert system["role"] == "system" and "JSON" in system["content"]
    assert user["role"] == "user" and "Bases X" in user["content"]
    assert json.dumps(EVIDENCE, ensure_ascii=False) in user["content"]


def test_parse_report_accepts_a_valid_report() -> None:
    parsed = parse_report(json.dumps(valid_report(extra="se descarta")))
    assert parsed == valid_report()


@pytest.mark.parametrize(
    "content",
    [
        None,
        "no es json",
        "[]",
        json.dumps(valid_report(title="")),
        json.dumps(valid_report(sections=[])),
        json.dumps(valid_report(sections=[{"heading": "A", "paragraphs": "texto"}])),
        json.dumps(valid_report(observations=[{"number": 9, "status": "se_repite", "text": "x"}])),
        json.dumps(valid_report(observations=[{"number": 1, "status": "quizás", "text": "x"}])),
        json.dumps(valid_report(limitations=[""])),
    ],
)
def test_parse_report_rejects_invalid_reports(content: str | None) -> None:
    with pytest.raises(StoreError) as exc:
        parse_report(content)
    assert exc.value.status == 502


# --- Reporter -----------------------------------------------------------------------


def test_generate_calls_the_llm_once_and_saves_the_trace(out: Path) -> None:
    balancer = FakeBalancer(json.dumps(valid_report()))
    result = reporter(out, balancer).generate("r1", EVIDENCE)
    assert len(balancer.calls) == 1
    assert result["model"] == "fake-model" and result["report"]["title"] == "Reporte de la corrida r1"
    assert result["saved"] == "r1.report-20261007T120000Z.json"
    trace = json.loads((out / result["saved"]).read_text(encoding="utf-8"))
    assert trace["evidence"] == EVIDENCE and trace["content"] == json.dumps(valid_report())


def test_generate_errors(out: Path, tmp_path: Path) -> None:
    def status(r: Reporter, run_id: str = "r1") -> int:
        with pytest.raises(StoreError) as exc:
            r.generate(run_id, EVIDENCE)
        return exc.value.status

    assert status(reporter(out, FakeBalancer("{}")), "otra") == 404
    empty = tmp_path / "vacia.md"
    empty.write_text("  \n", encoding="utf-8")
    assert status(reporter(out, FakeBalancer("{}"), methodology=empty)) == 409
    assert status(reporter(out, FakeBalancer(None, fail=True))) == 503
    assert status(reporter(out, FakeBalancer(None, outcome="quota_exhausted"))) == 429
    assert status(reporter(out, FakeBalancer(None, outcome="transport_error"))) == 502
    assert status(reporter(out, FakeBalancer("{}"))) == 502  # forma inválida, pero queda la traza
    assert list(out.glob("r1.report-*.json"))


# --- HTTP ---------------------------------------------------------------------------


def request(url: str, method: str = "GET", body: Any = None) -> tuple[int, bytes]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def as_json(body: bytes) -> Any:
    return json.loads(body.decode("utf-8"))


@pytest.fixture()
def api(out: Path, tmp_path: Path) -> Iterator[tuple[str, FakeBalancer]]:
    balancer = FakeBalancer(json.dumps(valid_report()))
    paths = Paths(corpus=tmp_path, out=out, static=None, fixtures=tmp_path)
    server = make_server("127.0.0.1", 0, paths, reporter=reporter(out, balancer))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", balancer
    finally:
        server.shutdown()
        server.server_close()


def test_http_report(api: tuple[str, FakeBalancer], monkeypatch: pytest.MonkeyPatch) -> None:
    url, balancer = api
    monkeypatch.setenv("GROQ_API_KEY", "gsk-SECRETO-123")
    status, body = request(f"{url}/api/runs/r1/report", "POST", {"evidence": EVIDENCE})
    assert status == 200 and as_json(body)["report"]["sections"][0]["heading"] == "Resultados"
    assert "SECRETO" not in body.decode("utf-8") and len(balancer.calls) == 1

    assert request(f"{url}/api/runs/nada/report", "POST", {"evidence": EVIDENCE})[0] == 404
    assert request(f"{url}/api/runs/r1/report", "POST", {"evidence": []})[0] == 400
    assert request(f"{url}/api/runs/r1/report", "GET")[0] == 405


def test_http_report_without_credentials(api: tuple[str, FakeBalancer], monkeypatch: pytest.MonkeyPatch) -> None:
    url, balancer = api
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    status, body = request(f"{url}/api/runs/r1/report", "POST", {"evidence": EVIDENCE})
    assert status == 409 and "credenciales" in as_json(body)["error"]
    assert balancer.calls == []
