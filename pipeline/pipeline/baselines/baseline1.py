"""Baseline 1: ejecución libre del script del LLM, sin validación previa.

Siempre llega a la etapa `execution` (contracts/README.md §3): cualquier falla,
incluida una respuesta que no trae `code`, se registra ahí. La ejecución va
por el sandbox sin red (specs/sandbox.md).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pipeline.baselines.sandbox import DEFAULT_TIMEOUT_SECONDS, run_in_sandbox, to_verdict
from pipeline.orchestrator import Verdict


def extract_code(llm_raw: str) -> str | None:
    """`code` de la respuesta `{"code": "..."}`; None si no se puede leer. Sin reparar nada."""
    try:
        data = json.loads(llm_raw)
    except ValueError:
        return None
    code = data.get("code") if isinstance(data, dict) else None
    return code if isinstance(code, str) else None


def run_baseline_1(
    llm_raw: str, env: Mapping[str, object], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Verdict:
    """Runner del grupo `baseline1`: `(llm_raw, env) -> Verdict`."""
    code = extract_code(llm_raw)
    if code is None:
        return {
            "outcome": "runtime_error",
            "stage": "execution",
            "result": None,
            "error": {
                "code": "InvalidResponse",
                "message": 'la respuesta no es un objeto JSON con "code" de tipo string',
            },
        }
    return to_verdict(run_in_sandbox(code, env, timeout=timeout))
