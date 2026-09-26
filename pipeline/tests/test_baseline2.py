from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from pipeline.baselines import baseline2
from pipeline.baselines.baseline2 import (
    PREAMBLE_LINES,
    check_signature,
    data_preamble,
    run_baseline_2,
    run_baseline_2_scenarios,
    run_mypy,
)
from pipeline.orchestrator import build_messages, print_gamma

FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"
GAMMA = {"credit_score": "Int", "has_defaults": "Bool", "customer_tier": "String"}


def no_sandbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Reemplaza el sandbox: guarda el programa y devuelve `True`."""
    programs: list[str] = []

    def fake(program: str, env: Any, *, timeout: float) -> dict[str, Any]:
        programs.append(program)
        return {"status": "ok", "type": "Bool", "value": True}

    monkeypatch.setattr(baseline2, "run_in_sandbox", fake)
    return programs


def raw(code: str) -> str:
    return json.dumps({"code": code})


# --- Preámbulo Data y prompt ------------------------------------------------


def test_data_preamble_from_gamma() -> None:
    assert data_preamble(GAMMA) == (
        "from decimal import Decimal\n"
        "from typing import TypedDict\n"
        "Data = TypedDict(\"Data\", {'credit_score': int, 'customer_tier': str, 'has_defaults': bool})\n"
    )


def test_data_preamble_maps_decimal() -> None:
    preamble = data_preamble({"cuota": "Decimal", "n": "Int"})
    assert "'cuota': Decimal, 'n': int" in preamble
    assert preamble.count("\n") == PREAMBLE_LINES


def test_mypy_rejects_decimal_times_float() -> None:
    code = "def evaluate_rule(data: Data) -> Decimal:\n    return data['cuota'] * 0.30\n"
    result = run_mypy(data_preamble({"cuota": "Decimal"}) + code)
    assert result is not None and result[0] == 1 and "Unsupported operand" in result[1]


def test_data_preamble_accepts_python_keywords() -> None:
    ast.parse(data_preamble({"class": "Int", "if": "Bool"}))


def test_baseline2_prompt_shows_data_and_signature() -> None:
    system = build_messages("baseline2", "regla", GAMMA)[0]["content"]
    assert data_preamble(GAMMA) in system
    assert "evaluate_rule(data: Data)" in system and "mypy --strict" in system


# --- Etapa parse -------------------------------------------------------------


@pytest.mark.parametrize("llm_raw", ["{roto", '{"codigo": "x"}'])
def test_invalid_response_blocked_at_parse(llm_raw: str) -> None:
    verdict = run_baseline_2(llm_raw, {}, GAMMA)
    assert (verdict["outcome"], verdict["stage"]) == ("blocked", "parse")
    assert verdict["error"] is not None and verdict["error"]["code"] == "InvalidResponse"


def test_syntax_error_blocked_at_parse() -> None:
    verdict = run_baseline_2(raw("def evaluate_rule(data: Data) -> bool\n    return True\n"), {}, GAMMA)
    assert (verdict["outcome"], verdict["stage"]) == ("blocked", "parse")
    assert verdict["error"] is not None and verdict["error"]["code"] == "SyntaxError"


# --- Etapa typecheck: firma --------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "x = 1\n",
        "def evaluate_rule(data):\n    return True\n",
        "def evaluate_rule(data: dict[str, object]) -> bool:\n    return True\n",
        "def evaluate_rule(data: Data, extra: int) -> bool:\n    return True\n",
        "def evaluate_rule(*data: Data) -> bool:\n    return True\n",
        "class C:\n    def evaluate_rule(self, data: Data) -> bool:\n        return True\n",
    ],
)
def test_signature_mismatch(code: str) -> None:
    assert check_signature(ast.parse(code)) is not None
    verdict = run_baseline_2(raw(code), {}, GAMMA)
    assert (verdict["outcome"], verdict["stage"]) == ("blocked", "typecheck")
    assert verdict["error"] is not None and verdict["error"]["code"] == "SignatureMismatch"


def test_signature_ok() -> None:
    assert check_signature(ast.parse("def evaluate_rule(data: Data) -> bool:\n    return True\n")) is None


# --- Etapa typecheck: mypy (real, no ejecuta el código) ------------------------


def test_mypy_rejects_wrong_types(monkeypatch: pytest.MonkeyPatch) -> None:
    programs = no_sandbox(monkeypatch)
    code = "def evaluate_rule(data: Data) -> bool:\n    return data['credit_score'] > 'High'\n"
    verdict = run_baseline_2(raw(code), {"credit_score": 750}, GAMMA)

    assert (verdict["outcome"], verdict["stage"]) == ("blocked", "typecheck")
    assert verdict["error"] is not None and verdict["error"]["code"] == "mypy"
    assert verdict["error"]["message"].startswith("rule.py:")  # sin ruta temporal
    assert programs == []


def test_mypy_does_not_execute_code(tmp_path: Path) -> None:
    marker = tmp_path / "ejecutado"
    code = f"open({str(marker)!r}, 'w').write('x')\ndef evaluate_rule(data: Data) -> bool:\n    return True\n"
    result = run_mypy(data_preamble(GAMMA) + code)
    assert result is not None and result[0] == 0
    assert not marker.exists()


def test_mypy_ignores_repo_config() -> None:
    # El repo tiene [tool.mypy] strict; acá se exige --strict igual con config vacía.
    result = run_mypy("def f(x):\n    return x\n")
    assert result is not None and result[0] == 1 and "no-untyped-def" in result[1]


def test_mypy_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline2, "run_mypy", lambda program: None)
    code = "def evaluate_rule(data: Data) -> bool:\n    return True\n"
    verdict = run_baseline_2(raw(code), {}, GAMMA)
    assert (verdict["outcome"], verdict["stage"]) == ("timeout", "typecheck")


def test_passes_mypy_then_executes_program_with_preamble(monkeypatch: pytest.MonkeyPatch) -> None:
    programs = no_sandbox(monkeypatch)
    code = "def evaluate_rule(data: Data) -> bool:\n    return data['credit_score'] > 700\n"
    verdict = run_baseline_2(raw(code), {"credit_score": 750}, GAMMA)

    assert verdict["outcome"] == "executed" and verdict["stage"] == "execution"
    assert programs == [data_preamble(GAMMA) + code]


# --- Fixtures compartidas, con firma tipada, contra mypy y el sandbox reales ---

TYPED_CODE = {
    "rule-001": "def evaluate_rule(data: Data) -> bool:\n    return data['credit_score'] > 700 and not data['has_defaults']\n",
    "rule-002": "def evaluate_rule(data: Data) -> bool\n    return data['credit_score'] > 700\n",
    "rule-003": "def evaluate_rule(data: Data) -> bool:\n    return data['credit_score'] > 'High'\n",
    "rule-004": "def evaluate_rule(data: Data) -> bool:\n    return data['risk_level'] == 'Low'\n",
    "rule-005": "def evaluate_rule(data: Data) -> int | str:\n    if data['credit_score'] > 700:\n        return 500\n    else:\n        return \"Rejected\"\n",
    "rule-006": "def evaluate_rule(data: Data) -> bool:\n    return (lambda s: s > 700)(data['credit_score'])\n",
    "rule-007": "def evaluate_rule(data: Data) -> bool:\n    return data['credit_score'] >\n",
    "rule-008": "def evaluate_rule(data: Data) -> bool:\n    return data['cuota'] <= data['ingreso_mensual'] * Decimal('0.30')\n",
    "rule-013": "def evaluate_rule(data: Data) -> bool:\n    return data['monto'] % 100 == 0\n",
    "rule-014": "def evaluate_rule(data: Data) -> Decimal:\n    return data['monto'] / Decimal(12)\n",
}

EXPECTED: dict[str, tuple[str, str, Any]] = {
    "rule-001": ("executed", "execution", {"type": "Bool", "value": True}),
    "rule-002": ("blocked", "parse", "SyntaxError"),
    "rule-003": ("blocked", "typecheck", "mypy"),
    "rule-004": ("blocked", "typecheck", "mypy"),
    # Con `int | str` declarado, mypy lo acepta; el engine lo bloquea (BRANCH_MISMATCH).
    "rule-005": ("executed", "execution", {"type": "String", "value": "Rejected"}),
    "rule-006": ("executed", "execution", {"type": "Bool", "value": True}),
    "rule-007": ("blocked", "parse", "SyntaxError"),
    "rule-008": ("executed", "execution", {"type": "Bool", "value": True}),
    # Decimal % int es válido en Python y mypy lo acepta; el engine lo bloquea (OPERAND_MISMATCH).
    "rule-013": ("executed", "execution", {"type": "Bool", "value": False}),
    # Mismo texto canónico que el engine para el mismo valor.
    "rule-014": ("executed", "execution", {"type": "Decimal", "value": "833.3333333333333333333333333"}),
}


@pytest.mark.skipif("SANDBOX_IO" not in os.environ, reason="sandbox no disponible")
@pytest.mark.skipif(shutil.which("engine") is None, reason="binario del engine no instalado")
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixtures_with_real_mypy_and_sandbox(name: str) -> None:
    case = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    gamma = print_gamma(case["env"], ["engine"])  # Γ lo deduce el engine real
    verdict = run_baseline_2(raw(TYPED_CODE[name]), case["env"], gamma)

    outcome, stage, expected = EXPECTED[name]
    assert (verdict["outcome"], verdict["stage"]) == (outcome, stage)
    if outcome == "executed":
        assert verdict["result"] == expected and verdict["error"] is None
    else:
        assert verdict["error"] is not None and verdict["error"]["code"] == expected


# --- Varios escenarios por generación (contracts/README.md §3) ------------------


def test_scenarios_run_static_check_once(monkeypatch: pytest.MonkeyPatch) -> None:
    programs = no_sandbox(monkeypatch)
    mypy_calls: list[str] = []

    def fake_mypy(program: str) -> tuple[int, str]:
        mypy_calls.append(program)
        return 0, ""

    monkeypatch.setattr(baseline2, "run_mypy", fake_mypy)
    code = "def evaluate_rule(data: Data) -> bool:\n    return True\n"
    envs = [{"credit_score": 750}, {"credit_score": 650}, {"credit_score": 700}]

    timed = run_baseline_2_scenarios(raw(code), envs, GAMMA)

    assert len(mypy_calls) == 1
    assert len(programs) == 3
    assert [v["outcome"] for v, _ in timed] == ["executed"] * 3
    assert all(isinstance(ms, int) and ms >= 0 for _, ms in timed)


def test_scenarios_repeat_static_block(monkeypatch: pytest.MonkeyPatch) -> None:
    programs = no_sandbox(monkeypatch)
    timed = run_baseline_2_scenarios("{roto", [{}, {}], GAMMA)

    assert programs == []
    assert [(v["outcome"], v["stage"]) for v, _ in timed] == [("blocked", "parse")] * 2
    assert timed[0][1] == timed[1][1]
