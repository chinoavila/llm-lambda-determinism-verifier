"""Baseline 2: análisis estático (`ast` + `mypy --strict`) antes de ejecutar.

Etapas (contracts/README.md §3): `parse` (JSON y `ast.parse`) → `typecheck`
(firma `evaluate_rule(data: Data)` y mypy) → `execution` (sandbox sin red).
`Data` es un TypedDict armado desde Γ que se antepone al código del LLM, tanto
para mypy como para ejecutar; el código del LLM no se modifica. El análisis no
ejecuta el código, por eso corre en `pipeline` (specs/sandbox.md).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

from pipeline.baselines.baseline1 import extract_code
from pipeline.baselines.sandbox import DEFAULT_TIMEOUT_SECONDS, run_in_sandbox, to_verdict

if TYPE_CHECKING:
    from pipeline.orchestrator import Timed, Verdict

FUNCTION = "evaluate_rule"
MYPY_TIMEOUT_SECONDS = 60.0
PYTHON_TYPES = {"Int": "int", "Decimal": "Decimal", "Bool": "bool", "String": "str"}
# Líneas que el preámbulo agrega antes del código del LLM (desplazan los mensajes de mypy).
PREAMBLE_LINES = 3


class StaticCheckError(Exception):
    """mypy no se pudo ejecutar o falló por sí mismo: abortar la corrida."""


def data_preamble(gamma: Mapping[str, str]) -> str:
    """Definición de `Data` desde Γ. Sintaxis funcional: admite claves que son palabras reservadas.

    Siempre importa `Decimal`, aunque Γ no lo use: el preámbulo tiene largo fijo.
    """
    fields = ", ".join(f"{name!r}: {PYTHON_TYPES[t]}" for name, t in sorted(gamma.items()))
    return (
        "from decimal import Decimal\n"
        "from typing import TypedDict\n"
        f'Data = TypedDict("Data", {{{fields}}})\n'
    )


def check_signature(tree: ast.Module) -> str | None:
    """Mensaje de error si no hay un `def evaluate_rule(data: Data)` a nivel de módulo."""
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == FUNCTION]
    if not defs:
        return f"no define `{FUNCTION}` a nivel de módulo"
    args = defs[-1].args
    params = [*args.posonlyargs, *args.args]
    annotation = params[0].annotation if len(params) == 1 else None
    if (
        args.vararg
        or args.kwarg
        or args.kwonlyargs
        or not isinstance(annotation, ast.Name)
        or annotation.id != "Data"
    ):
        return f"la firma debe ser `{FUNCTION}(data: Data)`"
    return None


def run_mypy(program: str, timeout: float = MYPY_TIMEOUT_SECONDS) -> tuple[int, str] | None:
    """(exit code, salida) de `mypy --strict` sobre `program`; None si vence el timeout.

    Aislado de la config y la caché del repo: directorio temporal, config vacía,
    sin caché y sin entorno heredado. Los mensajes nombran `rule.py`, no la ruta temporal.
    """
    if find_spec("mypy") is None:
        raise StaticCheckError("mypy no está instalado en el contenedor pipeline")
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "rule.py").write_text(program, encoding="utf-8")
        Path(tmp, "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
        cmd = [
            sys.executable, "-I", "-m", "mypy", "--strict",
            "--config-file", "mypy.ini", "--cache-dir", os.devnull,
            "--no-error-summary", "rule.py",
        ]  # fmt: skip
        try:
            proc = subprocess.run(
                cmd, cwd=tmp, env={}, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return None
    output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if proc.returncode not in (0, 1) and "rule.py:" not in output:
        raise StaticCheckError(f"mypy salió con {proc.returncode}: {output}")
    return proc.returncode, output


def blocked(stage: str, code: str, message: str) -> Verdict:
    return {
        "outcome": "blocked",
        "stage": "parse" if stage == "parse" else "typecheck",
        "result": None,
        "error": {"code": code, "message": message},
    }


def run_baseline_2(
    llm_raw: str,
    env: Mapping[str, object],
    gamma: Mapping[str, str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Verdict:
    """Un escenario: `(llm_raw, env, gamma) -> Verdict`."""
    checked = check_static(llm_raw, gamma)
    if not isinstance(checked, str):
        return checked
    return to_verdict(run_in_sandbox(checked, env, timeout=timeout))


def run_baseline_2_scenarios(
    llm_raw: str,
    envs: Sequence[Mapping[str, object]],
    gamma: Mapping[str, str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[Timed]:
    """Runner del grupo `baseline2`: análisis estático una vez por generación, ejecución por escenario.

    `duration_ms` de cada escenario = análisis estático + su ejecución (contracts/README.md §3).
    """
    started = time.monotonic()
    checked = check_static(llm_raw, gamma)
    static_ms = round((time.monotonic() - started) * 1000)
    if not isinstance(checked, str):
        return [(checked, static_ms) for _ in envs]
    timed: list[Timed] = []
    for env in envs:
        started = time.monotonic()
        verdict = to_verdict(run_in_sandbox(checked, env, timeout=timeout))
        timed.append((verdict, static_ms + round((time.monotonic() - started) * 1000)))
    return timed


def check_static(llm_raw: str, gamma: Mapping[str, str]) -> Verdict | str:
    """Etapas parse y typecheck: el veredicto que bloquea, o el programa listo para ejecutar."""
    code = extract_code(llm_raw)
    if code is None:
        return blocked(
            "parse", "InvalidResponse", 'la respuesta no es un objeto JSON con "code" de tipo string'
        )
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        return blocked("parse", type(e).__name__, str(e))

    signature_error = check_signature(tree)
    if signature_error is not None:
        return blocked("typecheck", "SignatureMismatch", signature_error)

    program = data_preamble(gamma) + code
    mypy = run_mypy(program)
    if mypy is None:
        return {
            "outcome": "timeout",
            "stage": "typecheck",
            "result": None,
            "error": {"code": "TIMEOUT", "message": f"mypy superó {MYPY_TIMEOUT_SECONDS}s"},
        }
    returncode, output = mypy
    if returncode != 0:
        return blocked("typecheck", "mypy", output)
    return program
