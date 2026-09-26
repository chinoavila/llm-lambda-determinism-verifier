from __future__ import annotations

import json
import os
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pipeline.cli import check_cases, main
from pipeline.corpus import Report, check_balance, check_case, check_fields, plain, write_expected
from pipeline.orchestrator import CaseError

EXAMPLES = Path(__file__).parent / "data" / "corpus"
CUOTA = EXAMPLES / "ejemplo-cat3-cuota.json"
REAL_STACK = pytest.mark.skipif(
    shutil.which("engine") is None or "SANDBOX_IO" not in os.environ,
    reason="necesita el engine y el sandbox (correr en Docker Compose)",
)


def issues(report: Report) -> list[str]:
    return [f"{level}: {msg}" for level, msg in report.issues]


def edited(tmp_path: Path, change: Any, source: Path = CUOTA) -> Path:
    """Copia de una regla de ejemplo, con `change(data)` aplicado."""
    data = json.loads(source.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / source.name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# --- Piezas sin engine ni sandbox ---------------------------------------------


def test_check_fields_reports_each_problem() -> None:
    report = Report(Path("x.json"))
    check_fields({"category": 4, "domain": "", "gamma": [], "canonical_ast": {}, "canonical_python": 1}, report)
    assert issues(report) == [
        "error: category debe ser 1, 2 o 3, no 4",
        "error: domain debe ser un texto no vacío",
        "error: gamma debe ser un objeto {nombre: tipo}",
        'error: canonical_ast debe ser un programa {"expr": ...}',
        "error: canonical_python debe ser el código como texto",
    ]
    missing = Report(Path("x.json"))
    check_fields({}, missing)
    assert issues(missing) == [
        "error: faltan campos del corpus: ['category', 'domain', 'gamma', 'canonical_ast', 'canonical_python']"
    ]


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([True, False, True, False], []),
        ([True, True, False], []),
        ([True, True, True, False], ["aviso: no está balanceada: 3 true / 1 false"]),
        ([True, True], ["error: todos los escenarios dan True: la regla no se prueba"]),
    ],
)
def test_check_balance_for_bool_rules(values: list[bool], expected: list[str]) -> None:
    report = Report(Path("x.json"))
    check_balance([{"type": "Bool", "value": v} for v in values], report)
    assert issues(report) == expected


def test_check_balance_for_other_results_needs_two_values() -> None:
    same, varied = Report(Path("a")), Report(Path("b"))
    check_balance([{"type": "String", "value": "Alto"}] * 3, same)
    check_balance([{"type": "String", "value": "Alto"}, {"type": "String", "value": "Bajo"}], varied)
    assert issues(same) == ["error: todos los escenarios dan el mismo resultado: la regla no se prueba"]
    assert issues(varied) == []


def test_plain_removes_decimals_without_losing_digits() -> None:
    assert plain({"a": [Decimal("0.30")], "b": 1}, "x") == {"a": [0.3], "b": 1}
    with pytest.raises(CaseError, match="sin pérdida"):
        plain({"a": Decimal("0.12345678901234567890123")}, "x")


# --- Contra el engine y el sandbox reales ---------------------------------------


@REAL_STACK
@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.stem)
def test_examples_are_valid_and_complete(path: Path) -> None:
    report, _ = check_case(path)
    assert report.ok and report.issues == []


@REAL_STACK
def test_wrong_expected_is_an_error_and_never_overwritten(tmp_path: Path) -> None:
    def flip(data: dict[str, Any]) -> None:
        data["scenarios"][0]["expected"] = {"type": "Bool", "value": True}

    path = edited(tmp_path, flip)
    report, data = check_case(path)
    assert not report.ok
    assert any("S1: expected declarado" in m for m in issues(report))
    assert data is not None and write_expected(path, data, report) == 0


@REAL_STACK
def test_missing_expected_is_filled_with_write(tmp_path: Path) -> None:
    def drop(data: dict[str, Any]) -> None:
        for s in data["scenarios"]:
            s.pop("expected")

    path = edited(tmp_path, drop)
    report, data = check_case(path)
    assert report.ok and len(report.issues) == 4  # un aviso por escenario
    assert data is not None and write_expected(path, data, report) == 4
    again, _ = check_case(path)
    assert again.ok and again.issues == []
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["scenarios"][0]["env"]["cuota"] == 1500.5  # los decimales se conservan


@REAL_STACK
@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(gamma={"cuota": "Int", "ingreso": "Int", "tiene_morosidades": "Bool"}), "gamma declarado"),
        (lambda d: d.update(canonical_python="def evaluate_rule(data):\n    return True\n"), "el Python canónico da"),
        (lambda d: d["canonical_ast"]["expr"].update(op="OR"), "S1: expected declarado"),
        (lambda d: d["canonical_ast"].update(expr={"type": "Var", "name": "nope"}), "el AST canónico no ejecuta"),
        (lambda d: d["scenarios"][1]["env"].update(cuota=1500), "Γ de S2"),
    ],
    ids=["gamma", "python", "ast-distinto", "ast-bloqueado", "gamma-por-escenario"],
)
def test_detects_inconsistent_rules(tmp_path: Path, change: Any, message: str) -> None:
    report, _ = check_case(edited(tmp_path, change))
    assert not report.ok
    assert any(message in m for m in issues(report)), issues(report)


@REAL_STACK
def test_check_cases_exit_codes(tmp_path: Path) -> None:
    lines: list[str] = []
    assert check_cases([EXAMPLES], out=lines.append) == 0
    assert lines[-1] == "3/3 reglas sin errores"

    bad = edited(tmp_path, lambda d: d.update(category=7))
    lines.clear()
    assert check_cases([bad], out=lines.append) == 1
    assert lines[0] == "ERROR EJ-CAT3-CUOTA (ejemplo-cat3-cuota.json)"


def test_check_case_command_requires_paths() -> None:
    with pytest.raises(SystemExit):
        main(["check-case"])
