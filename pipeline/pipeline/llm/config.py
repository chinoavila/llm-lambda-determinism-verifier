"""Configuración del cliente LLM agnóstico (ver specs/llm-client.md).

El proveedor queda definido solo por la configuración del usuario: un archivo
TOML (ruta en LLM_CONFIG) con el pool de endpoints OpenAI-compatibles. Las
claves nunca van en el TOML: cada endpoint nombra la variable de entorno que
la contiene (`api_key_env`).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = "llm.toml"

# El cliente fija estos campos del request; la config no puede pisarlos.
RESERVED_PARAMS = frozenset({"model", "messages", "response_format", "stream"})


class ConfigError(Exception):
    """La configuración del LLM es inválida o incompleta."""


class MissingCredentials(ConfigError):
    """Falta la variable de entorno con la clave de un endpoint (`.env` sin completar)."""


@dataclass(frozen=True)
class Endpoint:
    """Un modelo servido por una API OpenAI-compatible."""

    name: str
    base_url: str
    model: str
    priority: int
    api_key: str | None = field(repr=False)
    params: Mapping[str, Any]


@dataclass(frozen=True)
class BalancerSettings:
    reserve_tokens: int
    min_remaining_requests: int
    max_wait_seconds: float
    max_transport_retries: int
    backoff_base_seconds: float
    request_timeout_seconds: float


@dataclass(frozen=True)
class LLMConfig:
    balancer: BalancerSettings
    endpoints: tuple[Endpoint, ...]


def load_config(
    path: str | Path | None = None, env: Mapping[str, str] | None = None
) -> LLMConfig:
    """Lee el TOML indicado (o LLM_CONFIG, o ./llm.toml) y resuelve las claves."""
    env = os.environ if env is None else env
    if path is None:
        path = env.get("LLM_CONFIG") or DEFAULT_CONFIG_PATH
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"no se pudo leer {path}: {e}") from e
    return parse_config(data, env)


def parse_config(data: Mapping[str, Any], env: Mapping[str, str]) -> LLMConfig:
    balancer = _table(data, "balancer", "raíz")
    settings = BalancerSettings(
        reserve_tokens=_int(balancer, "reserve_tokens", "balancer"),
        min_remaining_requests=_int(balancer, "min_remaining_requests", "balancer"),
        max_wait_seconds=_number(balancer, "max_wait_seconds", "balancer"),
        max_transport_retries=_int(balancer, "max_transport_retries", "balancer"),
        backoff_base_seconds=_number(balancer, "backoff_base_seconds", "balancer"),
        request_timeout_seconds=_number(balancer, "request_timeout_seconds", "balancer"),
    )

    raw_endpoints = data.get("endpoints")
    if not isinstance(raw_endpoints, list) or not raw_endpoints:
        raise ConfigError("falta al menos un [[endpoints]]")

    endpoints: list[Endpoint] = []
    for i, raw in enumerate(raw_endpoints):
        where = f"endpoints[{i}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{where} debe ser una tabla")
        endpoints.append(_endpoint(raw, where, env))

    names = [e.name for e in endpoints]
    if len(set(names)) != len(names):
        raise ConfigError("los `name` de [[endpoints]] deben ser únicos")
    return LLMConfig(balancer=settings, endpoints=tuple(endpoints))


def _endpoint(raw: Mapping[str, Any], where: str, env: Mapping[str, str]) -> Endpoint:
    base_url = _str(raw, "base_url", where).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigError(f"{where}.base_url debe empezar con http:// o https://")

    api_key: str | None = None
    if "api_key_env" in raw:
        var = _str(raw, "api_key_env", where)
        api_key = env.get(var) or None
        if api_key is None:
            raise MissingCredentials(f"{where}: la variable de entorno {var} no está definida")

    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ConfigError(f"{where}.params debe ser una tabla")
    reserved = RESERVED_PARAMS & params.keys()
    if reserved:
        raise ConfigError(f"{where}.params no puede definir {sorted(reserved)}")

    return Endpoint(
        name=_str(raw, "name", where),
        base_url=base_url,
        model=_str(raw, "model", where),
        priority=_int(raw, "priority", where),
        api_key=api_key,
        params=dict(params),
    )


def _table(data: Mapping[str, Any], key: str, where: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"falta la tabla [{key}] en {where}")
    return value


def _str(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where}.{key} debe ser un string no vacío")
    return value


def _int(data: Mapping[str, Any], key: str, where: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{where}.{key} debe ser un entero >= 0")
    return value


def _number(data: Mapping[str, Any], key: str, where: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{where}.{key} debe ser un número >= 0")
    return float(value)
