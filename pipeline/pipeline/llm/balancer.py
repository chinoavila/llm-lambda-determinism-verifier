"""Balanceo de modelos con modelo fijo por caso (ver specs/llm-client.md).

Uso desde el orquestador (thread-safe, un `ModelAssignment` por caso):

    balancer = build_balancer(load_config())
    with balancer.acquire() as assignment:  # elige el modelo del caso
        tratamiento = assignment.complete(messages_tratamiento)
        baseline_1 = assignment.complete(messages_b1)
        baseline_2 = assignment.complete(messages_b2)

- Proactivo: cada respuesta actualiza lo que queda de cuota según los headers
  x-ratelimit-*; un modelo sin margen no recibe casos nuevos hasta su reset.
- Reactivo: un 429 pone el modelo en cooldown (retry-after). Dentro del caso se
  espera y se reintenta el mismo modelo, salvo que la espera supere
  max_wait_seconds: entonces el desenlace es `quota_exhausted`.
- Red/timeout/5xx: backoff exponencial, hasta max_transport_retries reintentos.
- Otros 4xx y el 400 de JSON inválido no se reintentan.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType

from pipeline.llm.client import (
    GENERATION_FAILED_CODES,
    Attempt,
    LLMCall,
    Outcome,
    build_chat_request,
    build_models_request,
    error_code,
    listed_model_ids,
    read_completion,
)
from pipeline.llm.config import Endpoint, LLMConfig
from pipeline.llm.ratelimit import RateLimitSnapshot, parse_headers
from pipeline.llm.transport import Transport, TransportError, UrllibTransport

log = logging.getLogger(__name__)


class NoModelAvailable(Exception):
    """Pool vacío, o ningún modelo se libera dentro de max_wait_seconds."""


@dataclass
class _ModelState:
    endpoint: Endpoint
    unavailable_reason: str | None = None
    active_assignments: int = 0
    cooldown_until: float = 0.0
    remaining_tokens: int | None = None
    tokens_reset_at: float | None = None
    remaining_requests: int | None = None
    requests_reset_at: float | None = None


class Balancer:
    def __init__(
        self,
        config: LLMConfig,
        transport: Transport,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = config.balancer
        self.transport = transport
        self.clock = clock
        self.sleep = sleep
        self._cond = threading.Condition()
        self._states = {e.name: _ModelState(e) for e in config.endpoints}

    def health_check(self) -> None:
        """GET {base_url}/models por endpoint; excluye modelos no listados o inalcanzables."""
        groups: dict[tuple[str, str | None], list[_ModelState]] = {}
        for st in self._states.values():
            key = (st.endpoint.base_url, st.endpoint.api_key)
            groups.setdefault(key, []).append(st)

        for (base_url, api_key), states in groups.items():
            request = build_models_request(
                base_url, api_key, self.settings.request_timeout_seconds
            )
            reason: str | None = None
            ids: set[str] | None = None
            try:
                resp = self.transport.send(request)
            except TransportError as e:
                reason = f"endpoint no responde: {e}"
            else:
                if resp.status != 200:
                    reason = f"GET /models devolvió {resp.status}"
                else:
                    ids = listed_model_ids(resp.body.decode("utf-8", errors="replace"))
                    if ids is None:
                        reason = "GET /models devolvió un cuerpo inesperado"
            with self._cond:
                for st in states:
                    if reason is None and ids is not None and st.endpoint.model not in ids:
                        st.unavailable_reason = "modelo no listado en GET /models"
                    else:
                        st.unavailable_reason = reason
                    if st.unavailable_reason:
                        log.warning(
                            "modelo excluido del pool: %s (%s)",
                            st.endpoint.name,
                            st.unavailable_reason,
                        )

    def available_endpoints(self) -> list[str]:
        with self._cond:
            return [n for n, st in self._states.items() if st.unavailable_reason is None]

    def acquire(self) -> ModelAssignment:
        """Bloquea hasta que un modelo tenga margen; elige por prioridad y carga."""
        with self._cond:
            while True:
                now = self.clock()
                pool = [st for st in self._states.values() if st.unavailable_reason is None]
                if not pool:
                    raise NoModelAvailable("no queda ningún modelo disponible en el pool")
                ready = [st for st in pool if self._ready_at(st, now) <= now]
                if ready:
                    st = min(
                        ready,
                        key=lambda s: (s.endpoint.priority, s.active_assignments, s.endpoint.name),
                    )
                    st.active_assignments += 1
                    return ModelAssignment(self, st.endpoint)
                wait = min(self._ready_at(st, now) for st in pool) - now
                if wait > self.settings.max_wait_seconds:
                    raise NoModelAvailable(
                        f"el próximo modelo se libera en {wait:.1f}s "
                        f"(> max_wait_seconds={self.settings.max_wait_seconds})"
                    )
                self._cond.wait(timeout=wait)

    def _ready_at(self, st: _ModelState, now: float) -> float:
        at = max(now, st.cooldown_until)
        s = self.settings
        if (
            st.remaining_requests is not None
            and st.requests_reset_at is not None
            and now < st.requests_reset_at
            and st.remaining_requests < s.min_remaining_requests
        ):
            at = max(at, st.requests_reset_at)
        if (
            st.remaining_tokens is not None
            and st.tokens_reset_at is not None
            and now < st.tokens_reset_at
            and st.remaining_tokens - s.reserve_tokens * st.active_assignments < s.reserve_tokens
        ):
            at = max(at, st.tokens_reset_at)
        return at

    def _observe(self, name: str, snap: RateLimitSnapshot, now: float) -> None:
        with self._cond:
            st = self._states[name]
            if snap.remaining_tokens is not None:
                st.remaining_tokens = snap.remaining_tokens
                st.tokens_reset_at = _deadline(now, snap.tokens_reset_seconds)
            if snap.remaining_requests is not None:
                st.remaining_requests = snap.remaining_requests
                st.requests_reset_at = _deadline(now, snap.requests_reset_seconds)
            self._cond.notify_all()

    def _cooldown(self, name: str, until: float) -> None:
        with self._cond:
            st = self._states[name]
            st.cooldown_until = max(st.cooldown_until, until)

    def _release(self, name: str) -> None:
        with self._cond:
            self._states[name].active_assignments -= 1
            self._cond.notify_all()


class ModelAssignment:
    """Modelo asignado a un caso. Todas las llamadas del caso van a este modelo."""

    def __init__(self, balancer: Balancer, endpoint: Endpoint) -> None:
        self._balancer = balancer
        self.endpoint = endpoint
        self._released = False

    def __enter__(self) -> ModelAssignment:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._balancer._release(self.endpoint.name)

    def complete(self, messages: Sequence[Mapping[str, str]]) -> LLMCall:
        b = self._balancer
        s = b.settings
        ep = self.endpoint
        request, request_params = build_chat_request(ep, messages, s.request_timeout_seconds)
        attempts: list[Attempt] = []
        transport_failures = 0
        started = b.clock()

        def finish(
            outcome: Outcome,
            raw: str | None,
            content: str | None = None,
            finish_reason: str | None = None,
            usage: Mapping[str, object] | None = None,
        ) -> LLMCall:
            return LLMCall(
                outcome=outcome,
                endpoint=ep.name,
                base_url=ep.base_url,
                model=ep.model,
                request_params=request_params,
                content=content,
                finish_reason=finish_reason,
                usage=usage,
                raw_response=raw,
                attempts=tuple(attempts),
                duration_seconds=b.clock() - started,
            )

        while True:
            t0 = b.clock()
            try:
                resp = b.transport.send(request)
            except TransportError as e:
                status: int | None = None
                error: str | None = str(e)
                raw: str | None = None
            else:
                status, error = resp.status, None
                raw = resp.body.decode("utf-8", errors="replace")
                snap = parse_headers(resp.headers)
                b._observe(ep.name, snap, b.clock())
            duration = b.clock() - t0

            if status is not None and 200 <= status < 300:
                attempts.append(Attempt(status, None, duration, 0.0))
                assert raw is not None
                content, finish_reason, usage = read_completion(raw)
                return finish("ok", raw, content, finish_reason, usage)

            if status == 429:
                wait = (
                    snap.retry_after_seconds
                    or snap.tokens_reset_seconds
                    or s.backoff_base_seconds
                )
                b._cooldown(ep.name, b.clock() + wait)
                if wait > s.max_wait_seconds:
                    attempts.append(Attempt(status, "429 rate limit", duration, 0.0))
                    return finish("quota_exhausted", raw)
                attempts.append(Attempt(status, "429 rate limit", duration, wait))
                b.sleep(wait)
                continue

            if status is None or status >= 500:
                transport_failures += 1
                if transport_failures > s.max_transport_retries:
                    attempts.append(Attempt(status, error, duration, 0.0))
                    return finish("transport_error", raw)
                wait = s.backoff_base_seconds * 2 ** (transport_failures - 1)
                attempts.append(Attempt(status, error, duration, wait))
                b.sleep(wait)
                continue

            attempts.append(Attempt(status, None, duration, 0.0))
            assert raw is not None
            if status == 400 and error_code(raw) in GENERATION_FAILED_CODES:
                return finish("generation_failed", raw)
            return finish("request_error", raw)


def build_balancer(config: LLMConfig, transport: Transport | None = None) -> Balancer:
    """Construye el balanceador y corre el health check inicial."""
    balancer = Balancer(config, transport or UrllibTransport())
    balancer.health_check()
    if not balancer.available_endpoints():
        raise NoModelAvailable("el health check excluyó todos los modelos del pool")
    return balancer


def _deadline(now: float, seconds: float | None) -> float | None:
    return now + seconds if seconds is not None and math.isfinite(seconds) else None
