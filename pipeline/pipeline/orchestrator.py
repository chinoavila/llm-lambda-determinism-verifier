"""Orquestador del pipeline (C-2).

Por caso: una llamada al LLM por grupo (Tratamiento, Baseline 1, Baseline 2),
las tres sobre el mismo modelo asignado. El `outcome` de cada `LLMCall` decide
el ruteo: si no es `ok`, el caso se registra como `llm_error` sin ejecutar
nada; si es `ok`, la salida cruda va al runner del grupo (engine/ por
subproceso o un baseline). Cada desenlace es un renglón JSON Lines según
contracts/output-record-schema.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

from pipeline.baselines.baseline2 import data_preamble
from pipeline.llm import LLMCall

# Binario del engine (contracts/README.md §2). Se elige con ENGINE_BIN.
DEFAULT_ENGINE_CMD = (os.environ.get("ENGINE_BIN", "engine"),)
GAMMA_TIMEOUT_SECONDS = 10.0
ENGINE_TIMEOUT_SECONDS = 10.0

SCHEMA_VERSION = "1.0"
AST_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "ast-schema.json"

Group = Literal["treatment", "baseline1", "baseline2"]
GROUPS: tuple[Group, ...] = ("treatment", "baseline1", "baseline2")

RecordOutcome = Literal["executed", "blocked", "runtime_error", "timeout", "llm_error"]
Stage = Literal["llm", "parse", "scope", "typecheck", "execution"]

# Etapa que corresponde a cada código de salida con veredicto (contracts/README.md §2).
ENGINE_EXIT_STAGE: dict[int, str] = {0: "execution", 1: "parse", 2: "scope", 3: "typecheck"}


class EngineError(Exception):
    """El engine no respetó el contrato CLI o salió con 64/70: abortar la corrida."""


class Verdict(TypedDict):
    """Desenlace de un runner: los campos del registro que no pone el orquestador."""

    outcome: RecordOutcome
    stage: Stage
    result: dict[str, Any] | None
    error: dict[str, str] | None


class Record(TypedDict):
    """Un renglón de contracts/output-record-schema.json."""

    schema_version: str
    run_id: str
    case_id: str
    group: Group
    model: str
    timestamp: str
    llm_raw: str | None
    outcome: RecordOutcome
    stage: Stage
    result: dict[str, Any] | None
    error: dict[str, str] | None
    duration_ms: int | None


# Recibe la salida cruda del LLM, los datos del caso (`env`) y Γ deducido por el engine.
Runner = Callable[[str, Mapping[str, object], Mapping[str, str]], Verdict]


class Completer(Protocol):
    """Lo que el orquestador usa de `ModelAssignment`: el modelo fijo del caso."""

    def complete(self, messages: Sequence[Mapping[str, str]]) -> LLMCall: ...


@dataclass(frozen=True)
class Case:
    case_id: str
    description: str
    env: Mapping[str, object]


def print_gamma(
    env: Mapping[str, object],
    engine_cmd: Sequence[str] = DEFAULT_ENGINE_CMD,
    timeout: float = GAMMA_TIMEOUT_SECONDS,
) -> dict[str, str]:
    """Γ deducido por el engine de los datos del caso: `{nombre: tipo}`.

    Es la lista de variables disponibles que va en el prompt del LLM. El
    orquestador nunca decide tipos: los deduce el engine (`--print-gamma`).
    """
    cmd = [*engine_cmd, "--env", json.dumps(env), "--print-gamma"]
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise EngineError(f"no se pudo ejecutar el engine: {e}") from e
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise EngineError(f"engine --print-gamma salió con {proc.returncode}: {stderr}")
    try:
        gamma = json.loads(proc.stdout)
    except ValueError as e:
        raise EngineError(f"stdout de --print-gamma no es JSON: {proc.stdout!r}") from e
    if not isinstance(gamma, dict) or not all(isinstance(t, str) for t in gamma.values()):
        raise EngineError(f"stdout de --print-gamma no es {{nombre: tipo}}: {proc.stdout!r}")
    return gamma


def run_engine(
    llm_raw: str,
    env: Mapping[str, object],
    engine_cmd: Sequence[str] = DEFAULT_ENGINE_CMD,
    timeout: float = ENGINE_TIMEOUT_SECONDS,
) -> Verdict:
    """Runner del grupo Tratamiento: la salida cruda del LLM va tal cual al stdin del engine."""
    cmd = [*engine_cmd, "--env", json.dumps(env)]
    try:
        proc = subprocess.run(
            cmd, input=llm_raw.encode("utf-8"), capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {
            "outcome": "timeout",
            "stage": "execution",
            "result": None,
            "error": {"code": "TIMEOUT", "message": f"el engine superó {timeout}s"},
        }
    except OSError as e:
        raise EngineError(f"no se pudo ejecutar el engine: {e}") from e
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode == 70:
        return {
            "outcome": "runtime_error",
            "stage": "execution",
            "result": None,
            "error": {"code": "ENGINE_INTERNAL", "message": stderr},
        }
    expected_stage = ENGINE_EXIT_STAGE.get(proc.returncode)
    if expected_stage is None:
        raise EngineError(f"engine salió con {proc.returncode}: {stderr}")
    try:
        verdict = json.loads(proc.stdout)
    except ValueError as e:
        raise EngineError(f"stdout del engine no es JSON: {proc.stdout!r}") from e
    if (
        not isinstance(verdict, dict)
        or set(verdict) != {"outcome", "stage", "result", "error"}
        or verdict["stage"] != expected_stage
    ):
        raise EngineError(
            f"veredicto fuera de contrato para exit {proc.returncode}: {proc.stdout!r}"
        )
    # El contrato pide copiar el veredicto sin transformarlo (contracts/README.md §3).
    return {
        "outcome": verdict["outcome"],
        "stage": verdict["stage"],
        "result": verdict["result"],
        "error": verdict["error"],
    }


def run_treatment(
    llm_raw: str, env: Mapping[str, object], gamma: Mapping[str, str]
) -> Verdict:
    """Runner del grupo `treatment`. No usa Γ: el engine lo deduce de `env`."""
    return run_engine(llm_raw, env)


def build_messages(
    group: Group, description: str, gamma: Mapping[str, str]
) -> list[dict[str, str]]:
    """Prompt de cada grupo. Todos piden JSON (response_format = json_object)."""
    variables = json.dumps(dict(gamma), ensure_ascii=False)
    if group == "treatment":
        schema = AST_SCHEMA_PATH.read_text(encoding="utf-8")
        system = (
            "Traducí la regla de negocio a un programa del DSL descrito por este JSON Schema. "
            "Respondé solo con un objeto JSON que lo cumpla.\n"
            f"Variables disponibles y sus tipos: {variables}\n"
            f"JSON Schema:\n{schema}"
        )
    elif group == "baseline1":
        system = (
            "Traducí la regla de negocio a una función Python `evaluate_rule(data)` que recibe "
            "un dict con los datos del caso y devuelve el resultado de la regla.\n"
            f"Claves de `data` y sus tipos: {variables}\n"
            'Respondé solo con un objeto JSON de la forma {"code": "<código Python>"}.'
        )
    else:
        system = (
            "Traducí la regla de negocio a una función Python `evaluate_rule(data: Data)` que "
            "recibe los datos del caso y devuelve el resultado de la regla. La función debe "
            "tener anotaciones de tipos completas y pasar mypy --strict.\n"
            "`Data` ya está definido antes de tu código, así; no lo redefinas:\n"
            f"{data_preamble(gamma)}"
            'Respondé solo con un objeto JSON de la forma {"code": "<código Python>"}.'
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": description}]


def route_call(
    call: LLMCall,
    runner: Runner,
    env: Mapping[str, object],
    *,
    gamma: Mapping[str, str],
    run_id: str,
    case_id: str,
    group: Group,
) -> Record:
    """Rutea según `call.outcome`: si no es `ok`, `llm_error` sin ejecutar; si es `ok`, al runner."""

    def record(
        verdict: Verdict, llm_raw: str | None, duration_ms: int | None
    ) -> Record:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "case_id": case_id,
            "group": group,
            "model": call.model,
            "timestamp": datetime.now(UTC).isoformat(),
            "llm_raw": llm_raw,
            **verdict,
            "duration_ms": duration_ms,
        }

    if call.outcome != "ok" or call.content is None:
        # Un 2xx sin `content` legible no tiene nada que rutear: también es falla del LLM.
        code = call.outcome if call.outcome != "ok" else "missing_content"
        last = call.attempts[-1] if call.attempts else None
        message = f"status {last.status}: {last.error}" if last else ""
        llm_error: Verdict = {
            "outcome": "llm_error",
            "stage": "llm",
            "result": None,
            "error": {"code": code, "message": message},
        }
        return record(llm_error, None, None)

    started = time.monotonic()
    verdict = runner(call.content, env, gamma)
    duration_ms = round((time.monotonic() - started) * 1000)
    return record(verdict, call.content, duration_ms)


def run_case(
    case: Case,
    assignment: Completer,
    runners: Mapping[Group, Runner],
    gamma: Mapping[str, str],
    *,
    run_id: str,
) -> list[Record]:
    """Triple llamada del caso: una por grupo, las tres con el mismo modelo asignado."""
    records: list[Record] = []
    for group in GROUPS:
        call = assignment.complete(build_messages(group, case.description, gamma))
        records.append(
            route_call(
                call,
                runners[group],
                case.env,
                gamma=gamma,
                run_id=run_id,
                case_id=case.case_id,
                group=group,
            )
        )
    return records


def append_jsonl(path: Path, records: Iterable[Record]) -> None:
    """Agrega un renglón JSON por registro; no reescribe lo ya registrado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
