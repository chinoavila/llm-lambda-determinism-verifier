from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pipeline.cli import main
from pipeline.server import Paths, health, make_server, resolve_static


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


def request(url: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method)
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
