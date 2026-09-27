from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from pipeline.store import RuleStore, StoreError, reconcile_expected, slug

EXAMPLES = Path(__file__).parent / "data" / "corpus"
REAL_STACK = pytest.mark.skipif(
    shutil.which("engine") is None or "SANDBOX_IO" not in os.environ,
    reason="necesita el engine y el sandbox (correr en Docker Compose)",
)


@pytest.fixture()
def store(tmp_path: Path) -> RuleStore:
    for p in EXAMPLES.glob("*.json"):
        shutil.copy(p, tmp_path / p.name)
    (tmp_path / "README.md").write_text("no es una regla", encoding="utf-8")
    (tmp_path / "roto.json").write_text("{", encoding="utf-8")
    return RuleStore(tmp_path)


def example(name: str = "ejemplo-cat3-cuota.json") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return data


def status_of(exc: pytest.ExceptionInfo[StoreError]) -> int:
    return exc.value.status


def test_list_and_get_add_version_and_file(store: RuleStore) -> None:
    ids = sorted(r["case_id"] for r in store.list())
    assert ids == ["EJ-CAT1-RIESGO", "EJ-CAT2-BENEFICIO", "EJ-CAT3-CUOTA"]  # sin README ni roto.json
    rule = store.get("EJ-CAT3-CUOTA")
    assert rule["_file"] == "ejemplo-cat3-cuota.json" and len(rule["_version"]) == 16
    with pytest.raises(StoreError) as exc:
        store.get("NO-EXISTE")
    assert status_of(exc) == 404


def test_create_writes_a_new_file_without_internal_fields(store: RuleStore) -> None:
    rule = {**example(), "case_id": "NUEVA_Regla-1", "_version": "x", "_file": "y"}
    path = store.create(rule)
    assert path.name == "nueva-regla-1.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["case_id"] == "NUEVA_Regla-1" and "_version" not in written and "_file" not in written


@pytest.mark.parametrize(
    ("case_id", "status"),
    [("EJ-CAT3-CUOTA", 409), ("con espacios", 400), ("", 400), (7, 400)],
)
def test_create_rejects_duplicates_and_bad_ids(store: RuleStore, case_id: object, status: int) -> None:
    with pytest.raises(StoreError) as exc:
        store.create({**example(), "case_id": case_id})
    assert status_of(exc) == status


def test_update_requires_the_version_that_was_read(store: RuleStore) -> None:
    rule = store.get("EJ-CAT3-CUOTA")
    rule["description"] = "Nueva redacción."
    store.update("EJ-CAT3-CUOTA", rule)
    assert store.get("EJ-CAT3-CUOTA")["description"] == "Nueva redacción."
    with pytest.raises(StoreError) as exc:  # la misma versión ya no vale
        store.update("EJ-CAT3-CUOTA", rule)
    assert status_of(exc) == 409


def test_update_cannot_change_the_id(store: RuleStore) -> None:
    rule = store.get("EJ-CAT3-CUOTA")
    with pytest.raises(StoreError) as exc:
        store.update("EJ-CAT3-CUOTA", {**rule, "case_id": "OTRO"})
    assert status_of(exc) == 400


def test_delete_requires_the_version(store: RuleStore) -> None:
    version = store.get("EJ-CAT1-RIESGO")["_version"]
    with pytest.raises(StoreError):
        store.delete("EJ-CAT1-RIESGO", "vieja")
    store.delete("EJ-CAT1-RIESGO", version)
    assert "EJ-CAT1-RIESGO" not in store.paths()


def test_reconcile_expected() -> None:
    old = example()
    same = reconcile_expected(old, old)
    assert all("expected" in s for s in same["scenarios"])

    env_changed = json.loads(json.dumps(old))
    env_changed["scenarios"][0]["env"]["cuota"] = 1234.5
    result = reconcile_expected(old, env_changed)
    assert "expected" not in result["scenarios"][0] and "expected" in result["scenarios"][1]

    ast_changed = json.loads(json.dumps(old))
    ast_changed["canonical_ast"]["expr"]["op"] = "OR"
    assert not any("expected" in s for s in reconcile_expected(old, ast_changed)["scenarios"])

    manual = json.loads(json.dumps(old))
    manual["scenarios"][0]["expected"] = {"type": "Bool", "value": True}
    assert reconcile_expected(old, manual)["scenarios"][0]["expected"]["value"] is True


def test_slug() -> None:
    assert slug("FIS-C2-Deducción std") == "fis-c2-deducci-n-std"


@REAL_STACK
def test_verify_fills_missing_expected(store: RuleStore) -> None:
    rule = store.get("EJ-CAT3-CUOTA")
    for s in rule["scenarios"]:
        s.pop("expected")
    store.update("EJ-CAT3-CUOTA", rule)
    report = store.verify("EJ-CAT3-CUOTA")
    assert report["ok"] and report["filled"] == len(rule["scenarios"])
    assert all("expected" in s for s in store.get("EJ-CAT3-CUOTA")["scenarios"])


@REAL_STACK
def test_verify_reports_errors_without_writing(store: RuleStore) -> None:
    rule = store.get("EJ-CAT3-CUOTA")
    rule["canonical_python"] = "def evaluate_rule(data):\n    return True\n"
    store.update("EJ-CAT3-CUOTA", rule)
    report = store.verify("EJ-CAT3-CUOTA")
    assert not report["ok"] and report["filled"] == 0
    assert any("Python canónico" in i["message"] for i in report["issues"])
