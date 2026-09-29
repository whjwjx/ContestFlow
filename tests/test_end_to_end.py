import importlib.util

import pytest

from contestflow import charts, core, evidence, examples, project, release, reporting, runner

pytestmark = pytest.mark.skipif(
    any(importlib.util.find_spec(x) is None for x in ("numpy", "scipy", "matplotlib", "pypandoc")),
    reason="Install science and documents extras for end-to-end tests",
)


@pytest.mark.parametrize("kind", ["assignment", "forecast"])
def test_full_workflow_and_freeze(tmp_path, kind):
    root = tmp_path / kind
    project.init(root)
    examples.seed_example(root, kind)
    cfg = core.config(root)
    cfg["package"]["require_pdf"] = False
    core.write_json(root / "contest.json", cfg)
    records = runner.run(root, True)
    assert all(r["status"] == "success" for r in records)
    compared = evidence.compare(root)
    metric = "cost" if kind == "assignment" else "rmse"
    values = {r["experiment"]: r[metric] for r in compared["rows"]}
    assert values["improved"] < values["baseline"]
    charts.charts(root)
    selected = core.read_json(root / "reviews/selection.json")
    selected["table_style"] = "striped"
    selected["choices"][metric] = metric + "-dot-contrast"
    charts.apply_selection(root, selected, "test-fixture")
    assert charts.selection_current(root)["human_review"] == "not_asserted"
    current = core.read_json(root / "reviews/selection.json")
    core.write_json(root / "reviews/selection.json", {**current, "artifacts": {}})
    with pytest.raises(core.FlowError):
        charts.selection_current(root)
    core.write_json(root / "reviews/selection.json", current)
    with pytest.raises(core.FlowError):
        charts.apply_selection(root, {**selected, "review_id": "stale"})
    reporting.build_paper(root, "html")
    assert reporting.paper_current(root)
    assert "{{metric:" not in (root / "paper/build/resolved.md").read_text()
    assert project.next_task(root)["stage"] == "delivery"
    assert project.status(root)["human_review"] == "not_asserted"
    candidate = release.package(root)
    with pytest.raises(core.FlowError):
        release.freeze(root, True)
    report = release.verify(root, smoke=True, allow_exec=True)
    assert report["smoke"]["status"] == "passed"
    frozen = release.freeze(root, True)
    assert frozen["human_review"] == "not_asserted"
    assert project.next_task(root)["stage"] == "frozen"
    assert project.next_task(root)["guidance_only"] is True
    assert project.status(root)["human_review"] == "not_asserted"
    assert project.status(root)["platform_submission"] == "not_observed"
    with pytest.raises(core.FlowError):
        reporting.build_paper(root, "html")
    assert release.verify(root)["archive_sha256"] == candidate["sha256"]
    with (root / "src/solver.py").open("a") as stream:
        stream.write("\n# changed after freeze\n")
    with pytest.raises(core.FlowError):
        release.verify(root)
