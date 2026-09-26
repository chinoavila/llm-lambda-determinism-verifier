from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from pipeline.llm import Attempt, LLMCall, Outcome
from pipeline.orchestrator import (
    GROUPS,
    Case,
    EngineError,
    Group,
    Verdict,
    append_jsonl,
    print_gamma,
    route_call,
    run_case,
    run_engine,
)

CONTRACTS = Path(__file__).parents[2] / "contracts"
FIXTURES = sorted((CONTRACTS / "fixtures").glob("rule-*.json"))
FIXTURE = CONTRACTS / "fixtures" / "rule-001.json"
RECORD_SCHEMA = json.loads((CONTRACTS / "output-record-schema.json").read_text(encoding="utf-8"))

EXECUTED = '{"outcome":"executed","stage":"execution","result":{"type":"Bool","value":true},"error":null}\n'
BLOCKED = '{"outcome":"blocked","stage":"typecheck","result":null,"error":{"code":"BRANCH_MISMATCH","message":"x"}}\n'


def fake_engine(tmp_path: Path, stdout: str, exit_code: int = 0, sleep: float = 0) -> list[str]:
    """Engine falso: guarda argumentos y stdin en args.json/stdin.txt e imprime `stdout`."""
    script = tmp_path / "engine.py"
    script.write_text(
        "import json, sys, time\n"
        f"open({str(tmp_path / 'args.json')!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        f"open({str(tmp_path / 'stdin.txt')!r}, 'w').write(sys.stdin.read())\n"
        f"time.sleep({sleep})\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, str(script)]


def llm_call(outcome: Outcome = "ok", content: str | None = '{"expr": 1}') -> LLMCall:
    return LLMCall(
        outcome=outcome,
        endpoint="big",
        base_url="https://api.test/v1",
        model="m-big",
        request_params={},
        content=content if outcome == "ok" else None,
        finish_reason="stop" if outcome == "ok" else None,
        usage=None,
        raw_response="{}",
        attempts=(Attempt(200 if outcome == "ok" else 429, None, 0.1, 0.0),),
        duration_seconds=0.1,
    )


class FakeAssignment:
    """Modelo asignado falso: devuelve `calls` en orden y guarda los mensajes."""

    def __init__(self, calls: list[LLMCall]) -> None:
        self.calls = calls
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: Any) -> LLMCall:
        self.messages.append([dict(m) for m in messages])
        return self.calls.pop(0)


def fixed_runner(verdict: Verdict, seen: list[str]) -> Any:
    def runner(llm_raw: str, env: Any, gamma: Any) -> Verdict:
        seen.append(llm_raw)
        return verdict

    return runner


def assert_record_shape(record: Any) -> None:
    """Chequeo mínimo contra el contrato (sin dependencias de jsonschema)."""
    assert set(record) == set(RECORD_SCHEMA["required"])
    assert record["schema_version"] == "1.0"
    if record["outcome"] == "executed":
        assert record["result"] is not None and record["error"] is None
    else:
        assert record["result"] is None and record["error"] is not None
    if record["outcome"] == "llm_error":
        assert record["stage"] == "llm"
        assert record["llm_raw"] is None and record["duration_ms"] is None
    else:
        assert isinstance(record["llm_raw"], str) and isinstance(record["duration_ms"], int)


def test_print_gamma_sends_env_and_parses_gamma(tmp_path: Path) -> None:
    env = json.loads(FIXTURE.read_text(encoding="utf-8"))["env"]
    gamma_line = '{"credit_score":"Int","customer_tier":"String","has_defaults":"Bool","monthly_income":"Int"}\n'
    gamma = print_gamma(env, fake_engine(tmp_path, gamma_line))

    assert gamma == {
        "credit_score": "Int",
        "customer_tier": "String",
        "has_defaults": "Bool",
        "monthly_income": "Int",
    }
    args = json.loads((tmp_path / "args.json").read_text())
    assert args[0] == "--env" and json.loads(args[1]) == env
    assert args[2] == "--print-gamma"


def test_print_gamma_usage_error_aborts(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="64"):
        print_gamma({"x": 1.5}, fake_engine(tmp_path, "", exit_code=64))


def test_print_gamma_rejects_non_json_stdout(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="no es JSON"):
        print_gamma({}, fake_engine(tmp_path, "hola\n"))


def test_print_gamma_rejects_non_gamma_json(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="nombre: tipo"):
        print_gamma({}, fake_engine(tmp_path, '{"x": 1}\n'))


@pytest.mark.skipif(shutil.which("engine") is None, reason="binario del engine no instalado")
def test_print_gamma_with_real_engine() -> None:
    env = json.loads(FIXTURE.read_text(encoding="utf-8"))["env"]
    assert print_gamma(env, ["engine"]) == {
        "credit_score": "Int",
        "customer_tier": "String",
        "has_defaults": "Bool",
        "monthly_income": "Int",
    }


def test_print_gamma_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="no se pudo ejecutar"):
        print_gamma({}, [str(tmp_path / "no-existe")])


# --- Triple llamada por grupo ---------------------------------------------


def test_run_case_calls_llm_once_per_group_on_same_model() -> None:
    ok_verdict: Verdict = {
        "outcome": "executed",
        "stage": "execution",
        "result": {"type": "Bool", "value": True},
        "error": None,
    }
    seen: dict[Group, list[str]] = {g: [] for g in GROUPS}
    runners = {g: fixed_runner(ok_verdict, seen[g]) for g in GROUPS}
    assignment = FakeAssignment(
        [llm_call(content='{"expr":1}'), llm_call(content='{"code":"b1"}'), llm_call(content='{"code":"b2"}')]
    )
    case = Case("RULE-001", "Aprobar si credit_score > 700", {"credit_score": 750})

    records = run_case(case, assignment, runners, {"credit_score": "Int"}, run_id="run-1")

    assert [r["group"] for r in records] == ["treatment", "baseline1", "baseline2"]
    assert seen == {"treatment": ['{"expr":1}'], "baseline1": ['{"code":"b1"}'], "baseline2": ['{"code":"b2"}']}
    assert len(assignment.messages) == 3
    for messages in assignment.messages:
        assert messages[-1] == {"role": "user", "content": case.description}
        assert "JSON" in messages[0]["content"] and "credit_score" in messages[0]["content"]
    assert '"$defs"' in assignment.messages[0][0]["content"]  # Tratamiento lleva el AST schema
    assert '{"code"' in assignment.messages[1][0]["content"]
    assert "mypy --strict" in assignment.messages[2][0]["content"]
    assert "mypy" not in assignment.messages[1][0]["content"]
    for r in records:
        assert_record_shape(r)
        assert (r["run_id"], r["case_id"], r["model"]) == ("run-1", "RULE-001", "m-big")


# --- Ruteo a partir del outcome de LLMCall --------------------------------


@pytest.mark.parametrize(
    "outcome", ["generation_failed", "quota_exhausted", "transport_error", "request_error"]
)
def test_route_call_llm_failure_is_llm_error_without_running(outcome: Outcome) -> None:
    seen: list[str] = []
    runner = fixed_runner({"outcome": "executed", "stage": "execution", "result": None, "error": None}, seen)

    record = route_call(llm_call(outcome), runner, {}, gamma={}, run_id="r", case_id="c", group="baseline1")

    assert seen == []
    assert record["outcome"] == "llm_error" and record["stage"] == "llm"
    assert record["error"] is not None and record["error"]["code"] == outcome
    assert_record_shape(record)


def test_route_call_ok_without_content_is_llm_error() -> None:
    seen: list[str] = []
    runner = fixed_runner({"outcome": "executed", "stage": "execution", "result": None, "error": None}, seen)

    record = route_call(llm_call("ok", None), runner, {}, gamma={}, run_id="r", case_id="c", group="treatment")

    assert seen == []
    assert record["error"] == {"code": "missing_content", "message": "status 200: None"}
    assert_record_shape(record)


def test_route_call_ok_copies_runner_verdict_and_raw_output() -> None:
    blocked: Verdict = {
        "outcome": "blocked",
        "stage": "typecheck",
        "result": None,
        "error": {"code": "BRANCH_MISMATCH", "message": "x"},
    }
    seen: list[str] = []
    record = route_call(
        llm_call(content="{roto"), fixed_runner(blocked, seen), {}, gamma={}, run_id="r", case_id="c", group="treatment"
    )

    assert seen == ["{roto"]
    assert record["llm_raw"] == "{roto"
    assert (record["outcome"], record["stage"], record["result"], record["error"]) == (
        blocked["outcome"],
        blocked["stage"],
        blocked["result"],
        blocked["error"],
    )
    assert_record_shape(record)


# --- Runner del Tratamiento: engine por subproceso ------------------------


def test_run_engine_sends_raw_output_and_copies_verdict(tmp_path: Path) -> None:
    env = {"credit_score": 750}
    verdict = run_engine("  {crudo sin reparar", env, fake_engine(tmp_path, EXECUTED))

    assert verdict == json.loads(EXECUTED)
    assert (tmp_path / "stdin.txt").read_text() == "  {crudo sin reparar"
    args = json.loads((tmp_path / "args.json").read_text())
    assert args[0] == "--env" and json.loads(args[1]) == env and len(args) == 2


def test_run_engine_blocked(tmp_path: Path) -> None:
    assert run_engine("{}", {}, fake_engine(tmp_path, BLOCKED, exit_code=3)) == json.loads(BLOCKED)


def test_run_engine_internal_error_is_runtime_error(tmp_path: Path) -> None:
    verdict = run_engine("{}", {}, fake_engine(tmp_path, "", exit_code=70))
    assert verdict["outcome"] == "runtime_error" and verdict["stage"] == "execution"
    assert verdict["error"] is not None and verdict["error"]["code"] == "ENGINE_INTERNAL"


def test_run_engine_timeout(tmp_path: Path) -> None:
    verdict = run_engine("{}", {}, fake_engine(tmp_path, EXECUTED, sleep=5), timeout=0.5)
    assert verdict["outcome"] == "timeout"
    assert verdict["error"] is not None and verdict["error"]["code"] == "TIMEOUT"


def test_run_engine_usage_error_aborts(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="64"):
        run_engine("{}", {}, fake_engine(tmp_path, "", exit_code=64))


def test_run_engine_rejects_verdict_inconsistent_with_exit_code(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="fuera de contrato"):
        run_engine("{}", {}, fake_engine(tmp_path, BLOCKED, exit_code=0))


@pytest.mark.skipif(shutil.which("engine") is None, reason="binario del engine no instalado")
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_run_engine_with_real_engine_matches_fixture(fixture: Path) -> None:
    case = json.loads(fixture.read_text(encoding="utf-8"))
    verdict = run_engine(case["llm_raw"], case["env"], ["engine"])
    expected = case["expected_verdict"]

    assert (verdict["outcome"], verdict["stage"]) == (expected["outcome"], expected["stage"])
    if expected["outcome"] == "executed":
        assert verdict["result"] == expected["result"]
    else:
        assert verdict["error"] is not None and verdict["error"]["code"] == expected["error_code"]


# --- Registro JSON Lines ---------------------------------------------------


def test_append_jsonl_writes_one_line_per_record_and_appends(tmp_path: Path) -> None:
    out = tmp_path / "out" / "records.jsonl"
    first = route_call(llm_call("quota_exhausted"), fixed_runner(json.loads(EXECUTED), []), {}, gamma={}, run_id="r", case_id="c1", group="treatment")
    second = route_call(llm_call(content="{\"expr\": \"ñ\"}"), fixed_runner(json.loads(EXECUTED), []), {}, gamma={}, run_id="r", case_id="c2", group="treatment")

    append_jsonl(out, [first])
    append_jsonl(out, [second])

    lines = out.read_bytes().decode("utf-8").split("\n")
    assert lines[-1] == "" and len(lines) == 3
    assert [json.loads(line) for line in lines[:2]] == [first, second]
    assert "ñ" in lines[1]
    for line in lines[:2]:
        assert_record_shape(json.loads(line))
