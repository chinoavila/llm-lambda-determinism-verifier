"""Tests de pipeline/cli.py: subcomandos run, check-case y serve (integración ligera)."""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pipeline.cli import DEFAULT_CASES, case_paths, main, new_run_id, prepare, run
from pipeline.llm import Attempt, LLMCall
from pipeline.orchestrator import (
    GROUPS,
    Case,
    CaseError,
    Scenario,
    Verdict,
    drop_pending,
    per_scenario,
    read_case,
    resolved_calls,
)

FIXTURES = sorted(DEFAULT_CASES.glob("rule-*.json"))
REAL_STACK = pytest.mark.skipif(
    shutil.which("engine") is None or "SANDBOX_IO" not in os.environ,
    reason="necesita el engine y el sandbox (correr en Docker Compose)",
)


def llm_call(content: str) -> LLMCall:
    return LLMCall(
        outcome="ok",
        endpoint="fake",
        base_url="https://fake.test/v1",
        model="fake-model",
        request_params={},
        content=content,
        finish_reason="stop",
        usage=None,
        raw_response="{}",
        attempts=(Attempt(200, None, 0.0, 0.0),),
        duration_seconds=0.0,
    )


class FixtureLLM:
    """LLM falso: responde a cada fixture con su `llm_raw` o su `python_code`, según el grupo."""

    def __init__(self) -> None:
        self.by_description: dict[str, dict[str, Any]] = {}
        for path in FIXTURES:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.by_description[data["description"]] = data
        self.calls = 0

    def complete(self, messages: Any) -> LLMCall:
        self.calls += 1
        system, user = messages[0]["content"], messages[-1]["content"]
        fixture = self.by_description[user]
        if "JSON Schema" in system:
            return llm_call(fixture["llm_raw"])
        return llm_call(json.dumps({"code": fixture["python_code"]}))


class ScriptedLLM:
    def __init__(self, replies: list[LLMCall]) -> None:
        self.replies = replies

    def complete(self, messages: Any) -> LLMCall:
        return self.replies.pop(0)


class FakeBalancer:
    def __init__(self, assignment: Any) -> None:
        self.assignment = assignment
        self.acquired = 0

    def acquire(self) -> Any:
        self.acquired += 1
        return nullcontext(self.assignment)


# --- Piezas del comando ------------------------------------------------------


def test_new_run_id_sorts_by_time_and_has_suffix() -> None:
    run_id = new_run_id(datetime(2026, 9, 26, 13, 5, 9, tzinfo=UTC))
    assert re.fullmatch(r"20260926T130509Z-[0-9a-f]{6}", run_id)
    assert new_run_id() != new_run_id()


def test_case_paths_expands_directories_in_order(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "notas.txt").write_text("x")
    assert case_paths([tmp_path]) == [tmp_path / "a.json", tmp_path / "b.json"]


def test_case_paths_rejects_missing_and_empty(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="no existe"):
        case_paths([tmp_path / "nada.json"])
    with pytest.raises(CaseError, match="no hay casos"):
        case_paths([tmp_path])


def test_fixture_is_read_as_single_scenario_case() -> None:
    case = read_case(DEFAULT_CASES / "rule-008.json")
    assert case.case_id == "RULE-008"
    assert case.scenarios == (Scenario("S1", {"cuota": 1499.5, "ingreso_mensual": 5000}),)


def test_prepare_rejects_repeated_case_id(tmp_path: Path) -> None:
    for name in ("a.json", "b.json"):
        shutil.copy(DEFAULT_CASES / "rule-001.json", tmp_path / name)
    with pytest.raises(CaseError, match="case_id repetido"):
        prepare([tmp_path])


def test_run_writes_each_case_as_it_finishes(tmp_path: Path) -> None:
    ok: Verdict = {"outcome": "executed", "stage": "execution", "result": {"type": "Bool", "value": True}, "error": None}
    runners = {g: per_scenario(lambda raw, env, gamma: ok) for g in GROUPS}
    cases: list[tuple[Case, dict[str, str]]] = [
        (Case(f"C{i}", "regla", (Scenario("a", {}), Scenario("b", {}))), {}) for i in range(2)
    ]
    llm = type("LLM", (), {"complete": lambda self, m: llm_call("{}")})()
    balancer = FakeBalancer(llm)
    out = tmp_path / "out" / "r.jsonl"
    logs: list[str] = []

    written = run(cases, balancer, out, run_id="r", repetitions=2, runners=runners, log=logs.append)

    assert written == 2 * 2 * 3 * 2  # casos x repeticiones x grupos x escenarios
    assert balancer.acquired == 4  # un modelo por (caso, repetición)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == written
    assert {json.loads(line)["case_id"] for line in lines} == {"C0", "C1"}
    assert logs == [  # por rondas: la repetición 1 de todos los casos antes que la 2
        "[rep 1/2] [1/2] C0: 6 registros (executed=6)",
        "[rep 1/2] [2/2] C1: 6 registros (executed=6)",
        "[rep 2/2] [1/2] C0: 6 registros (executed=6)",
        "[rep 2/2] [2/2] C1: 6 registros (executed=6)",
    ]


def test_resume_retries_only_calls_cut_by_quota(tmp_path: Path) -> None:
    ok: Verdict = {"outcome": "executed", "stage": "execution", "result": {"type": "Bool", "value": True}, "error": None}
    runners = {g: per_scenario(lambda raw, env, gamma: ok) for g in GROUPS}
    cases: list[tuple[Case, dict[str, str]]] = [
        (Case(f"C{i}", "regla", (Scenario("a", {}), Scenario("b", {}))), {}) for i in range(2)
    ]
    out = tmp_path / "r.jsonl"
    quota = replace(llm_call("{}"), outcome="quota_exhausted", content=None)
    first = ScriptedLLM([llm_call("{}")] * 4 + [quota, quota])  # C1 rep 1: baseline1 y baseline2 sin cuota
    run(cases, FakeBalancer(first), out, run_id="r", repetitions=1, runners=runners, log=lambda _: None)
    assert sum('"quota_exhausted"' in line for line in out.read_text(encoding="utf-8").splitlines()) == 4

    assert drop_pending(out) == 4
    resolved = resolved_calls(out)
    assert ("C1", 1, "treatment") in resolved and ("C1", 1, "baseline1") not in resolved
    llm = ScriptedLLM([llm_call("{}")] * 8)
    run(cases, FakeBalancer(llm), out, run_id="r", repetitions=2, runners=runners, log=lambda _: None, resolved=resolved)

    assert not llm.replies  # 8 llamadas: los 2 pendientes de la rep 1 y la rep 2 completa
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2 * 2 * 3 * 2 and all(r["outcome"] == "executed" for r in records)
    assert drop_pending(out) == 0


def test_main_rejects_zero_repetitions() -> None:
    with pytest.raises(SystemExit):
        main(["run", "--repetitions", "0"])


@pytest.mark.parametrize("value", ["-0.1", "2.5"])
def test_main_rejects_temperature_out_of_range(value: str) -> None:
    with pytest.raises(SystemExit):
        main(["run", "--temperature", value])


# --- De punta a punta, sin red: engine, sandbox y mypy reales --------------------


@REAL_STACK
def test_end_to_end_over_fixtures_with_fake_llm(tmp_path: Path) -> None:
    prepared = prepare([DEFAULT_CASES])
    llm = FixtureLLM()
    out = tmp_path / "e2e.jsonl"

    written = run(prepared, FakeBalancer(llm), out, run_id="e2e", repetitions=1, log=lambda _: None)

    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert written == len(records) == len(FIXTURES) * 3
    assert llm.calls == len(FIXTURES) * 3
    for path in FIXTURES:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        expected = fixture["expected_verdict"]
        treatment = [r for r in records if r["case_id"] == fixture["case_id"] and r["group"] == "treatment"]
        assert len(treatment) == 1
        r = treatment[0]
        assert (r["outcome"], r["stage"], r["scenario_id"]) == (expected["outcome"], expected["stage"], "S1")
        assert r["llm_raw"] == fixture["llm_raw"]
    assert {r["group"] for r in records} == set(GROUPS)


@REAL_STACK
def test_main_without_credentials_skips_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    code = main(["run", str(DEFAULT_CASES / "rule-001.json"), "--out-dir", str(tmp_path)])
    assert code == 0
    assert "sin credenciales" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_main_resume_needs_an_existing_run(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["run", "--resume"])
    with pytest.raises(SystemExit):
        main(["run", "--resume", "--run-id", "no-existe", "--out-dir", str(tmp_path)])
