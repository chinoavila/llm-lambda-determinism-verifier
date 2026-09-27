"""Constructores del AST del DSL y escritura de reglas del corpus.

Escribir el AST canónico a mano en JSON es largo y propenso a errores; estas
funciones lo arman con la forma de contracts/ast-schema.json. Cada tanda del
corpus es un script que las usa (ver corpus/tools/README.md).

Las reglas se escriben sin `expected`: lo calcula el engine con
`python -m pipeline check-case <archivos> --write`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

Expr = dict[str, Any]
Env = dict[str, Any]

PUBLIC_DOMAIN = "Dominio público (17 U.S.C. § 105)"
F6744 = "IRS Form 6744 (Rev. 10-2025)"


def lit(value: Any, value_type: str | None = None) -> Expr:
    """Literal. El tipo se deduce salvo para `Decimal`, que se pide explícito
    (`lit("0.70", "Decimal")`) para no confundirlo con un `float` de Python."""
    if value_type == "Decimal":
        return {"type": "Literal", "value": float(value), "value_type": "Decimal"}
    if value_type is None:
        value_type = (
            "Bool" if isinstance(value, bool) else "Int" if isinstance(value, int) else "String"
        )
    return {"type": "Literal", "value": value, "value_type": value_type}


def dec(text: str) -> Expr:
    return lit(text, "Decimal")


def var(name: str) -> Expr:
    return {"type": "Var", "name": name}


def op(operator: str, left: Expr, right: Expr) -> Expr:
    return {"type": "BinaryOp", "op": operator, "left": left, "right": right}


def eq(name: str, value: Any) -> Expr:
    return op("==", var(name), lit(value))


def all_(*xs: Expr) -> Expr:
    """`AND` encadenado a izquierda: all_(a, b, c) = (a AND b) AND c."""
    acc = xs[0]
    for x in xs[1:]:
        acc = op("AND", acc, x)
    return acc


def any_(*xs: Expr) -> Expr:
    acc = xs[0]
    for x in xs[1:]:
        acc = op("OR", acc, x)
    return acc


def not_(x: Expr) -> Expr:
    return {"type": "UnaryOp", "op": "NOT", "operand": x}


def in_(x: Expr, options: list[Any]) -> Expr:
    return {"type": "In", "value": x, "options": [lit(o) for o in options]}


def ite(condition: Expr, then: Expr, otherwise: Expr) -> Expr:
    return {"type": "IfThenElse", "condition": condition, "then": then, "else": otherwise}


def adapted(reference: str, license: str = PUBLIC_DOMAIN) -> dict[str, str]:
    return {"kind": "adapted", "reference": reference, "license": license}


ORIGINAL = {"kind": "original"}


def write_rule(
    out: Path,
    name: str,
    *,
    case_id: str,
    category: int,
    domain: str,
    source: dict[str, str],
    description: str,
    gamma: dict[str, str],
    expr: Expr,
    python: str,
    scenarios: list[tuple[str, Env]],
    generator: str | None = None,
) -> Path:
    """Escribe `out/<name>.json`. Si el archivo ya existe, conserva los `expected`
    de los escenarios que siguen iguales (mismo id y mismo env) y la `review`. `generator` queda en
    `generated_by`: la UI avisa que un cambio a mano se pierde al volver a correr el script."""
    path = out / f"{name}.json"
    previous: dict[str, Any] = {}
    old: dict[str, Any] = {}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        previous = {
            s["scenario_id"]: s for s in old.get("scenarios", []) if "expected" in s
        }
        if old.get("canonical_ast") != {"expr": expr}:
            previous = {}  # cambió la regla: el engine recalcula todo
    rows = []
    for sid, env in scenarios:
        row: dict[str, Any] = {"scenario_id": sid, "env": env}
        kept = previous.get(sid)
        if kept is not None and kept.get("env") == env:
            row["expected"] = kept["expected"]
        rows.append(row)
    data = {
        "case_id": case_id,
        "category": category,
        "domain": domain,
        "source": source,
        **({"generated_by": generator} if generator else {}),
        "description": description,
        "gamma": gamma,
        "canonical_ast": {"expr": expr},
        "canonical_python": python,
        "scenarios": rows,
    }
    if "review" in old:  # la revisión la cargan personas desde la UI: el script no la toca
        data["review"] = old["review"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
