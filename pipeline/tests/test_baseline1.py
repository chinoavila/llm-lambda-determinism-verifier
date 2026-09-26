from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from pipeline.baselines import baseline1
from pipeline.baselines.baseline1 import extract_code, run_baseline_1
from pipeline.baselines.sandbox import to_verdict

FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"


# --- Extracción de `code` ----------------------------------------------------


def test_extract_code() -> None:
    assert extract_code('{"code": "x = 1"}') == "x = 1"
    assert extract_code('{"code": "x = 1", "extra": true}') == "x = 1"


@pytest.mark.parametrize("raw", ["", "{roto", "[]", '{"codigo": "x"}', '{"code": 1}', '"x = 1"'])
def test_extract_code_rejects(raw: str) -> None:
    assert extract_code(raw) is None


def test_invalid_response_does_not_reach_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no debería ejecutar")

    monkeypatch.setattr(baseline1, "run_in_sandbox", fail)
    verdict = run_baseline_1("{roto", {})
    assert verdict["outcome"] == "runtime_error" and verdict["stage"] == "execution"
    assert verdict["error"] is not None and verdict["error"]["code"] == "InvalidResponse"


# --- Mapeo del resultado del sandbox ------------------------------------------


@pytest.mark.parametrize(
    ("result", "outcome", "code"),
    [
        ({"status": "exception", "name": "KeyError", "message": "'x'"}, "runtime_error", "KeyError"),
        ({"status": "timeout", "timeout_seconds": 5.0}, "timeout", "TIMEOUT"),
        ({"status": "crash", "message": "sin resultado"}, "runtime_error", "SANDBOX_CRASH"),
    ],
)
def test_to_verdict_failures(result: dict[str, Any], outcome: str, code: str) -> None:
    verdict = to_verdict(result)
    assert (verdict["outcome"], verdict["stage"], verdict["result"]) == (outcome, "execution", None)
    assert verdict["error"] is not None and verdict["error"]["code"] == code


def test_to_verdict_ok() -> None:
    assert to_verdict({"status": "ok", "type": "Int", "value": 3}) == {
        "outcome": "executed",
        "stage": "execution",
        "result": {"type": "Int", "value": 3},
        "error": None,
    }


def test_sandbox_result_reaches_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any, float]] = []

    def fake(code: str, env: Any, *, timeout: float) -> dict[str, Any]:
        calls.append((code, env, timeout))
        return {"status": "ok", "type": "Bool", "value": True}

    monkeypatch.setattr(baseline1, "run_in_sandbox", fake)
    verdict = run_baseline_1('{"code": "def evaluate_rule(d): return True"}', {"a": 1}, timeout=2)
    assert calls == [("def evaluate_rule(d): return True", {"a": 1}, 2)]
    assert verdict["outcome"] == "executed"


# --- Fixtures compartidas, contra el sandbox real ------------------------------

EXPECTED: dict[str, tuple[str, Any]] = {
    "rule-001": ("executed", {"type": "Bool", "value": True}),
    "rule-002": ("runtime_error", "SyntaxError"),
    "rule-003": ("runtime_error", "TypeError"),
    "rule-004": ("runtime_error", "KeyError"),
    # El engine bloquea este caso (BRANCH_MISMATCH); Baseline 1 lo ejecuta.
    "rule-005": ("executed", {"type": "String", "value": "Rejected"}),
    "rule-006": ("executed", {"type": "Bool", "value": True}),
    "rule-007": ("runtime_error", "SyntaxError"),
    # Decimal <= float se puede comparar en Python.
    "rule-008": ("executed", {"type": "Bool", "value": True}),
    "rule-009": ("executed", {"type": "Bool", "value": True}),
    "rule-010": ("executed", {"type": "Bool", "value": True}),
    "rule-011": ("runtime_error", "ZeroDivisionError"),
    "rule-012": ("executed", {"type": "Bool", "value": False}),
    # El engine lo bloquea (% sobre Decimal); Python lo ejecuta.
    "rule-013": ("executed", {"type": "Bool", "value": False}),
    # int / int en Python es float: no exacto, se registra como Other.
    "rule-014": ("executed", {"type": "Other", "value": "833.3333333333334"}),
    # El engine lo bloquea (700.5 declarado Int); en Python no hay value_type.
    "rule-015": ("executed", {"type": "Bool", "value": True}),
}


@pytest.mark.skipif("SANDBOX_IO" not in os.environ, reason="sandbox no disponible")
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixtures_with_real_sandbox(name: str) -> None:
    case = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    llm_raw = json.dumps({"code": case["python_code"]})
    verdict = run_baseline_1(llm_raw, case["env"])

    outcome, expected = EXPECTED[name]
    assert verdict["outcome"] == outcome and verdict["stage"] == "execution"
    if outcome == "executed":
        assert verdict["result"] == expected and verdict["error"] is None
    else:
        assert verdict["error"] is not None and verdict["error"]["code"] == expected
