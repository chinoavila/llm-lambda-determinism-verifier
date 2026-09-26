"""Verificación de reglas del corpus: `python -m pipeline check-case`. Ver docs/corpus.md.

El corpus no es un entregable del MVP, pero lo consume: esto asegura que cada regla sea
válida antes de gastar llamadas al LLM, y calcula `expected` con el engine sobre el AST
canónico (un resultado exacto y sin etiquetado humano).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pipeline.baselines.sandbox import run_in_sandbox, to_verdict
from pipeline.orchestrator import (
    DEFAULT_ENGINE_CMD,
    CaseError,
    EngineError,
    case_gamma,
    exact_value,
    load_case,
    run_engine,
)

CATEGORIES = (1, 2, 3)
CORPUS_FIELDS = ("category", "domain", "gamma", "canonical_ast", "canonical_python")

Level = Literal["error", "aviso"]


@dataclass
class Report:
    """Resultado de verificar una regla. `expected` es lo que calculó el engine por escenario."""

    path: Path
    case_id: str = "?"
    issues: list[tuple[Level, str]] = field(default_factory=list)
    expected: dict[str, dict[str, Any]] = field(default_factory=dict)

    def error(self, msg: str) -> None:
        self.issues.append(("error", msg))

    def warn(self, msg: str) -> None:
        self.issues.append(("aviso", msg))

    @property
    def ok(self) -> bool:
        return not any(level == "error" for level, _ in self.issues)


def plain(value: Any, where: str) -> Any:
    """Copia de `value` sin `Decimal`, apta para `json.dumps` sin perder exactitud."""
    if isinstance(value, dict):
        return {k: plain(v, f"{where}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v, f"{where}[{i}]") for i, v in enumerate(value)]
    return exact_value(value, where) if isinstance(value, Decimal) else value


def check_fields(data: Mapping[str, Any], report: Report) -> None:
    """Campos que el corpus agrega sobre contracts/case-schema.json."""
    missing = [f for f in CORPUS_FIELDS if f not in data]
    if missing:
        report.error(f"faltan campos del corpus: {missing}")
    if "category" in data and data["category"] not in CATEGORIES:
        report.error(f"category debe ser 1, 2 o 3, no {data['category']!r}")
    if "domain" in data and not (isinstance(data["domain"], str) and data["domain"]):
        report.error("domain debe ser un texto no vacío")
    if "gamma" in data and not isinstance(data["gamma"], dict):
        report.error("gamma debe ser un objeto {nombre: tipo}")
    ast = data.get("canonical_ast")
    if "canonical_ast" in data and not (isinstance(ast, dict) and set(ast) == {"expr"}):
        report.error('canonical_ast debe ser un programa {"expr": ...}')
    if "canonical_python" in data and not isinstance(data["canonical_python"], str):
        report.error("canonical_python debe ser el código como texto")


def check_balance(results: Sequence[Mapping[str, Any]], report: Report) -> None:
    """Booleanas: los dos valores, con diferencia de a lo sumo 1. Otras: al menos dos distintos."""
    if not results:
        return
    if all(r["type"] == "Bool" for r in results):
        counts = Counter(bool(r["value"]) for r in results)
        if len(counts) < 2:
            report.error(f"todos los escenarios dan {results[0]['value']}: la regla no se prueba")
        elif abs(counts[True] - counts[False]) > 1:
            report.warn(f"no está balanceada: {counts[True]} true / {counts[False]} false")
    elif len({json.dumps(r, sort_keys=True) for r in results}) < 2:
        report.error("todos los escenarios dan el mismo resultado: la regla no se prueba")


def check_case(
    path: Path,
    engine_cmd: Sequence[str] = DEFAULT_ENGINE_CMD,
    *,
    sandbox_timeout: float = 5.0,
) -> tuple[Report, dict[str, Any] | None]:
    """Verifica una regla. Devuelve el reporte y los datos leídos (para `--write`)."""
    report = Report(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except ValueError as e:
        report.error(f"no es JSON: {e}")
        return report, None
    if not isinstance(data, dict):
        report.error("la regla debe ser un objeto JSON")
        return report, None
    report.case_id = str(data.get("case_id", "?"))
    check_fields(data, report)
    try:
        case = load_case(data)
        gamma = case_gamma(case, engine_cmd)
        ast = json.dumps(plain(data.get("canonical_ast"), "canonical_ast"))
    except (CaseError, EngineError) as e:
        report.error(str(e))
        return report, data
    if not report.ok:
        return report, data

    if gamma != data["gamma"]:
        report.error(f"gamma declarado {data['gamma']} distinto del que deduce el engine {gamma}")

    results: list[dict[str, Any]] = []
    for scenario, raw in zip(case.scenarios, data["scenarios"]):
        sid = scenario.scenario_id
        verdict = run_engine(ast, scenario.env, engine_cmd)
        if verdict["outcome"] != "executed" or verdict["result"] is None:
            report.error(f"{sid}: el AST canónico no ejecuta ({verdict['stage']}: {verdict['error']})")
            continue
        expected = verdict["result"]
        results.append(expected)
        report.expected[sid] = expected

        python = to_verdict(
            run_in_sandbox(data["canonical_python"], scenario.env, timeout=sandbox_timeout)
        )
        if python["result"] != expected:
            got = python["result"] if python["result"] is not None else python["error"]
            report.error(f"{sid}: el Python canónico da {got}, el engine {expected}")

        declared = raw.get("expected")
        if declared is None:
            report.warn(f"{sid}: falta expected (el engine calcula {expected})")
        elif plain(declared, f"{sid}.expected") != expected:
            report.error(f"{sid}: expected declarado {declared} distinto del calculado {expected}")

    check_balance(results, report)
    return report, data


def write_expected(path: Path, data: dict[str, Any], report: Report) -> int:
    """Completa los `expected` que faltan con lo calculado. Nunca pisa uno existente."""
    filled = 0
    for scenario in data["scenarios"]:
        sid = scenario.get("scenario_id")
        if scenario.get("expected") is None and sid in report.expected:
            scenario["expected"] = report.expected[sid]
            filled += 1
    if filled:
        text = json.dumps(plain(data, report.case_id), ensure_ascii=False, indent=2)
        path.write_text(text + "\n", encoding="utf-8")
    return filled
