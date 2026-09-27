from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pipeline.cli import main
from pipeline.server import Paths, health, make_server, resolve_static
from pipeline.store import RuleStore

EXAMPLE = Path(__file__).parent / "data" / "corpus" / "ejemplo-cat3-cuota.json"


@pytest.fixture()
def paths(tmp_path: Path) -> Paths:
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (static / "assets" / "app-1a2b.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    corpus, out = tmp_path / "corpus", tmp_path / "out"
    corpus.mkdir()
    out.mkdir()
    (corpus / "a.json").write_text("{}", encoding="utf-8")
    (corpus / "README.md").write_text("", encoding="utf-8")
    (out / "r1.jsonl").write_text("", encoding="utf-8")
    return Paths(corpus=corpus, out=out, static=static)


@pytest.fixture()
def base_url(paths: Paths) -> Iterator[str]:
    server = make_server("127.0.0.1", 0, paths)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def request(url: str, method: str = "GET", body: Any = None) -> tuple[int, dict[str, str], bytes]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def as_json(body: bytes) -> Any:
    return json.loads(body.decode("utf-8"))


# --- health -----------------------------------------------------------------------


def test_health_without_credentials_names_the_variable(paths: Paths) -> None:
    result = health(paths, env={"SANDBOX_IO": "/io"})
    assert result["llm"]["ready"] is False
    assert "GROQ_API_KEY" in result["llm"]["error"]
    assert result["sandbox_queue"] is True
    assert (result["corpus_rules"], result["runs"]) == (1, 1)


def test_health_never_returns_the_api_key(paths: Paths) -> None:
    result = health(paths, env={"GROQ_API_KEY": "gsk-SECRETO-123"})
    assert result["llm"]["ready"] is True and result["llm"]["models"]
    assert "SECRETO" not in json.dumps(result)


# --- archivos de la SPA --------------------------------------------------------------


@pytest.mark.parametrize(
    ("url_path", "expected"),
    [
        ("/", "index.html"),
        ("/corpus", "index.html"),  # ruta de la app
        ("/corpus/FIS-C1-EITC", "index.html"),
        ("/assets/app-1a2b.js", "app-1a2b.js"),
        ("/assets/falta.js", None),  # archivo que no existe: 404, no index.html
        ("/../secret.txt", None),
        ("/%2e%2e/secret.txt", None),
    ],
)
def test_resolve_static(paths: Paths, url_path: str, expected: str | None) -> None:
    assert paths.static is not None
    found = resolve_static(paths.static, url_path)
    assert (found.name if found else None) == expected


# --- HTTP ---------------------------------------------------------------------------


def test_http_health(base_url: str) -> None:
    status, headers, body = request(f"{base_url}/api/health")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert set(as_json(body)) == {"engine", "sandbox_queue", "llm", "corpus_rules", "runs"}


def test_http_unknown_api_and_wrong_method(base_url: str) -> None:
    status, _, body = request(f"{base_url}/api/nada")
    assert status == 404 and "no existe" in as_json(body)["error"]
    status, _, body = request(f"{base_url}/api/health", method="POST")
    assert status == 405


def test_http_serves_spa_and_assets(base_url: str) -> None:
    status, headers, body = request(f"{base_url}/corpus")
    assert status == 200 and body == b"<div id=root></div>" and headers["Cache-Control"] == "no-cache"
    status, headers, _ = request(f"{base_url}/assets/app-1a2b.js")
    assert status == 200 and headers["Content-Type"].startswith("text/javascript")
    assert "immutable" in headers["Cache-Control"]
    status, _, _ = request(f"{base_url}/assets/falta.js")
    assert status == 404


def test_http_without_compiled_ui(tmp_path: Path) -> None:
    server = make_server("127.0.0.1", 0, Paths(corpus=tmp_path, out=tmp_path, static=None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(f"http://127.0.0.1:{server.server_address[1]}/")
        assert status == 404 and "no está compilada" in as_json(body)["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_serve_command_is_registered() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["serve", "--help"])
    assert exc.value.code == 0


# --- Corpus y corridas por HTTP (etapas 2 y 3) ---------------------------------------


class NoEngineStore(RuleStore):
    """Store sin engine ni sandbox: `verify` responde fijo (check-case se prueba en test_store)."""

    def verify(self, case_id: str, *, write: bool = True) -> dict[str, Any]:
        return {"case_id": case_id, "ok": True, "issues": [], "filled": 0}


@pytest.fixture()
def api(tmp_path: Path) -> Iterator[str]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shutil.copy(EXAMPLE, corpus / EXAMPLE.name)
    paths = Paths(corpus=corpus, out=tmp_path / "out", static=None, fixtures=tmp_path)
    server = make_server("127.0.0.1", 0, paths, store=NoEngineStore(corpus))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_http_rules_crud(api: str) -> None:
    status, _, body = request(f"{api}/api/rules")
    assert status == 200 and [r["case_id"] for r in as_json(body)] == ["EJ-CAT3-CUOTA"]

    rule = as_json(request(f"{api}/api/rules/EJ-CAT3-CUOTA")[2])
    rule["description"] = "Otra redacción."
    status, _, body = request(f"{api}/api/rules/EJ-CAT3-CUOTA", "PUT", rule)
    saved = as_json(body)
    assert status == 200 and saved["rule"]["description"] == "Otra redacción." and saved["check"]["ok"]

    status, _, body = request(f"{api}/api/rules/EJ-CAT3-CUOTA", "PUT", rule)  # versión vieja
    assert status == 409 and "cambió" in as_json(body)["error"]

    status, _, body = request(f"{api}/api/rules", "POST", {**rule, "case_id": "NUEVA"})
    assert status == 201 and as_json(body)["rule"]["_file"] == "nueva.json"

    version = as_json(request(f"{api}/api/rules/NUEVA")[2])["_version"]
    status, _, _ = request(f"{api}/api/rules/NUEVA?version={version}", "DELETE")
    assert status == 200
    assert request(f"{api}/api/rules/NUEVA")[0] == 404


def test_http_rejects_bad_bodies(api: str) -> None:
    req = urllib.request.Request(f"{api}/api/rules", method="POST", data=b"{no es json")
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        assert e.code == 400 and "JSON" in as_json(e.read())["error"]
    status, _, _ = request(f"{api}/api/rules", "POST", ["lista"])
    assert status == 400


def test_http_run_estimate_and_start_guard(api: str, monkeypatch: pytest.MonkeyPatch) -> None:
    status, _, body = request(f"{api}/api/runs/estimate", "POST", {"source": "corpus", "repetitions": 3})
    assert status == 200 and as_json(body)["calls"] == 9
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    status, _, body = request(f"{api}/api/runs", "POST", {"source": "corpus", "confirm_calls": 3})
    assert status == 409 and "credenciales" in as_json(body)["error"]
    status, _, body = request(f"{api}/api/runs")
    assert status == 200 and as_json(body) == {"active": None, "runs": []}


def test_http_records_reject_unknown_filters(api: str) -> None:
    status, _, body = request(f"{api}/api/runs/r1/records?color=rojo")
    assert status == 400 and "color" in as_json(body)["error"]
