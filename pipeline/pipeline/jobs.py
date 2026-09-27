"""Corridas del pipeline lanzadas desde la UI, y lectura de sus registros.

Ver specs/ui.md. Una corrida es exactamente `python -m pipeline run` como
subproceso, con su salida en `out/<run_id>.log`: desde la UI y desde la terminal
se obtiene lo mismo. Consume cuota del LLM, así que `start` exige que el cliente
confirme el número de llamadas que va a hacer. Hay a lo sumo una corrida a la vez.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pipeline.cli import new_run_id
from pipeline.orchestrator import GROUPS
from pipeline.store import RuleStore, StoreError

RUN_ID = re.compile(r"[0-9A-Za-z_\-]{1,80}")
Status = Literal["running", "finished", "failed", "cancelled"]
Command = Callable[[Sequence[Path], int, str, Path], list[str]]
PIPELINE_DIR = Path(__file__).resolve().parents[1]


def pipeline_command(cases: Sequence[Path], repetitions: int, run_id: str, out: Path) -> list[str]:
    return [
        sys.executable, "-m", "pipeline", "run", *map(str, cases),
        "--repetitions", str(repetitions), "--run-id", run_id, "--out-dir", str(out),
    ]  # fmt: skip


@dataclass
class Job:
    run_id: str
    source: str
    cases: list[str]
    repetitions: int
    calls: int
    started_at: str
    process: subprocess.Popen[bytes] = field(repr=False)
    status: Status = "running"
    returncode: int | None = None
    cancelled: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "cases": self.cases,
            "repetitions": self.repetitions,
            "calls": self.calls,
            "started_at": self.started_at,
            "status": self.status,
            "returncode": self.returncode,
        }


class RunManager:
    def __init__(
        self,
        out: Path,
        store: RuleStore,
        fixtures: Path,
        *,
        command: Command = pipeline_command,
        cwd: Path = PIPELINE_DIR,
    ) -> None:
        self.out = out
        self.store = store
        self.fixtures = fixtures
        self.command = command
        self.cwd = cwd
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    # --- Qué se corre -----------------------------------------------------------

    def resolve(self, selection: Mapping[str, Any]) -> tuple[str, list[Path], int]:
        """`{"source": "corpus" | "fixtures", "case_ids": [...]?, "repetitions": n}`."""
        source = selection.get("source")
        repetitions = selection.get("repetitions", 1)
        if not isinstance(repetitions, int) or isinstance(repetitions, bool) or not 1 <= repetitions <= 20:
            raise StoreError(400, "repetitions debe ser un entero entre 1 y 20")
        if source == "corpus":
            paths = self.store.paths()
            wanted = selection.get("case_ids")
            if wanted:
                if not isinstance(wanted, list) or not all(isinstance(c, str) for c in wanted):
                    raise StoreError(400, "case_ids debe ser una lista de ids")
                missing = [c for c in wanted if c not in paths]
                if missing:
                    raise StoreError(400, f"no existen en el corpus: {missing}")
                files = [paths[c] for c in wanted]
            else:
                files = list(paths.values())
        elif source == "fixtures":
            files = sorted(self.fixtures.glob("*.json"))
        else:
            raise StoreError(400, 'source debe ser "corpus" o "fixtures"')
        if not files:
            raise StoreError(400, "no hay casos para correr")
        return source, files, repetitions

    def estimate(self, selection: Mapping[str, Any]) -> dict[str, Any]:
        _, files, repetitions = self.resolve(selection)
        return {"cases": len(files), "repetitions": repetitions, "calls": len(files) * len(GROUPS) * repetitions}

    # --- Ciclo de vida -------------------------------------------------------------

    def start(self, selection: Mapping[str, Any], confirm_calls: object) -> Job:
        source, files, repetitions = self.resolve(selection)
        calls = len(files) * len(GROUPS) * repetitions
        if confirm_calls != calls:
            raise StoreError(409, f"la corrida hace {calls} llamadas al LLM: confirmá ese número para lanzarla")
        with self.lock:
            if self.active() is not None:
                raise StoreError(409, "ya hay una corrida en curso")
            run_id = new_run_id()
            self.out.mkdir(parents=True, exist_ok=True)
            log = (self.out / f"{run_id}.log").open("wb")
            try:
                process = subprocess.Popen(
                    self.command(files, repetitions, run_id, self.out),
                    cwd=self.cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                )  # fmt: skip
            finally:
                log.close()
            job = Job(
                run_id=run_id,
                source=source,
                cases=[p.name for p in files],
                repetitions=repetitions,
                calls=calls,
                started_at=datetime.now(UTC).isoformat(timespec="seconds"),
                process=process,
            )
            self.jobs[run_id] = job
        threading.Thread(target=self._wait, args=(job,), daemon=True).start()
        return job

    def _wait(self, job: Job) -> None:
        code = job.process.wait()
        with self.lock:
            job.returncode = code
            job.status = "cancelled" if job.cancelled else "finished" if code == 0 else "failed"

    def active(self) -> Job | None:
        return next((j for j in self.jobs.values() if j.status == "running"), None)

    def cancel(self, run_id: str) -> Job:
        job = self.jobs.get(self.check_id(run_id))
        if job is None or job.status != "running":
            raise StoreError(409, f"la corrida {run_id} no está en curso")
        job.cancelled = True
        job.process.terminate()
        return job

    # --- Lectura ----------------------------------------------------------------------

    @staticmethod
    def check_id(run_id: str) -> str:
        if not RUN_ID.fullmatch(run_id):
            raise StoreError(400, "run_id inválido")
        return run_id

    def log(self, run_id: str, offset: int = 0) -> dict[str, Any]:
        path = self.out / f"{self.check_id(run_id)}.log"
        if not path.exists():
            raise StoreError(404, f"no hay log de la corrida {run_id}")
        with path.open("rb") as f:
            f.seek(max(0, offset))
            data = f.read()
        job = self.jobs.get(run_id)
        return {
            "text": data.decode("utf-8", errors="replace"),
            "offset": max(0, offset) + len(data),
            "status": job.status if job else None,
        }

    def list_runs(self) -> list[dict[str, Any]]:
        """Corridas con registros o log en `out/`, más nuevas primero."""
        ids = {p.stem for p in self.out.glob("*.jsonl")} | {p.stem for p in self.out.glob("*.log")}
        runs = []
        for run_id in ids:
            records = self.out / f"{run_id}.jsonl"
            log = self.out / f"{run_id}.log"
            newest = max((p.stat().st_mtime for p in (records, log) if p.exists()), default=0.0)
            job = self.jobs.get(run_id)
            runs.append({
                "run_id": run_id,
                "records": sum(1 for _ in records.open("rb")) if records.exists() else 0,
                "has_log": log.exists(),
                "modified": datetime.fromtimestamp(newest, UTC).isoformat(timespec="seconds"),
                "job": job.summary() if job else None,
            })  # fmt: skip
        return sorted(runs, key=lambda r: r["run_id"], reverse=True)

    def records(self, run_id: str, filters: Mapping[str, str]) -> list[dict[str, Any]]:
        """Renglones del JSONL, filtrados por igualdad de campo, cada uno con el `expected`
        de su escenario si la regla está en el corpus. Sin agregados (mission.md §2)."""
        path = self.out / f"{self.check_id(run_id)}.jsonl"
        if not path.exists():
            raise StoreError(404, f"la corrida {run_id} no tiene registros")
        expected = self._expected_index()
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if any(str(record.get(k)) != v for k, v in filters.items()):
                continue
            record["expected"] = expected.get((str(record.get("case_id")), str(record.get("scenario_id"))))
            rows.append(record)
        return rows

    def _expected_index(self) -> dict[tuple[str, str], Any]:
        index: dict[tuple[str, str], Any] = {}
        for rule in self.store.list():
            for s in rule.get("scenarios", []):
                if isinstance(s, dict) and "expected" in s:
                    index[(str(rule["case_id"]), str(s.get("scenario_id")))] = s["expected"]
        return index
