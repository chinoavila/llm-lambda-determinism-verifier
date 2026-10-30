"""Servidor de la UI: `python -m pipeline serve`. Ver specs/ui.md y docs/ui.md.

Sirve la SPA compilada (`ui/dist`) y la API bajo `/api`, con `http.server` de la
stdlib: la API es chica y local, y así no se agregan dependencias al pipeline.
Las rutas llaman a las mismas funciones que la CLI (`check-case`, `run`): el
corpus vive en `pipeline/store.py` y las corridas en `pipeline/jobs.py`.
La API nunca devuelve credenciales: del LLM solo informa si hay y qué modelos usa.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from pipeline.baselines.sandbox import SandboxError
from pipeline.jobs import RunManager
from pipeline.llm import ConfigError, load_config
from pipeline.orchestrator import EngineError
from pipeline.report import Reporter
from pipeline.store import RuleStore, StoreError

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 2 * 1024 * 1024
RECORD_FILTERS = ("case_id", "scenario_id", "group", "repetition", "outcome", "stage", "model")

Json = Any


@dataclass(frozen=True)
class Paths:
    """Carpetas que la UI lee y escribe. `static` es `None` si la SPA no está compilada."""

    corpus: Path
    out: Path
    static: Path | None
    fixtures: Path = field(default=REPO_ROOT / "contracts" / "fixtures")

    @classmethod
    def default(cls) -> Paths:
        dist = REPO_ROOT / "ui" / "dist"
        return cls(REPO_ROOT / "corpus", REPO_ROOT / "out", dist if dist.is_dir() else None)


@dataclass(frozen=True)
class Request:
    match: re.Match[str]
    query: dict[str, str]
    body: Json


Handler = Callable[[Request], tuple[HTTPStatus, Json]]


def llm_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    try:
        config = load_config(env=env)
    except ConfigError as e:  # incluye MissingCredentials: el mensaje nombra la variable, no la clave
        return {"ready": False, "models": [], "error": str(e)}
    return {"ready": True, "models": [e.model for e in config.endpoints], "error": None}


def health(paths: Paths, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Qué partes del pipeline están listas en este contenedor."""
    env = os.environ if env is None else env
    return {
        "engine": shutil.which("engine") is not None,
        "sandbox_queue": bool(env.get("SANDBOX_IO")),
        "llm": llm_status(env),
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


def body_object(req: Request) -> dict[str, Any]:
    if not isinstance(req.body, dict):
        raise StoreError(400, "el cuerpo debe ser un objeto JSON")
    return req.body


def build_routes(
    paths: Paths, store: RuleStore, runs: RunManager, reporter: Reporter
) -> list[tuple[str, re.Pattern[str], Handler]]:
    """Tabla de rutas de la API. Ver specs/ui.md."""

    def saved(case_id: str, status: HTTPStatus) -> tuple[HTTPStatus, Json]:
        check = store.verify(case_id, write=True)
        return status, {"rule": store.get(case_id), "check": check}

    def create_rule(req: Request) -> tuple[HTTPStatus, Json]:
        rule = body_object(req)
        store.create(rule)
        return saved(rule["case_id"], HTTPStatus.CREATED)

    def update_rule(req: Request) -> tuple[HTTPStatus, Json]:
        case_id = req.match["id"]
        store.update(case_id, body_object(req))
        return saved(case_id, HTTPStatus.OK)

    def delete_rule(req: Request) -> tuple[HTTPStatus, Json]:
        store.delete(req.match["id"], req.query.get("version"))
        return HTTPStatus.OK, {"deleted": req.match["id"]}

    def check_all(_req: Request) -> tuple[HTTPStatus, Json]:
        return HTTPStatus.OK, [store.verify(case_id, write=False) for case_id in store.paths()]

    def require_llm() -> None:
        if not llm_status()["ready"]:
            raise StoreError(409, "faltan las credenciales del LLM: completá .env (ver .env.example)")

    def start_run(req: Request) -> tuple[HTTPStatus, Json]:
        body = body_object(req)
        require_llm()
        job = runs.start(body, body.get("confirm_calls"))
        return HTTPStatus.CREATED, job.summary()

    def report(req: Request) -> tuple[HTTPStatus, Json]:
        evidence = body_object(req).get("evidence")
        if not isinstance(evidence, dict):
            raise StoreError(400, "evidence debe ser un objeto JSON")
        require_llm()
        return HTTPStatus.OK, reporter.generate(runs.check_id(req.match["id"]), evidence)

    def records(req: Request) -> tuple[HTTPStatus, Json]:
        unknown = sorted(set(req.query) - set(RECORD_FILTERS))
        if unknown:
            raise StoreError(400, f"filtros desconocidos: {unknown}")
        return HTTPStatus.OK, runs.records(req.match["id"], req.query)

    def offset(req: Request) -> int:
        try:
            return int(req.query.get("offset", "0"))
        except ValueError:
            raise StoreError(400, "offset debe ser un entero") from None

    rule_id = r"(?P<id>[A-Za-z0-9_\-]{1,120})"
    run_id = r"(?P<id>[0-9A-Za-z_\-]{1,80})"
    table: list[tuple[str, str, Handler]] = [
        ("GET", r"/api/health", lambda _r: (HTTPStatus.OK, health(paths))),
        ("GET", r"/api/rules", lambda _r: (HTTPStatus.OK, store.list())),
        ("POST", r"/api/rules", create_rule),
        ("POST", r"/api/rules/check", check_all),
        ("GET", rf"/api/rules/{rule_id}", lambda r: (HTTPStatus.OK, store.get(r.match["id"]))),
        ("PUT", rf"/api/rules/{rule_id}", update_rule),
        ("DELETE", rf"/api/rules/{rule_id}", delete_rule),
        ("POST", rf"/api/rules/{rule_id}/check", lambda r: (HTTPStatus.OK, store.verify(r.match["id"], write=True))),
        ("GET", r"/api/runs", lambda _r: (HTTPStatus.OK, {"active": _active(runs), "runs": runs.list_runs()})),
        ("POST", r"/api/runs/estimate", lambda r: (HTTPStatus.OK, runs.estimate(body_object(r)))),
        ("POST", r"/api/runs", start_run),
        ("POST", rf"/api/runs/{run_id}/cancel", lambda r: (HTTPStatus.OK, runs.cancel(r.match["id"]).summary())),
        ("GET", rf"/api/runs/{run_id}/log", lambda r: (HTTPStatus.OK, runs.log(r.match["id"], offset(r)))),
        ("GET", rf"/api/runs/{run_id}/records", records),
        ("POST", rf"/api/runs/{run_id}/report", report),
    ]
    return [(method, re.compile(pattern), handler) for method, pattern, handler in table]


def _active(runs: RunManager) -> Json:
    job = runs.active()
    return job.summary() if job else None


def make_handler(
    paths: Paths, store: RuleStore, runs: RunManager, reporter: Reporter
) -> type[BaseHTTPRequestHandler]:
    routes = build_routes(paths, store, runs, reporter)

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
            url = urlsplit(self.path)
            if not url.path.startswith("/api/"):
                if method == "GET":
                    self.send_static(url.path)
                else:
                    self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"{method} solo se admite en /api"})
                return
            other_method = False
            for m, pattern, handler in routes:
                match = pattern.fullmatch(url.path)
                if match is None:
                    continue
                if m != method:
                    other_method = True
                    continue
                self.run(handler, match, url.query)
                return
            if other_method:
                self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"{method} no se admite en {url.path}"})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": f"no existe {url.path}"})

        def run(self, handler: Handler, match: re.Match[str], query: str) -> None:
            try:
                req = Request(match, {k: v[-1] for k, v in parse_qs(query).items()}, self.read_body())
                status, body = handler(req)
            except StoreError as e:
                self.send_json(HTTPStatus(e.status), {"error": str(e)})
            except (SandboxError, EngineError) as e:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": f"{type(e).__name__}: {e}"})
            except Exception as e:  # noqa: BLE001 - la UI muestra el error en lugar de cortar la conexión
                traceback.print_exc(file=sys.stderr)
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(e).__name__}: {e}"})
            else:
                self.send_json(status, body)

        def read_body(self) -> Json:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise StoreError(400, "Content-Length no es un entero") from None
            if length < 0:
                raise StoreError(400, "Content-Length no puede ser negativo")
            if length == 0:
                return None
            if length > MAX_BODY:
                raise StoreError(413, "el cuerpo supera 2 MB")
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise StoreError(400, "el cuerpo no es JSON válido") from None

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


def make_server(
    host: str,
    port: int,
    paths: Paths,
    *,
    store: RuleStore | None = None,
    runs: RunManager | None = None,
    reporter: Reporter | None = None,
) -> ThreadingHTTPServer:
    store = store or RuleStore(paths.corpus)
    runs = runs or RunManager(paths.out, store, paths.fixtures)
    reporter = reporter or Reporter(paths.out)
    return ThreadingHTTPServer((host, port), make_handler(paths, store, runs, reporter))


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
