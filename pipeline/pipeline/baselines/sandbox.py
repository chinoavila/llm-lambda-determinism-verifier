"""Cliente del sandbox, del lado de `pipeline`. Ver docs/sandbox.md.

El código del LLM nunca se ejecuta en este contenedor: se deja como job en la
cola compartida (`$SANDBOX_IO/jobs`) y el contenedor `sandbox`, sin red,
responde en `$SANDBOX_IO/results`.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipeline.orchestrator import Verdict

DEFAULT_TIMEOUT_SECONDS = 5.0
# Margen sobre el timeout del job: arranque del hijo y otros jobs en la cola.
QUEUE_MARGIN_SECONDS = 30.0
POLL_SECONDS = 0.02
STATUSES = frozenset({"ok", "exception", "timeout", "crash"})


class SandboxError(Exception):
    """El sandbox no respondió o respondió fuera de protocolo: abortar la corrida."""


def sandbox_io() -> Path:
    return Path(os.environ.get("SANDBOX_IO", "/io"))


def run_in_sandbox(
    code: str,
    env: Mapping[str, object],
    *,
    function: str = "evaluate_rule",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    io_dir: Path | None = None,
) -> dict[str, Any]:
    """Ejecuta `function(env)` del `code` en el sandbox y devuelve el resultado crudo.

    `status` es `ok` (con `type` y `value`), `exception` (con `name` y
    `message`), `timeout` o `crash`. El mapeo al registro lo hace cada baseline.
    """
    io = io_dir or sandbox_io()
    jobs, results = io / "jobs", io / "results"
    jobs.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    job_path, result_path = jobs / f"{job_id}.json", results / f"{job_id}.json"

    tmp = jobs / f".{job_id}.tmp"
    tmp.write_text(
        json.dumps({"code": code, "env": dict(env), "function": function, "timeout": timeout}),
        encoding="utf-8",
    )
    os.replace(tmp, job_path)  # el worker nunca ve un job a medio escribir

    deadline = time.monotonic() + timeout + QUEUE_MARGIN_SECONDS
    while not result_path.exists():
        if time.monotonic() > deadline:
            job_path.unlink(missing_ok=True)
            raise SandboxError(f"el sandbox no respondió el job {job_id} (¿está corriendo?)")
        time.sleep(POLL_SECONDS)
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SandboxError(f"resultado del job {job_id} no es JSON") from e
    finally:
        result_path.unlink(missing_ok=True)
    if not isinstance(result, dict) or result.get("status") not in STATUSES:
        raise SandboxError(f"resultado del job {job_id} fuera de protocolo: {result!r}")
    return result


def to_verdict(result: Mapping[str, Any]) -> Verdict:
    """Mapea el resultado del sandbox a la etapa `execution` del registro (ver specs/sandbox.md)."""
    status = result["status"]
    if status == "ok":
        return {
            "outcome": "executed",
            "stage": "execution",
            "result": {"type": result["type"], "value": result["value"]},
            "error": None,
        }
    if status == "exception":
        error = {"code": str(result["name"]), "message": str(result["message"])}
        return {"outcome": "runtime_error", "stage": "execution", "result": None, "error": error}
    if status == "timeout":
        error = {"code": "TIMEOUT", "message": f"superó {result.get('timeout_seconds')}s"}
        return {"outcome": "timeout", "stage": "execution", "result": None, "error": error}
    error = {"code": "SANDBOX_CRASH", "message": str(result.get("message", ""))}
    return {"outcome": "runtime_error", "stage": "execution", "result": None, "error": error}
