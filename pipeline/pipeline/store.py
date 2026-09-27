"""Reglas de `corpus/` para la UI: listar, crear, editar, eliminar y verificar.

Ver specs/ui.md. Cada regla es un archivo JSON; la API agrega al leer `_version`
(hash del archivo) y `_file`, y los quita al escribir. Guardar con una `_version`
vieja da 409: el archivo cambió desde que se abrió (otra persona o un generador de
corpus/tools/). La verificación es la misma de `check-case` (pipeline/corpus.py).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.corpus import check_case, write_expected
from pipeline.orchestrator import DEFAULT_ENGINE_CMD

Rule = dict[str, Any]

INTERNAL = ("_version", "_file")
CASE_ID = re.compile(r"[A-Za-z0-9_\-]{1,120}")


class StoreError(Exception):
    """Error de la petición: lleva el código HTTP que corresponde."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def version_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def slug(case_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", case_id.lower()).strip("-")


def dumps(rule: Rule) -> str:
    """El mismo formato que corpus/tools/dsl.py, así los diffs quedan limpios."""
    clean = {k: v for k, v in rule.items() if k not in INTERNAL}
    return json.dumps(clean, ensure_ascii=False, indent=2) + "\n"


def reconcile_expected(previous: Rule, rule: Rule) -> Rule:
    """Quita los `expected` que ya no valen, para que check-case los recalcule: todos si
    cambió el AST, y el de cada escenario cuyo `env` cambió. Un `expected` editado a
    mano con el mismo AST y el mismo `env` se conserva: si difiere del engine,
    check-case lo marca, y esa diferencia es la que hay que discutir."""
    ast_changed = previous.get("canonical_ast") != rule.get("canonical_ast")
    old_env = {
        s.get("scenario_id"): s.get("env")
        for s in previous.get("scenarios", [])
        if isinstance(s, dict)
    }
    scenarios = []
    for s in rule.get("scenarios", []):
        s = dict(s)
        if ast_changed or old_env.get(s.get("scenario_id")) != s.get("env"):
            s.pop("expected", None)
        scenarios.append(s)
    return {**rule, "scenarios": scenarios}


class RuleStore:
    def __init__(self, root: Path, engine_cmd: Sequence[str] = DEFAULT_ENGINE_CMD) -> None:
        self.root = root
        self.engine_cmd = engine_cmd

    def paths(self) -> dict[str, Path]:
        """`case_id` -> archivo. Los JSON ilegibles o sin `case_id` no son reglas."""
        found: dict[str, Path] = {}
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            case_id = data.get("case_id") if isinstance(data, dict) else None
            if isinstance(case_id, str):
                found.setdefault(case_id, path)
        return found

    def path(self, case_id: str) -> Path:
        path = self.paths().get(case_id)
        if path is None:
            raise StoreError(404, f"no existe la regla {case_id}")
        return path

    @staticmethod
    def read(path: Path) -> Rule:
        text = path.read_text(encoding="utf-8")
        rule: Rule = json.loads(text)
        rule["_version"] = version_of(text)
        rule["_file"] = path.name
        return rule

    def list(self) -> list[Rule]:
        return [self.read(p) for p in self.paths().values()]

    def get(self, case_id: str) -> Rule:
        return self.read(self.path(case_id))

    def create(self, rule: Rule) -> Path:
        case_id = self._case_id(rule)
        if case_id in self.paths():
            raise StoreError(409, f"ya existe la regla {case_id}")
        path = self.root / f"{slug(case_id)}.json"
        if path.exists():
            raise StoreError(409, f"ya existe el archivo {path.name}")
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(rule), encoding="utf-8")
        return path

    def update(self, case_id: str, rule: Rule) -> Path:
        if self._case_id(rule) != case_id:
            raise StoreError(400, "el id de una regla no se puede cambiar")
        path = self.path(case_id)
        self._check_version(path, rule.get("_version"))
        previous = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(dumps(reconcile_expected(previous, rule)), encoding="utf-8")
        return path

    def delete(self, case_id: str, version: str | None) -> None:
        path = self.path(case_id)
        self._check_version(path, version)
        path.unlink()

    def verify(self, case_id: str, *, write: bool = True) -> dict[str, Any]:
        """`check-case` sobre una regla; con `write`, completa los `expected` que faltan."""
        path = self.path(case_id)
        report, data = check_case(path, self.engine_cmd)
        filled = write_expected(path, data, report) if write and report.ok and data is not None else 0
        return {
            "case_id": case_id,
            "ok": report.ok,
            "issues": [{"level": level, "message": msg} for level, msg in report.issues],
            "filled": filled,
        }

    @staticmethod
    def _case_id(rule: Rule) -> str:
        case_id = rule.get("case_id")
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
            raise StoreError(400, "case_id solo admite letras, dígitos, - y _ (hasta 120)")
        return case_id

    @staticmethod
    def _check_version(path: Path, version: object) -> None:
        current = version_of(path.read_text(encoding="utf-8"))
        if version != current:
            raise StoreError(
                409,
                "la regla cambió desde que la abriste (otra persona o un generador de corpus/tools/). "
                "Recargala y volvé a aplicar tus cambios.",
            )
