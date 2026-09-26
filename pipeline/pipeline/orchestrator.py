"""Orquestador del pipeline (C-2).

Por caso y repetición: una llamada al LLM por grupo (Tratamiento, Baseline 1,
Baseline 2), todas sobre el mismo modelo asignado. El `outcome` de cada
`LLMCall` decide el ruteo: si no es `ok`, la generación se registra como
`llm_error` sin ejecutar nada; si es `ok`, la misma salida cruda va al runner
del grupo contra el `env` de cada escenario del caso (engine/ por subproceso o
un baseline). Un renglón JSON Lines por escenario, según
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

SCHEMA_VERSION = "2.0"
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
    repetition: int
    scenario_id: str
    model: str
    timestamp: str
    llm_raw: str | None
    outcome: RecordOutcome
    stage: Stage
    result: dict[str, Any] | None
    error: dict[str, str] | None
    duration_ms: int | None


# Ejecuta la salida cruda del LLM con los datos de UN escenario (`env`) y Γ del caso.
ScenarioRunner = Callable[[str, Mapping[str, object], Mapping[str, str]], Verdict]

# Veredicto de un escenario y su `duration_ms` (contracts/README.md §3).
Timed = tuple[Verdict, int]

# Ejecuta la MISMA salida del LLM contra el `env` de cada escenario, en orden.
Runner = Callable[[str, Sequence[Mapping[str, object]], Mapping[str, str]], list[Timed]]


class CaseError(Exception):
    """El caso no respeta contracts/case-schema.json o §5: error del corpus, abortar la corrida."""


class Completer(Protocol):
    """Lo que el orquestador usa de `ModelAssignment`: el modelo fijo del caso."""

    def complete(self, messages: Sequence[Mapping[str, str]]) -> LLMCall: ...


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    env: Mapping[str, object]


@dataclass(frozen=True)
class Case:
    case_id: str
    description: str
    scenarios: tuple[Scenario, ...]


def load_case(data: Mapping[str, Any]) -> Case:
    """Caso de entrada según contracts/case-schema.json; ignora los campos del corpus."""
    case_id, description, scenarios = (
        data.get("case_id"),
        data.get("description"),
        data.get("scenarios"),
    )
    if not isinstance(case_id, str) or not case_id:
        raise CaseError("case_id debe ser un texto no vacío")
    if not isinstance(description, str) or not description:
        raise CaseError(f"{case_id}: description debe ser un texto no vacío")
    if not isinstance(scenarios, list) or not scenarios:
        raise CaseError(f"{case_id}: scenarios debe ser una lista no vacía")
    parsed: list[Scenario] = []
    for s in scenarios:
        sid = s.get("scenario_id") if isinstance(s, dict) else None
        env = s.get("env") if isinstance(s, dict) else None
        if not isinstance(sid, str) or not sid or not isinstance(env, dict):
            raise CaseError(f"{case_id}: cada escenario necesita scenario_id y env: {s!r}")
        parsed.append(Scenario(sid, env))
    ids = [s.scenario_id for s in parsed]
    if len(set(ids)) != len(ids):
        raise CaseError(f"{case_id}: scenario_id repetido en {ids}")
    return Case(case_id, description, tuple(parsed))


def case_gamma(case: Case, engine_cmd: Sequence[str] = DEFAULT_ENGINE_CMD) -> dict[str, str]:
    """Γ común del caso: el engine lo deduce de cada escenario y tiene que coincidir."""
    gammas = [print_gamma(s.env, engine_cmd) for s in case.scenarios]
    for s, g in zip(case.scenarios, gammas):
        if g != gammas[0]:
            raise CaseError(
                f"{case.case_id}: Γ de {s.scenario_id} ({g}) distinto de "
                f"{case.scenarios[0].scenario_id} ({gammas[0]})"
            )
    return gammas[0]


def elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def per_scenario(runner: ScenarioRunner) -> Runner:
    """Runner que ejecuta cada escenario por separado y cronometra cada uno."""

    def run(
        llm_raw: str, envs: Sequence[Mapping[str, object]], gamma: Mapping[str, str]
    ) -> list[Timed]:
        timed: list[Timed] = []
        for env in envs:
            started = time.monotonic()
            verdict = runner(llm_raw, env, gamma)
            timed.append((verdict, elapsed_ms(started)))
        return timed

    return run


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
    scenarios: Sequence[Scenario],
    *,
    gamma: Mapping[str, str],
    run_id: str,
    case_id: str,
    group: Group,
    repetition: int,
) -> list[Record]:
    """Rutea según `call.outcome`: si no es `ok`, `llm_error` sin ejecutar; si es `ok`, al runner.

    Siempre devuelve un registro por escenario, en el orden del caso.
    """

    def record(
        scenario: Scenario, verdict: Verdict, llm_raw: str | None, duration_ms: int | None
    ) -> Record:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "case_id": case_id,
            "group": group,
            "repetition": repetition,
            "scenario_id": scenario.scenario_id,
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
        return [record(s, llm_error, None, None) for s in scenarios]

    timed = runner(call.content, [s.env for s in scenarios], gamma)
    if len(timed) != len(scenarios):
        raise RuntimeError(
            f"el runner de {group} devolvió {len(timed)} veredictos para {len(scenarios)} escenarios"
        )
    return [record(s, verdict, call.content, ms) for s, (verdict, ms) in zip(scenarios, timed)]


def run_case(
    case: Case,
    assignment: Completer,
    runners: Mapping[Group, Runner],
    gamma: Mapping[str, str],
    *,
    run_id: str,
    repetitions: int = 1,
) -> list[Record]:
    """`repetitions` rondas de triple llamada (una por grupo), todas con el mismo modelo asignado.

    Cada llamada es una generación: su salida se ejecuta contra todos los escenarios del caso.
    """
    if repetitions < 1:
        raise ValueError("repetitions debe ser >= 1")
    records: list[Record] = []
    for repetition in range(1, repetitions + 1):
        for group in GROUPS:
            call = assignment.complete(build_messages(group, case.description, gamma))
            records.extend(
                route_call(
                    call,
                    runners[group],
                    case.scenarios,
                    gamma=gamma,
                    run_id=run_id,
                    case_id=case.case_id,
                    group=group,
                    repetition=repetition,
                )
            )
    return records


def append_jsonl(path: Path, records: Iterable[Record]) -> None:
    """Agrega un renglón JSON por registro; no reescribe lo ya registrado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
