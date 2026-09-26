"""Tests del sandbox real: necesitan el servicio `sandbox` corriendo (lo levanta
`docker compose run pipeline` por depends_on). Fuera de Compose se saltean."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.baselines.sandbox import SandboxError, run_in_sandbox

pytestmark = pytest.mark.skipif(
    "SANDBOX_IO" not in os.environ, reason="sandbox no disponible (correr en Docker Compose)"
)


def run(body: str, env: dict[str, object] | None = None, timeout: float = 5.0) -> dict[str, object]:
    code = "def evaluate_rule(data):\n" + "".join(f"    {line}\n" for line in body.splitlines())
    return run_in_sandbox(code, env or {}, timeout=timeout)


# --- Resultados y excepciones ----------------------------------------------


def test_fixture_rule_executes() -> None:
    code = "def evaluate_rule(data):\n    return data['credit_score'] > 700 and not data['has_defaults']\n"
    result = run_in_sandbox(code, {"credit_score": 750, "has_defaults": False})
    assert result == {"status": "ok", "type": "Bool", "value": True}


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("True", {"type": "Bool", "value": True}),
        ("42", {"type": "Int", "value": 42}),
        ("'Gold'", {"type": "String", "value": "Gold"}),
        ("[1, 2]", {"type": "Other", "value": "[1, 2]"}),
    ],
)
def test_result_types(expr: str, expected: dict[str, object]) -> None:
    assert run(f"return {expr}") == {"status": "ok", **expected}


def test_exception_is_reported_by_name() -> None:
    result = run("return data['risk_level']", {"credit_score": 1})
    assert result["status"] == "exception" and result["name"] == "KeyError"


def test_syntax_error() -> None:
    result = run_in_sandbox("def evaluate_rule(data)\n    return 1\n", {})
    assert result["status"] == "exception" and result["name"] == "SyntaxError"


def test_missing_function() -> None:
    result = run_in_sandbox("x = 1\n", {})
    assert result["status"] == "exception" and result["name"] == "NameError"


def test_prints_do_not_corrupt_result() -> None:
    assert run("print('{\"status\": \"ok\"}')\nreturn 1") == {"status": "ok", "type": "Int", "value": 1}


def test_sys_exit_is_an_exception() -> None:
    result = run("import sys\nsys.exit(3)")
    assert result["status"] == "exception" and result["name"] == "SystemExit"


# --- Aislamiento -----------------------------------------------------------


def test_no_network() -> None:
    result = run("import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=2)\nreturn True")
    assert result["status"] == "exception" and result["name"] in {"OSError", "TimeoutError"}


def test_no_dns() -> None:
    result = run("import socket\nsocket.getaddrinfo('example.com', 443)\nreturn True")
    assert result["status"] == "exception" and result["name"] == "gaierror"


def test_no_credentials_in_environment() -> None:
    result = run("import os\nreturn sorted(os.environ)")
    assert result["status"] == "ok"
    assert result["value"] in ("[]", "['LC_CTYPE']")  # LC_CTYPE lo agrega Python (PEP 538)


def test_not_root() -> None:
    result = run("import os\nreturn os.getuid()")
    assert result["status"] == "ok" and result["value"] != 0


def test_repo_not_visible() -> None:
    assert run("import os\nreturn os.path.exists('/workspace')") == {"status": "ok", "type": "Bool", "value": False}


def test_queue_not_readable() -> None:
    result = run("import os\nreturn os.listdir('/io')")
    assert result["status"] == "exception" and result["name"] == "PermissionError"


@pytest.mark.parametrize("path", ["/tmp/x", "/work/x", "/x"])
def test_filesystem_not_writable(path: str) -> None:
    result = run(f"open({path!r}, 'w').write('x')\nreturn True")
    assert result["status"] == "exception"


# --- Límites ---------------------------------------------------------------


def test_busy_loop_times_out() -> None:
    assert run("while True:\n    pass", timeout=1)["status"] == "timeout"


def test_sleep_times_out() -> None:
    assert run("import time\ntime.sleep(60)", timeout=1)["status"] == "timeout"


def test_memory_limit() -> None:
    result = run("x = bytearray(1 << 30)\nreturn len(x)")
    assert result["status"] == "exception" and result["name"] == "MemoryError"


def test_leftover_processes_are_killed() -> None:
    spawn = run(
        "import os, time\n"
        "if os.fork() == 0:\n"
        "    os.setsid()\n"
        "    time.sleep(60)\n"
        "    os._exit(0)\n"
        "return True"
    )
    assert spawn["status"] == "ok"
    count = run(
        "import os\n"
        "me = os.getuid()\n"
        "pids = [p for p in os.listdir('/proc') if p.isdigit() and int(p) != os.getpid()]\n"
        "return sum(1 for p in pids if os.stat('/proc/' + p).st_uid == me)"
    )
    assert count == {"status": "ok", "type": "Int", "value": 0}


def test_missing_worker_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipeline.baselines.sandbox.QUEUE_MARGIN_SECONDS", 0.2)
    with pytest.raises(SandboxError, match="no respondió"):
        run_in_sandbox("", {}, timeout=0, io_dir=tmp_path)
    assert list((tmp_path / "jobs").iterdir()) == []
