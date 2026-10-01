"""Armado del request chat/completions y tipos del resultado de una llamada.

Toda llamada usa `response_format = json_object` (decisión de diseño, los tres
grupos por igual; ver specs/llm-client.md). La respuesta cruda se conserva sin
transformar: acá solo se lee, nunca se repara.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pipeline.llm.config import Endpoint
from pipeline.llm.transport import HttpRequest

USER_AGENT = "llm-lambda-determinism-verifier/0.1"
RESPONSE_FORMAT = {"type": "json_object"}

# Códigos de error 400 que significan "el modelo no logró generar JSON válido".
GENERATION_FAILED_CODES = frozenset({"json_validate_failed"})

Outcome = Literal[
    "ok",  # 2xx: el orquestador ruteará la respuesta al runner del caso.
    "generation_failed",  # 400 por JSON inválido del modelo; no se reintenta y el orquestador registra llm_error.
    "quota_exhausted",  # 429 con espera > max_wait_seconds; el orquestador registra llm_error sin reintento.
    "transport_error",  # red/timeout/5xx tras agotar retries; el orquestador lo trata como llm_error y corta el caso.
    "request_error",  # cualquier otro 4xx (config, auth, modelo inexistente); se registra llm_error y no se reintenta.
]


@dataclass(frozen=True)
class Attempt:
    status: int | None  # None = no hubo respuesta HTTP
    error: str | None
    duration_seconds: float
    waited_seconds: float  # espera posterior a este intento, antes del siguiente


@dataclass(frozen=True)
class LLMCall:
    """Procedencia completa de una llamada; lo registra el orquestador."""

    outcome: Outcome
    endpoint: str
    base_url: str
    model: str
    request_params: Mapping[str, Any]  # cuerpo enviado, sin `messages`
    content: str | None
    finish_reason: str | None
    usage: Mapping[str, Any] | None
    raw_response: str | None  # cuerpo HTTP de la última respuesta, sin tocar
    attempts: tuple[Attempt, ...]
    duration_seconds: float


def build_chat_request(
    endpoint: Endpoint, messages: Sequence[Mapping[str, str]], timeout: float
) -> tuple[HttpRequest, dict[str, Any]]:
    request_params: dict[str, Any] = {
        **endpoint.params,
        "model": endpoint.model,
        "response_format": RESPONSE_FORMAT,
    }
    body = {**request_params, "messages": [dict(m) for m in messages]}
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    request = HttpRequest(
        method="POST",
        url=f"{endpoint.base_url}/chat/completions",
        headers=headers,
        body=json.dumps(body).encode("utf-8"),
        timeout=timeout,
    )
    return request, request_params


def build_models_request(
    base_url: str, api_key: str | None, timeout: float
) -> HttpRequest:
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return HttpRequest("GET", f"{base_url}/models", headers, None, timeout)


def read_completion(
    body: str,
) -> tuple[str | None, str | None, Mapping[str, Any] | None]:
    """(content, finish_reason, usage) de una respuesta 2xx; None donde falte."""
    data = _json_object(body)
    if data is None:
        return None, None, None
    usage = data.get("usage")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None, None, usage if isinstance(usage, dict) else None
    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    finish = choice.get("finish_reason")
    return (
        content if isinstance(content, str) else None,
        finish if isinstance(finish, str) else None,
        usage if isinstance(usage, dict) else None,
    )


def error_code(body: str) -> str | None:
    data = _json_object(body)
    error = data.get("error") if data is not None else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def listed_model_ids(body: str) -> set[str] | None:
    data = _json_object(body)
    items = data.get("data") if data is not None else None
    if not isinstance(items, list):
        return None
    return {m["id"] for m in items if isinstance(m, dict) and isinstance(m.get("id"), str)}


def _json_object(body: str) -> dict[str, Any] | None:
    try:
        data = json.loads(body)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
