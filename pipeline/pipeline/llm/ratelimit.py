"""Lectura de headers de rate limit (x-ratelimit-*, retry-after).

Formato de Groq/OpenAI: los reset vienen como duración estilo Go ("2m59.56s",
"7.66s", "500ms") y retry-after en segundos. Si un proveedor no manda estos
headers, todos los campos quedan en None y el balanceo es solo reactivo.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


@dataclass(frozen=True)
class RateLimitSnapshot:
    remaining_tokens: int | None
    tokens_reset_seconds: float | None
    remaining_requests: int | None
    requests_reset_seconds: float | None
    retry_after_seconds: float | None


def parse_headers(headers: Mapping[str, str]) -> RateLimitSnapshot:
    return RateLimitSnapshot(
        remaining_tokens=_int(headers.get("x-ratelimit-remaining-tokens")),
        tokens_reset_seconds=parse_duration(headers.get("x-ratelimit-reset-tokens")),
        remaining_requests=_int(headers.get("x-ratelimit-remaining-requests")),
        requests_reset_seconds=parse_duration(headers.get("x-ratelimit-reset-requests")),
        retry_after_seconds=parse_duration(headers.get("retry-after")),
    )


def parse_duration(value: str | None) -> float | None:
    """Segundos a partir de "7.66s", "2m59.56s", "500ms" o "12"; None si no se entiende."""
    if value is None:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    total, pos = 0.0, 0
    for m in _DURATION_PART.finditer(value):
        if m.start() != pos:
            return None
        total += float(m.group(1)) * _UNIT_SECONDS[m.group(2)]
        pos = m.end()
    return total if pos and pos == len(value) else None


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
