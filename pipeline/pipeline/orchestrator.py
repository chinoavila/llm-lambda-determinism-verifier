"""Orquestador del pipeline (C-2).

PLACEHOLDER: reemplazar por la invocación real al LLM, el ruteo por grupo
(Tratamiento -> engine/ vía subproceso, Baselines -> pipeline.baselines) y el
registro JSON Lines de cada caso. Ver specs/roadmap.md y contracts/.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence

# Binario del engine (contracts/README.md §2). Se elige con ENGINE_BIN.
DEFAULT_ENGINE_CMD = (os.environ.get("ENGINE_BIN", "engine"),)
GAMMA_TIMEOUT_SECONDS = 10.0


class EngineError(Exception):
    """El engine no respetó el contrato CLI o salió con 64/70: abortar la corrida."""


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


def route_case(group: str) -> str:
    """PLACEHOLDER: reemplazar por el ruteo real hacia C-1 o los baselines."""
    return group
