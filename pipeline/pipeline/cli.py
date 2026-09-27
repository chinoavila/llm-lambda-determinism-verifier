"""Comandos: `python -m pipeline run` (punta a punta, specs/orquestador.md),
`python -m pipeline check-case` (verificación del corpus, docs/corpus.md) y
`python -m pipeline serve` (UI y su API, specs/ui.md).

`run` lee los casos, verifica todos antes de la primera llamada al LLM (formato y Γ común),
arma el balanceador y corre cada caso con los tres grupos. Los registros de cada caso se
agregan al JSONL apenas termina, así una corrida cortada conserva lo hecho.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pipeline.baselines.baseline1 import run_baseline_1
from pipeline.baselines.baseline2 import StaticCheckError, run_baseline_2_scenarios
from pipeline.baselines.sandbox import SandboxError
from pipeline.corpus import check_case, write_expected
from pipeline.llm import (
    ConfigError,
    MissingCredentials,
    NoModelAvailable,
    build_balancer,
    load_config,
)
from pipeline.orchestrator import (
    DEFAULT_ENGINE_CMD,
    Case,
    CaseError,
    Completer,
    EngineError,
    Group,
    Runner,
    append_jsonl,
    case_gamma,
    per_scenario,
    read_case,
    run_case,
    run_treatment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = REPO_ROOT / "contracts" / "fixtures"
DEFAULT_OUT_DIR = REPO_ROOT / "out"

RUNNERS: Mapping[Group, Runner] = {
    "treatment": per_scenario(run_treatment),
    "baseline1": per_scenario(run_baseline_1),
    "baseline2": run_baseline_2_scenarios,
}


class Acquirer(Protocol):
    """Lo que el comando usa del balanceador: un modelo fijo por caso."""

    def acquire(self) -> AbstractContextManager[Completer]: ...


def new_run_id(now: datetime | None = None) -> str:
    """Fecha y hora UTC más un sufijo aleatorio corto: ordena bien y no choca."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"


def case_paths(paths: Sequence[Path]) -> list[Path]:
    """Archivos de casos: un directorio aporta sus `*.json` en orden alfabético."""
    found: list[Path] = []
    for p in paths:
        if p.is_dir():
            found.extend(sorted(p.glob("*.json")))
        elif p.is_file():
            found.append(p)
        else:
            raise CaseError(f"no existe: {p}")
    if not found:
        raise CaseError("no hay casos para correr")
    return found


def prepare(
    paths: Sequence[Path], engine_cmd: Sequence[str] = DEFAULT_ENGINE_CMD
) -> list[tuple[Case, dict[str, str]]]:
    """Lee y verifica todos los casos antes de gastar una sola llamada al LLM."""
    cases = [read_case(p) for p in case_paths(paths)]
    ids = [c.case_id for c in cases]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        raise CaseError(f"case_id repetido: {duplicated}")
    return [(c, case_gamma(c, engine_cmd)) for c in cases]


def run(
    prepared: Sequence[tuple[Case, dict[str, str]]],
    balancer: Acquirer,
    out: Path,
    *,
    run_id: str,
    repetitions: int,
    runners: Mapping[Group, Runner] = RUNNERS,
    log: Callable[[str], None] = lambda msg: print(msg, file=sys.stderr, flush=True),
) -> int:
    """Corre los casos en orden y devuelve cuántos registros escribió."""
    written = 0
    for i, (case, gamma) in enumerate(prepared, start=1):
        with balancer.acquire() as assignment:
            records = run_case(case, assignment, runners, gamma, run_id=run_id, repetitions=repetitions)
        append_jsonl(out, records)
        written += len(records)
        outcomes = Counter(r["outcome"] for r in records)
        summary = ", ".join(f"{o}={n}" for o, n in sorted(outcomes.items()))
        log(f"[{i}/{len(prepared)}] {case.case_id}: {len(records)} registros ({summary})")
    return written


def check_cases(
    paths: Sequence[Path],
    *,
    write: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    """`check-case`: reporta cada regla y sale con 1 si alguna tiene errores."""
    try:
        files = case_paths(paths)
    except CaseError as e:
        out(f"error: {e}")
        return 1
    failed = 0
    for path in files:
        report, data = check_case(path)
        status = "OK" if report.ok else "ERROR"
        out(f"{status} {report.case_id} ({path.name})")
        for level, msg in report.issues:
            out(f"  {level}: {msg}")
        if not report.ok:
            failed += 1
        elif write and data is not None:
            filled = write_expected(path, data, report)
            if filled:
                out(f"  escrito: {filled} expected calculados por el engine")
    out(f"{len(files) - failed}/{len(files)} reglas sin errores")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="corre los casos con los tres grupos y escribe el JSONL")
    p_run.add_argument(
        "cases", nargs="*", type=Path, default=[DEFAULT_CASES],
        help=f"archivos o directorios de casos (por defecto {DEFAULT_CASES.relative_to(REPO_ROOT)})",
    )  # fmt: skip
    p_run.add_argument("--repetitions", type=int, default=1, help="rondas de triple llamada por caso")
    p_run.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p_run.add_argument("--run-id", default=None, help="por defecto, fecha y hora UTC más un sufijo")
    p_check = sub.add_parser("check-case", help="verifica reglas del corpus (docs/corpus.md)")
    p_check.add_argument("cases", nargs="+", type=Path, help="archivos o directorios de reglas")
    p_check.add_argument(
        "--write", action="store_true",
        help="completa los expected que faltan con lo que calcula el engine (nunca pisa uno existente)",
    )  # fmt: skip
    p_serve = sub.add_parser("serve", help="sirve la UI y su API (docs/ui.md)")
    p_serve.add_argument(
        "--host", default="127.0.0.1",
        help="interfaz donde escuchar; en Docker, 0.0.0.0 y compose publica solo en localhost",
    )  # fmt: skip
    p_serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == "check-case":
        return check_cases(args.cases, write=args.write)
    if args.command == "serve":
        from pipeline.server import serve  # acá: server importa jobs, que importa este módulo

        return serve(args.host, args.port)

    if args.repetitions < 1:
        parser.error("--repetitions debe ser >= 1")
    run_id = args.run_id or new_run_id()
    out = args.out_dir / f"{run_id}.jsonl"

    try:
        prepared = prepare(args.cases)
        config = load_config()
    except MissingCredentials as e:
        print(
            f"sin credenciales del LLM ({e}): se omite la corrida. "
            "Completá .env (ver .env.example) y volvé a correr.",
            file=sys.stderr,
        )
        return 0
    except (CaseError, EngineError, ConfigError) as e:
        print(f"error antes de empezar: {e}", file=sys.stderr)
        return 1

    print(f"run_id={run_id}: {len(prepared)} casos, {args.repetitions} repeticiones -> {out}", file=sys.stderr)
    try:
        written = run(prepared, build_balancer(config), out, run_id=run_id, repetitions=args.repetitions)
    except (EngineError, SandboxError, StaticCheckError, NoModelAvailable) as e:
        # Fallas del sistema, no del modelo: se corta la corrida. Lo ya escrito queda.
        print(f"corrida abortada: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"listo: {written} registros en {out}", file=sys.stderr)
    return 0
