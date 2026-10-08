"""Reporte con IA de una corrida (specs/ui.md §Reporte con IA).

La SPA calcula la evidencia (las estadísticas de la corrida y una muestra de fallos) y
la manda por POST; acá solo se arma el prompt con las bases metodológicas del proyecto
(`report_methodology.md`), se hace una llamada al LLM y se valida la forma del informe.
El servidor no agrega ni calcula nada (mission.md §2). Cada informe queda guardado en
`out/<run_id>.report-<timestamp>.json` con la evidencia y la respuesta cruda.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.cli import Acquirer
from pipeline.llm import NoModelAvailable, build_balancer, load_config
from pipeline.store import StoreError

METHODOLOGY = Path(__file__).with_name("report_methodology.md")
OBSERVATIONS = 8
OBSERVATION_STATUS = ("se_repite", "no_se_repite", "no_concluyente")

SYSTEM_PROMPT = f"""\
Sos un investigador que redacta, en español rioplatense formal y con el tono de un informe \
científico, el reporte de una corrida del pipeline descripto en las bases metodológicas. \
Recibís esas bases y la evidencia de la corrida en JSON, calculada a partir de sus registros.

Reglas:
- Usá solo cifras que estén en la evidencia, tal como aparecen (o como porcentaje de un \
cociente que esté en ella). No inventes datos, modelos, reglas ni referencias.
- pass@1 es por generación (regla × grupo × repetición); los renglones son por escenario. \
No mezcles las dos unidades.
- Si la evidencia no alcanza para afirmar algo, decilo. Con una sola repetición o sin \
temperatura fija, las cifras no permiten comparar grupos: declaralo y no confirmes hipótesis.
- Contrastá cada una de las {OBSERVATIONS} observaciones metodológicas de las bases con la \
evidencia y decí si se repite, no se repite o no es concluyente.
- Citá las referencias de las bases como [1], [2] o [3] cuando corresponda.

Respondé solo con un objeto JSON con esta forma:
{{"title": str, "abstract": str,
 "sections": [{{"heading": str, "paragraphs": [str]}}],
 "observations": [{{"number": 1-{OBSERVATIONS}, "status": "se_repite" | "no_se_repite" | \
"no_concluyente", "text": str}}],
 "limitations": [str], "conclusions": [str]}}
Las secciones van en este orden: Introducción, Método, Resultados, Discusión. \
"observations" lleva las {OBSERVATIONS}, en orden.
"""


def build_messages(run_id: str, evidence: Mapping[str, Any], methodology: str) -> list[dict[str, str]]:
    user = (
        f"# Bases metodológicas\n\n{methodology.strip()}\n\n"
        f"# Evidencia de la corrida {run_id}\n\n{json.dumps(evidence, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _strings(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(s, str) and s.strip() for s in value):
        raise StoreError(502, f"el informe del LLM no es válido: {where} debe ser una lista de textos")
    return value


def _text(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StoreError(502, f"el informe del LLM no es válido: falta {where}{key}")
    return value


def parse_report(content: str | None) -> dict[str, Any]:
    """Valida la forma del informe. No repara: si no cumple, es un error (502)."""
    try:
        data = json.loads(content or "")
    except ValueError:
        raise StoreError(502, "el LLM no devolvió JSON válido") from None
    if not isinstance(data, dict):
        raise StoreError(502, "el informe del LLM no es válido: debe ser un objeto JSON")

    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise StoreError(502, "el informe del LLM no es válido: faltan las secciones")
    for i, s in enumerate(sections):
        if not isinstance(s, dict):
            raise StoreError(502, f"el informe del LLM no es válido: sections[{i}] debe ser un objeto")
        _text(s, "heading", f"sections[{i}].")
        _strings(s.get("paragraphs"), f"sections[{i}].paragraphs")

    observations = data.get("observations")
    if not isinstance(observations, list):
        raise StoreError(502, "el informe del LLM no es válido: faltan las observaciones")
    for i, o in enumerate(observations):
        if not isinstance(o, dict) or o.get("status") not in OBSERVATION_STATUS:
            raise StoreError(502, f"el informe del LLM no es válido: observations[{i}].status")
        number = o.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= OBSERVATIONS:
            raise StoreError(502, f"el informe del LLM no es válido: observations[{i}].number")
        _text(o, "text", f"observations[{i}].")

    return {
        "title": _text(data, "title", ""),
        "abstract": _text(data, "abstract", ""),
        "sections": [{"heading": s["heading"], "paragraphs": s["paragraphs"]} for s in sections],
        "observations": [{"number": o["number"], "status": o["status"], "text": o["text"]} for o in observations],
        "limitations": _strings(data.get("limitations"), "limitations"),
        "conclusions": _strings(data.get("conclusions"), "conclusions"),
    }


def default_balancer() -> Acquirer:
    return build_balancer(load_config())


class Reporter:
    """Una llamada al LLM por reporte. El balanceador se arma recién en el primer pedido,
    así el servidor arranca aunque falten credenciales."""

    def __init__(
        self,
        out: Path,
        *,
        methodology: Path = METHODOLOGY,
        balancer: Callable[[], Acquirer] = default_balancer,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.out = out
        self.methodology = methodology
        self._make_balancer = balancer
        self._balancer: Acquirer | None = None
        self._lock = threading.Lock()
        self.now = now

    def balancer(self) -> Acquirer:
        with self._lock:
            if self._balancer is None:
                self._balancer = self._make_balancer()
            return self._balancer

    def generate(self, run_id: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
        if not (self.out / f"{run_id}.jsonl").exists():
            raise StoreError(404, f"la corrida {run_id} no tiene registros")
        try:
            methodology = self.methodology.read_text(encoding="utf-8")
        except OSError:
            methodology = ""
        if not methodology.strip():
            raise StoreError(409, f"falta la metodología del reporte ({self.methodology.name})")

        messages = build_messages(run_id, evidence, methodology)
        try:
            with self.balancer().acquire() as assignment:
                call = assignment.complete(messages)
        except NoModelAvailable as e:
            raise StoreError(503, f"no hay modelos disponibles: {e}") from None

        created = self.now()
        stamp = created.strftime("%Y%m%dT%H%M%SZ")
        saved = self.out / f"{run_id}.report-{stamp}.json"
        trace = {
            "run_id": run_id,
            "created_at": created.isoformat(timespec="seconds"),
            "endpoint": call.endpoint,
            "model": call.model,
            "request_params": dict(call.request_params),
            "outcome": call.outcome,
            "finish_reason": call.finish_reason,
            "usage": dict(call.usage) if call.usage is not None else None,
            "duration_seconds": call.duration_seconds,
            "evidence": evidence,
            "content": call.content,
            "raw_response": call.raw_response,
        }
        saved.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if call.outcome == "quota_exhausted":
            raise StoreError(429, f"se agotó la cuota de {call.model}: probá más tarde")
        if call.outcome != "ok":
            last = call.attempts[-1].error if call.attempts else None
            raise StoreError(502, f"el LLM falló ({call.outcome}{f': {last}' if last else ''})")
        return {
            "report": parse_report(call.content),
            "model": call.model,
            "usage": trace["usage"],
            "saved": saved.name,
        }
