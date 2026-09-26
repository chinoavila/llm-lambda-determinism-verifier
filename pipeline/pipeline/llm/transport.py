"""Transporte HTTP mínimo sobre la stdlib (urllib), inyectable para tests."""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.message import Message
from typing import Protocol


class TransportError(Exception):
    """Fallo de red o timeout: no hubo respuesta HTTP."""


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)  # lleva Authorization
    body: bytes | None
    timeout: float


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]  # nombres en minúscula
    body: bytes


class Transport(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Seguir un redirect reenviaría el header Authorization a otro host.
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class UrllibTransport:
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirect)

    def send(self, request: HttpRequest) -> HttpResponse:
        req = urllib.request.Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with self._opener.open(req, timeout=request.timeout) as resp:
                return HttpResponse(resp.status, _lower(resp.headers), resp.read())
        except urllib.error.HTTPError as e:
            return HttpResponse(e.code, _lower(e.headers), e.read())
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            raise TransportError(str(e)) from e


def _lower(headers: Message) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}
