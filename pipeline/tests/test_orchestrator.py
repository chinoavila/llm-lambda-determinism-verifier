from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipeline.orchestrator import EngineError, print_gamma

FIXTURE = Path(__file__).parents[2] / "contracts" / "fixtures" / "rule-001.json"


def fake_engine(tmp_path: Path, stdout: str, exit_code: int = 0) -> list[str]:
    """Engine falso: guarda sus argumentos en args.json e imprime `stdout`."""
    script = tmp_path / "engine.py"
    script.write_text(
        "import json, sys\n"
        f"open({str(tmp_path / 'args.json')!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, str(script)]


def test_print_gamma_sends_env_and_parses_gamma(tmp_path: Path) -> None:
    env = json.loads(FIXTURE.read_text(encoding="utf-8"))["env"]
    gamma_line = '{"credit_score":"Int","customer_tier":"String","has_defaults":"Bool","monthly_income":"Int"}\n'
    gamma = print_gamma(env, fake_engine(tmp_path, gamma_line))

    assert gamma == {
        "credit_score": "Int",
        "customer_tier": "String",
        "has_defaults": "Bool",
        "monthly_income": "Int",
    }
    args = json.loads((tmp_path / "args.json").read_text())
    assert args[0] == "--env" and json.loads(args[1]) == env
    assert args[2] == "--print-gamma"


def test_print_gamma_usage_error_aborts(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="64"):
        print_gamma({"x": 1.5}, fake_engine(tmp_path, "", exit_code=64))


def test_print_gamma_rejects_non_json_stdout(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="no es JSON"):
        print_gamma({}, fake_engine(tmp_path, "hola\n"))


def test_print_gamma_rejects_non_gamma_json(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="nombre: tipo"):
        print_gamma({}, fake_engine(tmp_path, '{"x": 1}\n'))


def test_print_gamma_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="no se pudo ejecutar"):
        print_gamma({}, [str(tmp_path / "no-existe")])
