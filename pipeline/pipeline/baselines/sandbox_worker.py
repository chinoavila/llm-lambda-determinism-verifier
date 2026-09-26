"""Worker del sandbox de los baselines (C-3). Corre SOLO en el contenedor `sandbox`.

Ver docs/sandbox.md. Solo stdlib: la imagen `sandbox` copia este archivo y nada más.

- Modo worker (por defecto): revisa la cola `$SANDBOX_IO/jobs`, ejecuta cada job
  en un proceso hijo nuevo y deja el resultado en `$SANDBOX_IO/results`.
- Modo hijo (`--child`): lo lanza el worker, ya como el usuario `sandbox`, sin
  entorno y con límites de recursos. Ejecuta el código del LLM y escribe una
  línea JSON con el resultado.

El contenedor no tiene red (`network_mode: none`) ni volúmenes del repo; el
hijo, además, no puede escribir en ningún lado ni leer la cola.
"""

from __future__ import annotations

import json
import os
import pwd
import resource
import signal
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

SANDBOX_USER = "sandbox"
POLL_SECONDS = 0.02
MAX_OUTPUT_BYTES = 1 << 20  # lo que el hijo puede escribir como resultado
MEMORY_BYTES = 256 << 20
MAX_PROCESSES = 16
MAX_OPEN_FILES = 64
DEFAULT_TIMEOUT_SECONDS = 5.0


# --- Modo hijo --------------------------------------------------------------


def decimal_text(value: Decimal) -> str:
    """Texto canónico de contracts/README.md §3: posicional, sin ceros finales, "0" sin signo."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def encode(value: object) -> dict[str, Any]:
    """`result` del registro; `bool` antes que `int` porque True es un int.

    `float` va a `Other`: no es exacto, así que no se registra como `Decimal`.
    """
    if isinstance(value, bool):
        return {"type": "Bool", "value": value}
    if isinstance(value, int):
        return {"type": "Int", "value": value}
    if isinstance(value, Decimal) and value.is_finite():
        return {"type": "Decimal", "value": decimal_text(value)}
    if isinstance(value, str):
        return {"type": "String", "value": value}
    return {"type": "Other", "value": repr(value)}


def child() -> None:
    # Los números no enteros de `env` llegan como decimal.Decimal exactos, igual
    # que el Decimal del DSL (contracts/README.md §3).
    job = json.load(sys.stdin, parse_float=Decimal)
    # El resultado sale por una copia privada de stdout; lo que imprima el
    # código del LLM va a /dev/null y no puede mezclarse con él.
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    try:
        namespace: dict[str, Any] = {"__name__": "__sandbox__"}
        exec(compile(job["code"], "<llm>", "exec"), namespace)
        fn = namespace.get(job["function"])
        if not callable(fn):
            raise NameError(f"name '{job['function']}' is not defined")
        result: dict[str, Any] = {"status": "ok", **encode(fn(job["env"]))}
    except BaseException as e:  # SystemExit y KeyboardInterrupt también son desenlaces
        try:
            message = str(e)
        except BaseException:
            message = ""
        result = {"status": "exception", "name": type(e).__name__, "message": message}
    out.write(json.dumps(result) + "\n")
    out.flush()


# --- Modo worker ------------------------------------------------------------


def limit_resources(timeout: float) -> None:
    """preexec_fn del hijo: solo baja límites, nunca los sube."""
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCESSES, MAX_PROCESSES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (MAX_OPEN_FILES, MAX_OPEN_FILES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    cpu = int(timeout) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))


def kill_sandbox_processes(uid: int, gid: int) -> None:
    """Mata todo lo que quede corriendo como `sandbox` (procesos que el código dejó vivos)."""
    pid = os.fork()
    if pid == 0:  # pragma: no cover - proceso auxiliar efímero
        try:
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
            os.kill(-1, signal.SIGKILL)  # en Linux, -1 excluye al que llama
        finally:
            os._exit(0)
    os.waitpid(pid, 0)


def run_job(job: dict[str, Any], work: Path, job_id: str) -> dict[str, Any]:
    user = pwd.getpwnam(SANDBOX_USER)
    timeout = float(job.get("timeout", DEFAULT_TIMEOUT_SECONDS))
    stdin_path, stdout_path = work / f"{job_id}.in", work / f"{job_id}.out"
    stdin_path.write_text(
        json.dumps({"code": job["code"], "env": job["env"], "function": job["function"]}),
        encoding="utf-8",
    )
    try:
        with stdin_path.open("rb") as fin, stdout_path.open("wb") as fout:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-S", os.path.abspath(__file__), "--child"],
                stdin=fin,
                stdout=fout,
                stderr=subprocess.DEVNULL,
                env={},
                cwd="/",
                user=user.pw_uid,
                group=user.pw_gid,
                extra_groups=[],
                start_new_session=True,
                preexec_fn=lambda: limit_resources(timeout),
            )
            try:
                returncode = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                return {"status": "timeout", "timeout_seconds": timeout}
            finally:
                kill_sandbox_processes(user.pw_uid, user.pw_gid)
        lines = stdout_path.read_bytes()[:MAX_OUTPUT_BYTES].decode("utf-8", "replace").splitlines()
        try:
            result = json.loads(lines[-1])
        except (IndexError, ValueError):
            return {"status": "crash", "message": f"el proceso terminó con {returncode} sin resultado"}
        if not isinstance(result, dict) or result.get("status") not in ("ok", "exception"):
            return {"status": "crash", "message": "resultado con forma inesperada"}
        return result
    finally:
        stdin_path.unlink(missing_ok=True)
        stdout_path.unlink(missing_ok=True)


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def worker() -> None:
    io = Path(os.environ.get("SANDBOX_IO", "/io"))
    work = Path(os.environ.get("SANDBOX_WORK", "/work"))
    jobs, results = io / "jobs", io / "results"
    jobs.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    os.chmod(io, 0o700)  # el hijo no puede ver la cola
    print(f"sandbox worker listo en {io}", flush=True)
    while True:
        pending = sorted(jobs.glob("*.json"))
        if not pending:
            time.sleep(POLL_SECONDS)
            continue
        for path in pending:
            job_id = path.stem
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                result = run_job(job, work, job_id)
            except Exception as e:  # un job roto no debe tumbar al worker
                result = {"status": "crash", "message": f"{type(e).__name__}: {e}"}
            path.unlink(missing_ok=True)
            write_atomic(results / f"{job_id}.json", result)


if __name__ == "__main__":
    child() if sys.argv[1:] == ["--child"] else worker()
