"""Servidor de la UI: `python -m pipeline serve`. Ver specs/ui.md y docs/ui.md.

Sirve la SPA compilada (`ui/dist`) y la API bajo `/api`, con `http.server` de la
stdlib: la API es chica y local, y así no se agregan dependencias al pipeline.
La API nunca devuelve credenciales: del LLM solo informa si hay y qué modelos usa.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from pipeline.llm import ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parents[2]

Json = dict[str, Any]
Handler = Callable[[re.Match[str]], tuple[HTTPStatus, Json]]


@dataclass(frozen=True)
class Paths:
    """Carpetas que la UI lee y escribe. `static` es `None` si la SPA no está compilada."""

    corpus: Path
    out: Path
    static: Path | None

    @classmethod
    def default(cls) -> Paths:
        dist = REPO_ROOT / "ui" / "dist"
        return cls(REPO_ROOT / "corpus", REPO_ROOT / "out", dist if dist.is_dir() else None)


def health(paths: Paths, env: Mapping[str, str] | None = None) -> Json:
    """Qué partes del pipeline están listas en este contenedor."""
    env = os.environ if env is None else env
    try:
        config = load_config(env=env)
        llm: Json = {"ready": True, "models": [e.model for e in config.endpoints], "error": None}
    except ConfigError as e:  # incluye MissingCredentials: el mensaje nombra la variable, no la clave
        llm = {"ready": False, "models": [], "error": str(e)}
    return {
        "engine": shutil.which("engine") is not None,
        "sandbox_queue": bool(env.get("SANDBOX_IO")),
        "llm": llm,
        "corpus_rules": len(list(paths.corpus.glob("*.json"))) if paths.corpus.is_dir() else 0,
        "runs": len(list(paths.out.glob("*.jsonl"))) if paths.out.is_dir() else 0,
    }


def resolve_static(root: Path, url_path: str) -> Path | None:
    """Archivo de la SPA para `url_path`. Las rutas de la app (sin extensión) caen en
    `index.html`; un archivo que falta o una ruta que sale de `root` dan `None`."""
    root = root.resolve()
    rel = unquote(url_path).lstrip("/")
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    if "." in candidate.name:
        return None
    return root / "index.html"


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def make_handler(paths: Paths) -> type[BaseHTTPRequestHandler]:
    routes: list[tuple[str, re.Pattern[str], Handler]] = [
        ("GET", re.compile(r"/api/health"), lambda _m: (HTTPStatus.OK, health(paths))),
    ]

    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "pipeline-ui"

        def do_GET(self) -> None:
            self.dispatch("GET")

        def do_POST(self) -> None:
            self.dispatch("POST")

        def do_PUT(self) -> None:
            self.dispatch("PUT")

        def do_DELETE(self) -> None:
            self.dispatch("DELETE")

        def dispatch(self, method: str) -> None:
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                other_method = False
                for m, r, h in routes:
                    match = r.fullmatch(path)
                    if match is None:
                        continue
                    if m != method:
                        other_method = True
                        continue
                    status, body = h(match)
                    self.send_json(status, body)
                    return
                if other_method:
                    self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"{method} no se admite en {path}"})
                else:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": f"no existe {path}"})
            elif method == "GET":
                self.send_static(path)
            else:
                self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"{method} solo se admite en /api"})

        def send_json(self, status: HTTPStatus, body: Json) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def send_static(self, path: str) -> None:
            if paths.static is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "la UI no está compilada (ver docs/ui.md)"})
                return
            target = resolve_static(paths.static, path)
            if target is None or not target.is_file():
                self.send_json(HTTPStatus.NOT_FOUND, {"error": f"no existe {path}"})
                return
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            # Los assets de Vite llevan hash en el nombre; index.html no.
            cache = "no-cache" if target.name == "index.html" else "public, max-age=31536000, immutable"
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[ui] {self.address_string()} {format % args}", file=sys.stderr, flush=True)

    return RequestHandler


def make_server(host: str, port: int, paths: Paths) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(paths))


def serve(host: str, port: int, paths: Paths | None = None) -> int:
    paths = paths or Paths.default()
    server = make_server(host, port, paths)
    ui = paths.static or "sin compilar"
    print(f"UI en http://localhost:{server.server_address[1]} (SPA: {ui})", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
