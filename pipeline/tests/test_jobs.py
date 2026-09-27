from __future__ import annotations

import json
import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from pipeline.jobs import Command, Job, RunManager
from pipeline.store import RuleStore, StoreError

EXAMPLES = Path(__file__).parent / "data" / "corpus"

# Corrida falsa: imprime el log, escribe un registro por escenario de la primera regla
# y, si se pide, se queda esperando (para probar la cancelación).
FAKE_RUN = """
import json, sys, time
cases, out, run_id, wait = sys.argv[1].split(","), sys.argv[2], sys.argv[3], float(sys.argv[4])
print(f"run_id={run_id}: {len(cases)} casos", flush=True)
rule = json.load(open(cases[0], encoding="utf-8"))
with open(f"{out}/{run_id}.jsonl", "w", encoding="utf-8") as f:
    for group in ("treatment", "baseline1"):
        for s in rule["scenarios"]:
            f.write(json.dumps({"run_id": run_id, "case_id": rule["case_id"], "group": group,
                                "scenario_id": s["scenario_id"], "outcome": "executed"}) + "\\n")
time.sleep(wait)
print("listo", flush=True)
"""


def fake_command(wait: float = 0.0) -> Command:
    def command(cases: Sequence[Path], repetitions: int, run_id: str, out: Path) -> list[str]:
        return [sys.executable, "-c", FAKE_RUN, ",".join(map(str, cases)), str(out), run_id, str(wait)]

    return command


@pytest.fixture()
def corpus(tmp_path: Path) -> RuleStore:
    root = tmp_path / "corpus"
    root.mkdir()
    for p in EXAMPLES.glob("*.json"):
        shutil.copy(p, root / p.name)
    return RuleStore(root)


def manager(tmp_path: Path, store: RuleStore, wait: float = 0.0) -> RunManager:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "rule-001.json").write_text("{}", encoding="utf-8")
    return RunManager(tmp_path / "out", store, fixtures, command=fake_command(wait), cwd=tmp_path)


def wait_for(job: Job, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while job.status == "running" and time.monotonic() < deadline:
        time.sleep(0.05)


def test_estimate_counts_three_calls_per_case_and_repetition(tmp_path: Path, corpus: RuleStore) -> None:
    runs = manager(tmp_path, corpus)
    assert runs.estimate({"source": "corpus", "repetitions": 2}) == {"cases": 3, "repetitions": 2, "calls": 18}
    assert runs.estimate({"source": "corpus", "case_ids": ["EJ-CAT1-RIESGO"]})["calls"] == 3
    assert runs.estimate({"source": "fixtures"})["cases"] == 1


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ({"source": "otro"}, "source"),
        ({"source": "corpus", "repetitions": 0}, "repetitions"),
        ({"source": "corpus", "repetitions": True}, "repetitions"),
        ({"source": "corpus", "case_ids": ["NO-EXISTE"]}, "no existen"),
    ],
)
def test_estimate_rejects_bad_selections(tmp_path: Path, corpus: RuleStore, selection: dict[str, object], message: str) -> None:
    with pytest.raises(StoreError, match=message):
        manager(tmp_path, corpus).estimate(selection)


def test_start_requires_confirming_the_exact_number_of_calls(tmp_path: Path, corpus: RuleStore) -> None:
    runs = manager(tmp_path, corpus)
    with pytest.raises(StoreError, match="9 llamadas") as exc:
        runs.start({"source": "corpus"}, confirm_calls=None)
    assert exc.value.status == 409
    with pytest.raises(StoreError):
        runs.start({"source": "corpus"}, confirm_calls=3)
    assert not runs.jobs


def test_run_writes_log_and_records_with_expected(tmp_path: Path, corpus: RuleStore) -> None:
    runs = manager(tmp_path, corpus)
    job = runs.start({"source": "corpus", "case_ids": ["EJ-CAT3-CUOTA"]}, confirm_calls=3)
    wait_for(job)
    assert job.status == "finished" and job.returncode == 0

    log = runs.log(job.run_id)
    assert "1 casos" in log["text"] and "listo" in log["text"] and log["status"] == "finished"
    assert runs.log(job.run_id, offset=log["offset"])["text"] == ""  # lectura incremental

    rows = runs.records(job.run_id, {"group": "treatment"})
    rule = corpus.get("EJ-CAT3-CUOTA")
    assert [r["scenario_id"] for r in rows] == [s["scenario_id"] for s in rule["scenarios"]]
    assert rows[0]["expected"] == rule["scenarios"][0]["expected"]

    listed = runs.list_runs()
    assert listed[0]["run_id"] == job.run_id and listed[0]["records"] == 2 * len(rule["scenarios"])
    assert listed[0]["job"]["status"] == "finished"


def test_only_one_run_at_a_time_and_cancel(tmp_path: Path, corpus: RuleStore) -> None:
    runs = manager(tmp_path, corpus, wait=30)
    job = runs.start({"source": "corpus"}, confirm_calls=9)
    with pytest.raises(StoreError, match="en curso"):
        runs.start({"source": "corpus"}, confirm_calls=9)
    assert runs.active() is job
    runs.cancel(job.run_id)
    wait_for(job)
    assert job.status == "cancelled" and runs.active() is None
    with pytest.raises(StoreError):
        runs.cancel(job.run_id)


def test_run_ids_cannot_escape_out(tmp_path: Path, corpus: RuleStore) -> None:
    runs = manager(tmp_path, corpus)
    for bad in ("../secreto", "a/b", ""):
        with pytest.raises(StoreError) as exc:
            runs.records(bad, {})
        assert exc.value.status == 400


def test_records_of_unknown_run(tmp_path: Path, corpus: RuleStore) -> None:
    with pytest.raises(StoreError) as exc:
        manager(tmp_path, corpus).records("20260101T000000Z-abcdef", {})
    assert exc.value.status == 404


def test_default_command_is_the_cli(tmp_path: Path) -> None:
    from pipeline.jobs import pipeline_command

    cmd = pipeline_command([tmp_path / "a.json"], 2, "r1", tmp_path)
    assert cmd[1:4] == ["-m", "pipeline", "run"] and "--repetitions" in cmd and "r1" in cmd
    assert json.dumps(cmd)  # todo texto: se puede registrar tal cual
