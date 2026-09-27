from __future__ import annotations

import json
from decimal import Decimal
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from pipeline.llm import Attempt, LLMCall, Outcome
from pipeline.orchestrator import (
    GROUPS,
    Case,
    CaseError,
    EngineError,
    Group,
    Record,
    Runner,
    Scenario,
    Verdict,
    append_jsonl,
    case_gamma,
    load_case,
    read_case,
    build_messages,
    per_scenario,
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


def fixed_runner(verdict: Verdict, seen: list[Any]) -> Runner:
    """Runner por escenario que siempre da `verdict` y anota (llm_raw, env) en `seen`."""

    def runner(llm_raw: str, env: Any, gamma: Any) -> Verdict:
        seen.append((llm_raw, dict(env)))
        return verdict

    return per_scenario(runner)


SCENARIOS = (Scenario("s1", {"credit_score": 750}), Scenario("s2", {"credit_score": 650}))


def route(call: LLMCall, runner: Runner, case_id: str = "c", group: Group = "treatment") -> list[Record]:
    return route_call(
        call, runner, SCENARIOS, gamma={}, run_id="r", case_id=case_id, group=group, repetition=1
    )


def assert_record_shape(record: Any) -> None:
    """Chequeo mínimo contra el contrato (sin dependencias de jsonschema)."""
    assert set(record) == set(RECORD_SCHEMA["required"])
    assert record["schema_version"] == "2.0"
    assert isinstance(record["repetition"], int) and record["repetition"] >= 1
    assert isinstance(record["scenario_id"], str) and record["scenario_id"]
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


OK_VERDICT: Verdict = {
    "outcome": "executed",
    "stage": "execution",
    "result": {"type": "Bool", "value": True},
    "error": None,
}


def test_run_case_calls_llm_once_per_group_on_same_model() -> None:
    seen: dict[Group, list[Any]] = {g: [] for g in GROUPS}
    runners = {g: fixed_runner(OK_VERDICT, seen[g]) for g in GROUPS}
    assignment = FakeAssignment(
        [llm_call(content='{"expr":1}'), llm_call(content='{"code":"b1"}'), llm_call(content='{"code":"b2"}')]
    )
    case = Case("RULE-001", "Aprobar si credit_score > 700", SCENARIOS)

    records = run_case(case, assignment, runners, {"credit_score": "Int"}, run_id="run-1")

    # Una generación por grupo, ejecutada contra los dos escenarios, en orden.
    assert [(r["group"], r["scenario_id"]) for r in records] == [
        ("treatment", "s1"), ("treatment", "s2"),
        ("baseline1", "s1"), ("baseline1", "s2"),
        ("baseline2", "s1"), ("baseline2", "s2"),
    ]  # fmt: skip
    assert seen["treatment"] == [('{"expr":1}', {"credit_score": 750}), ('{"expr":1}', {"credit_score": 650})]
    assert [raw for raw, _ in seen["baseline2"]] == ['{"code":"b2"}', '{"code":"b2"}']
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
        assert (r["run_id"], r["case_id"], r["model"], r["repetition"]) == ("run-1", "RULE-001", "m-big", 1)


def test_run_case_repetitions_are_new_generations() -> None:
    runners = {g: fixed_runner(OK_VERDICT, []) for g in GROUPS}
    calls = [llm_call(content=f'{{"n":{i}}}') for i in range(6)]
    assignment = FakeAssignment(calls)
    case = Case("RULE-001", "regla", SCENARIOS)

    records = run_case(case, assignment, runners, {}, run_id="r", repetitions=2)

    assert len(assignment.messages) == 6  # 2 repeticiones x 3 grupos
    assert [r["repetition"] for r in records] == [1] * 6 + [2] * 6
    assert {r["llm_raw"] for r in records if r["repetition"] == 2 and r["group"] == "treatment"} == {'{"n":3}'}


def test_run_case_rejects_zero_repetitions() -> None:
    with pytest.raises(ValueError):
        run_case(Case("c", "d", SCENARIOS), FakeAssignment([]), {}, {}, run_id="r", repetitions=0)


# --- Ruteo a partir del outcome de LLMCall --------------------------------


@pytest.mark.parametrize(
    "outcome", ["generation_failed", "quota_exhausted", "transport_error", "request_error"]
)
def test_route_call_llm_failure_is_llm_error_in_every_scenario(outcome: Outcome) -> None:
    seen: list[Any] = []
    records = route(llm_call(outcome), fixed_runner(OK_VERDICT, seen), group="baseline1")

    assert seen == []
    assert [r["scenario_id"] for r in records] == ["s1", "s2"]
    for record in records:
        assert record["outcome"] == "llm_error" and record["stage"] == "llm"
        assert record["error"] is not None and record["error"]["code"] == outcome
        assert_record_shape(record)


def test_route_call_ok_without_content_is_llm_error() -> None:
    seen: list[Any] = []
    records = route(llm_call("ok", None), fixed_runner(OK_VERDICT, seen))

    assert seen == []
    assert [r["error"] for r in records] == [{"code": "missing_content", "message": "status 200: None"}] * 2
    for record in records:
        assert_record_shape(record)


def test_route_call_same_raw_output_against_each_scenario() -> None:
    blocked: Verdict = {
        "outcome": "blocked",
        "stage": "typecheck",
        "result": None,
        "error": {"code": "BRANCH_MISMATCH", "message": "x"},
    }
    seen: list[Any] = []
    records = route(llm_call(content="{roto"), fixed_runner(blocked, seen))

    assert seen == [("{roto", {"credit_score": 750}), ("{roto", {"credit_score": 650})]
    for record in records:
        assert record["llm_raw"] == "{roto"
        assert (record["outcome"], record["stage"], record["result"], record["error"]) == (
            blocked["outcome"],
            blocked["stage"],
            blocked["result"],
            blocked["error"],
        )
        assert_record_shape(record)


def test_route_call_rejects_runner_with_wrong_count() -> None:
    def short(llm_raw: str, envs: Any, gamma: Any) -> list[Any]:
        return [(OK_VERDICT, 0)]

    with pytest.raises(RuntimeError, match="1 veredictos para 2"):
        route(llm_call(), short)


# --- Casos de entrada (contracts/README.md §5) ------------------------------


def test_load_case_reads_pipeline_fields_and_ignores_corpus_fields() -> None:
    case = load_case(
        {
            "case_id": "RULE-042",
            "category": 3,
            "description": "regla",
            "canonical_ast": {"expr": {}},
            "scenarios": [
                {"scenario_id": "a", "env": {"x": 1}, "expected": {"type": "Bool", "value": True}},
                {"scenario_id": "b", "env": {"x": 2}},
            ],
        }
    )
    assert case == Case("RULE-042", "regla", (Scenario("a", {"x": 1}), Scenario("b", {"x": 2})))


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"description": "d", "scenarios": [{"scenario_id": "a", "env": {}}]}, "case_id"),
        ({"case_id": "c", "scenarios": [{"scenario_id": "a", "env": {}}]}, "description"),
        ({"case_id": "c", "description": "d", "scenarios": []}, "no vacía"),
        ({"case_id": "c", "description": "d", "scenarios": [{"env": {}}]}, "scenario_id y env"),
        (
            {"case_id": "c", "description": "d", "scenarios": [{"scenario_id": "a", "env": {}}] * 2},
            "repetido",
        ),
    ],
)
def test_load_case_rejects_invalid_cases(data: dict[str, Any], match: str) -> None:
    with pytest.raises(CaseError, match=match):
        load_case(data)


def test_case_gamma_requires_same_gamma_in_every_scenario(tmp_path: Path) -> None:
    same = fake_engine(tmp_path, '{"x":"Int"}\n')
    assert case_gamma(Case("c", "d", (Scenario("a", {"x": 1}), Scenario("b", {"x": 2}))), same) == {"x": "Int"}


def test_case_gamma_rejects_different_gammas() -> None:
    engine = ["engine"] if shutil.which("engine") else None
    if engine is None:
        pytest.skip("binario del engine no instalado")
    case = Case("c", "d", (Scenario("a", {"x": 1}), Scenario("b", {"x": "uno"})))
    with pytest.raises(CaseError, match="distinto"):
        case_gamma(case, engine)


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


def test_run_engine_program_runtime_error_is_copied(tmp_path: Path) -> None:
    runtime = '{"outcome":"runtime_error","stage":"execution","result":null,"error":{"code":"DIVISION_BY_ZERO","message":"x"}}\n'
    assert run_engine("{}", {}, fake_engine(tmp_path, runtime, exit_code=4)) == json.loads(runtime)


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
    first = route(llm_call("quota_exhausted"), fixed_runner(json.loads(EXECUTED), []), case_id="c1")
    second = route(llm_call(content="{\"expr\": \"ñ\"}"), fixed_runner(json.loads(EXECUTED), []), case_id="c2")

    append_jsonl(out, first)
    append_jsonl(out, second)

    lines = out.read_bytes().decode("utf-8").split("\n")
    assert lines[-1] == "" and len(lines) == 5
    assert [json.loads(line) for line in lines[:4]] == [*first, *second]
    assert "ñ" in lines[2]
    for line in lines[:4]:
        assert_record_shape(json.loads(line))


# --- Decimales exactos del corpus ---------------------------------------------


def test_read_case_keeps_decimals_exact(tmp_path: Path) -> None:
    path = tmp_path / "rule.json"
    path.write_text(
        '{"case_id": "c", "description": "d", "scenarios": [{"scenario_id": "a", "env": {"cuota": 1250.75, "n": 5000}}]}',
        encoding="utf-8",
    )
    case = read_case(path)
    env = case.scenarios[0].env
    assert env == {"cuota": 1250.75, "n": 5000}
    assert json.dumps(env) == '{"cuota": 1250.75, "n": 5000}'  # lo que reciben engine y sandbox


def test_load_case_rejects_decimals_that_would_lose_digits() -> None:
    data = {"case_id": "c", "description": "d", "scenarios": [{"scenario_id": "a", "env": {"x": Decimal("0.12345678901234567890123")}}]}
    with pytest.raises(CaseError, match="sin pérdida"):
        load_case(data)


def test_read_case_rejects_non_json(tmp_path: Path) -> None:
    path = tmp_path / "rule.json"
    path.write_text("{roto", encoding="utf-8")
    with pytest.raises(CaseError, match="no es JSON"):
        read_case(path)


# --- Prompts: misma información de tipos en los tres grupos --------------------


def test_prompts_share_types_note_and_add_language_specifics() -> None:
    gamma = {"cuota": "Decimal"}
    systems = {g: build_messages(g, "regla", gamma)[0]["content"] for g in GROUPS}
    for text in systems.values():
        assert "Decimal un número decimal exacto" in text
    assert "/ siempre da Decimal" in systems["treatment"]
    assert "decimal.Decimal" in systems["baseline1"] and "decimal.Decimal" in systems["baseline2"]
    assert "decimal.Decimal" not in systems["treatment"]
    assert "'cuota': Decimal" in systems["baseline2"]


# --- La clave de respuestas del corpus no llega al LLM (docs/corpus.md) ------------

REPO = Path(__file__).parents[2]
CORPUS_RULES = sorted((REPO / "corpus").glob("*.json")) + sorted(
    (Path(__file__).parent / "data" / "corpus").glob("*.json")
)


def prompts_of(path: Path, gamma: dict[str, str]) -> str:
    """Todo lo que `run_case` le manda al LLM para la regla de `path`, en los tres grupos."""
    case = read_case(path)
    assignment = FakeAssignment([llm_call("quota_exhausted") for _ in GROUPS])
    runners = {g: fixed_runner(OK_VERDICT, []) for g in GROUPS}
    run_case(case, assignment, runners, gamma, run_id="r")
    assert len(assignment.messages) == len(GROUPS)
    return json.dumps(assignment.messages, ensure_ascii=False)


def test_corpus_answer_key_never_reaches_the_llm(tmp_path: Path) -> None:
    """Marcas en cada campo que el LLM no debe ver: ninguna aparece en los prompts."""
    data = json.loads((Path(__file__).parent / "data" / "corpus" / "ejemplo-cat3-cuota.json").read_text("utf-8"))
    data["canonical_ast"]["expr"]["right"] = {"type": "Literal", "value": "CANARIO_AST", "value_type": "String"}
    data["canonical_python"] = "# CANARIO_PY\n" + data["canonical_python"]
    data["source"] = {"kind": "adapted", "reference": "CANARIO_SOURCE", "license": "CANARIO_LICENSE"}
    for s in data["scenarios"]:
        s["expected"] = {"type": "String", "value": "CANARIO_EXPECTED"}
    path = tmp_path / "regla.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    prompts = prompts_of(path, data["gamma"])

    assert "CANARIO" not in prompts
    assert data["description"] in prompts


@pytest.mark.parametrize("path", CORPUS_RULES, ids=lambda p: p.stem)
def test_corpus_descriptions_do_not_embed_the_answer_key(path: Path) -> None:
    """Ninguna regla del corpus copia su AST, su Python o sus expected en el enunciado."""
    data = json.loads(path.read_text(encoding="utf-8"))
    prompts = prompts_of(path, data["gamma"])

    leaks = [json.dumps(data["canonical_ast"]["expr"], ensure_ascii=False), data["canonical_python"].strip()]
    leaks += [json.dumps(s["expected"], ensure_ascii=False) for s in data["scenarios"] if "expected" in s]
    for leak in leaks:
        assert json.dumps(leak, ensure_ascii=False)[1:-1] not in prompts, leak[:80]
