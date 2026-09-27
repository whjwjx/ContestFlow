import pytest

from contestflow import core, evidence, project, runner


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "runner"
    project.init(root)
    script = "import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({'valid':True,'metrics':{'score':2}}))\n"
    core.write_text(root / "src/solve.py", script)
    core.write_json(
        root / "configs/experiments.json",
        {
            "schema_version": 1,
            "experiments": [
                {
                    "id": "baseline",
                    "command": ["{python}", "{workspace}/src/solve.py", "{run_dir}/result.json"],
                    "inputs": ["src"],
                    "outputs": ["result.json"],
                    "timeout_seconds": 10,
                }
            ],
        },
    )
    core.write_json(
        root / "evidence/metrics.json",
        {
            "schema_version": 1,
            "metrics": {
                "score": {
                    "label": "Score",
                    "unit": "points",
                    "direction": "max",
                    "definition": "Fixture score",
                    "aggregation": "One instance",
                }
            },
        },
    )
    return root


def test_explicit_execution_permission(workspace):
    with pytest.raises(core.FlowError):
        runner.run(workspace)


def test_resume_then_invalidate_source(workspace):
    first = runner.run(workspace, True)[0]
    second = runner.run(workspace, True)[0]
    assert first["status"] == "success"
    assert second["reused"] and first["attempt"] == second["attempt"]
    with (workspace / "src/solve.py").open("a") as stream:
        stream.write("\n# updated\n")
    assert runner.current_runs(workspace)[0]["status"] == "stale"
    third = runner.run(workspace, True)[0]
    assert third["status"] == "success" and third["attempt"] != first["attempt"]


def test_tampered_result_not_reused(workspace):
    first = runner.run(workspace, True)[0]
    core.write_json(workspace / first["result"], {"valid": True, "metrics": {"score": 999}})
    assert runner.current_runs(workspace)[0]["status"] == "stale"
    assert runner.run(workspace, True)[0]["attempt"] != first["attempt"]


def test_timeout_is_recorded(workspace):
    core.write_text(workspace / "src/solve.py", "import time\ntime.sleep(10)\n")
    spec = core.read_json(workspace / "configs/experiments.json")
    spec["experiments"][0]["timeout_seconds"] = 0.1
    core.write_json(workspace / "configs/experiments.json", spec)
    assert runner.run(workspace, True)[0]["status"] == "timeout"
    compared = evidence.compare(workspace)
    assert not compared["complete"]
    assert compared["rows"][0]["status"] == "timeout"
    assert "score" not in compared["rows"][0]


def test_invalid_solution_not_success(workspace):
    text = (workspace / "src/solve.py").read_text().replace("'valid':True", "'valid':False")
    core.write_text(workspace / "src/solve.py", text)
    record = runner.run(workspace, True)[0]
    assert record["status"] == "error"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "4", None])
def test_nonfinite_or_nonnumeric_rejected(value):
    with pytest.raises(core.FlowError):
        runner.result_valid({"valid": True, "metrics": {"score": value}})


def test_evidence_dependency_changes(workspace):
    runner.run(workspace, True)
    evidence.compare(workspace)
    assert evidence.evidence_current(workspace)
    definitions = core.read_json(workspace / "evidence/metrics.json")
    definitions["metrics"]["score"]["unit"] = "different units"
    core.write_json(workspace / "evidence/metrics.json", definitions)
    assert not evidence.evidence_current(workspace)
    evidence.compare(workspace)
    with (workspace / "evidence/comparison.csv").open("a") as stream:
        stream.write("corrupt\n")
    assert not evidence.evidence_current(workspace)


def test_duplicate_experiment_rejected(workspace):
    cfg = core.read_json(workspace / "configs/experiments.json")
    cfg["experiments"].append(cfg["experiments"][0])
    core.write_json(workspace / "configs/experiments.json", cfg)
    with pytest.raises(core.FlowError):
        runner.run(workspace, True)


def test_edited_json_rows_rejected(workspace):
    runner.run(workspace, True)
    evidence.compare(workspace)
    table = core.read_json(workspace / "evidence/comparison.json")
    table["rows"][0]["score"] = 999
    core.write_json(workspace / "evidence/comparison.json", table)
    assert not evidence.evidence_current(workspace)


def test_rehashed_csv_still_must_match_runs(workspace):
    runner.run(workspace, True)
    evidence.compare(workspace)
    path = workspace / "evidence/comparison.csv"
    core.write_text(path, "changed data\n")
    table = core.read_json(workspace / "evidence/comparison.json")
    table["table_sha256"] = core.digest(path)
    core.write_json(workspace / "evidence/comparison.json", table)
    assert not evidence.evidence_current(workspace)


def test_unknown_metric_is_not_silently_dropped(workspace):
    runner.run(workspace, True)
    defs = core.read_json(workspace / "evidence/metrics.json")
    defs["metrics"]["extra"] = defs["metrics"]["score"]
    core.write_json(workspace / "evidence/metrics.json", defs)
    with pytest.raises(core.FlowError):
        evidence.compare(workspace)
