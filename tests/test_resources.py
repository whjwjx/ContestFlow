from copy import deepcopy

import pytest

from contestflow import charts, core, project, resources


def custom_palette():
    item = deepcopy(resources.catalog()["resources"][-1])
    item.update(id="palette.team", title="Team palette", status="collected")
    return item


def library(root, *entries):
    core.write_json(
        root / "configs/resource-library.json", {"schema_version": 1, "resources": list(entries)}
    )


def chart_workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    project.init(root)
    evidence = {
        "context_id": "synthetic-example",
        "context": {"definitions": {"metrics": {"score": {"label": "Score", "unit": "1"}}}},
        "rows": [{"experiment": "example", "score": 1}],
    }
    monkeypatch.setattr(charts, "require_evidence", lambda root: evidence)

    def render(root, evidence, metric, kind, palette, output):
        colors = resources.palette_colors(root)[palette]
        for suffix in (".png", ".pdf"):
            output.with_suffix(suffix).write_text(str(colors), encoding="utf-8")

    monkeypatch.setattr(charts, "render", render)
    return root


def test_catalog_is_read_only_and_defaults_stay_small(tmp_path):
    data = resources.catalog(tmp_path)
    assert len(data["resources"]) == 11
    assert not list(tmp_path.iterdir())
    assert resources.selected_resources(tmp_path) == []
    assert resources.selected_checks(tmp_path) == []
    assert list(resources.palette_colors(tmp_path)) == ["journal", "contrast", "mono"]


def test_explicit_selection_orders_palettes_and_drives_checks(tmp_path):
    project.init(tmp_path / "workspace")
    root = tmp_path / "workspace"
    resources.select_resources(root, ["palette.project-p7", "tool.numpy", "palette.project-p6"])
    assert list(resources.palette_colors(root)) == ["project-p7", "project-p6"]
    assert resources.selected_checks(root) == ["plots", "science"]
    assert [item["id"] for item in resources.selected_resources(root)] == [
        "palette.project-p7",
        "tool.numpy",
        "palette.project-p6",
    ]
    resources.select_resources(root, ["tool.numpy"])
    assert list(resources.palette_colors(root)) == ["journal", "contrast", "mono"]
    resources.select_resources(root, [])
    assert resources.selected_checks(root) == []


@pytest.mark.parametrize(
    "change",
    [
        {"id": "palette../escape"},
        {"checks": ["run:arbitrary-command"]},
        {"command": "arbitrary-command"},
        {"colors": ["red"]},
        {"kind": "tool"},
        {"source_url": "file:///private"},
        {"status": "verified-by-team"},
    ],
)
def test_custom_resources_reject_unsafe_or_unrecognized_data(tmp_path, change):
    item = custom_palette()
    item.update(change)
    library(tmp_path, item)
    with pytest.raises(core.FlowError):
        resources.catalog(tmp_path)


def test_duplicate_and_builtin_collision_are_rejected(tmp_path):
    item = custom_palette()
    library(tmp_path, item, item)
    with pytest.raises(core.FlowError, match="Duplicate"):
        resources.catalog(tmp_path)
    item["id"] = "palette.journal"
    library(tmp_path, item)
    with pytest.raises(core.FlowError, match="Duplicate"):
        resources.catalog(tmp_path)


@pytest.mark.parametrize(
    "data",
    [
        {"schema_version": True, "resources": []},
        {"schema_version": 2, "resources": []},
        {"schema_version": 1, "resources": {}},
        {"schema_version": 1, "resources": [None]},
    ],
)
def test_invalid_catalog_schema_is_a_flow_error(tmp_path, data):
    core.write_json(tmp_path / "configs/resource-library.json", data)
    with pytest.raises(core.FlowError):
        resources.catalog(tmp_path)


def test_invalid_selection_does_not_replace_previous_choices(tmp_path):
    root = tmp_path / "workspace"
    project.init(root)
    resources.select_resources(root, ["tool.numpy"])
    before = (root / "configs/resources.json").read_bytes()
    for ids in (["tool.missing"], ["tool.numpy", "tool.numpy"], "tool.numpy", [None]):
        with pytest.raises(core.FlowError):
            resources.select_resources(root, ids)
        assert (root / "configs/resources.json").read_bytes() == before
    core.write_json(root / "deliverables/FROZEN.json", {})
    with pytest.raises(core.FlowError, match="frozen"):
        resources.select_resources(root, [])


def test_custom_palette_changes_invalidate_review_without_overwriting_choice(tmp_path, monkeypatch):
    root = chart_workspace(tmp_path, monkeypatch)
    item = custom_palette()
    library(root, item)
    resources.select_resources(root, [item["id"]])
    charts.charts(root)
    review = charts.review_current(root)
    assert len(review["variants"]) == 2
    assert review["resources"]["definitions"] == [item]
    choice = core.read_json(root / "reviews/selection.json")
    assert choice["choices"] == {"score": "score-bar-team"}
    assert choice["human_review"] == "not_asserted"
    before = (root / "reviews/selection.json").read_bytes()
    item["colors"][0] = "#010203"
    library(root, item)
    with pytest.raises(core.FlowError, match="resources changed"):
        charts.review_current(root)
    charts.charts(root)
    assert (root / "reviews/selection.json").read_bytes() == before
    with pytest.raises(core.FlowError, match="Selection stale"):
        charts.selection_current(root)


def test_font_choice_and_palette_selection_invalidate_existing_review(tmp_path, monkeypatch):
    root = chart_workspace(tmp_path, monkeypatch)
    charts.charts(root)
    assert len(charts.review_current(root)["variants"]) == 6
    cfg = core.config(root)
    cfg["paper"]["cjk_font"] = "Chosen Font"
    core.write_json(root / "contest.json", cfg)
    with pytest.raises(core.FlowError, match="font configuration changed"):
        charts.review_current(root)
    charts.charts(root)
    resources.select_resources(root, ["palette.project-p6"])
    with pytest.raises(core.FlowError, match="resources changed"):
        charts.review_current(root)


def test_legacy_review_without_resource_context_is_stale(tmp_path, monkeypatch):
    root = chart_workspace(tmp_path, monkeypatch)
    charts.charts(root)
    review = core.read_json(root / "reviews/manifest.json")
    del review["resources"]
    del review["review_id"]
    review["review_id"] = core.identity(review)
    core.write_json(root / "reviews/manifest.json", review)
    before = (root / "reviews/selection.json").read_bytes()
    with pytest.raises(core.FlowError, match="resources changed"):
        charts.review_current(root)
    assert (root / "reviews/selection.json").read_bytes() == before


def test_cli_resource_choice_drives_inventory_without_running_probes(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from contestflow import preflight
    from contestflow.cli import main

    root = tmp_path / "比赛 工作区"
    project.init(root)
    assert main(["resources", str(root), "--select", "tool.numpy", "palette.project-p7"]) == 0
    selection = json.loads(capsys.readouterr().out)
    assert selection["selected"] == ["tool.numpy", "palette.project-p7"]
    monkeypatch.setattr(
        preflight,
        "inventory",
        lambda root: {
            "python": sys.version,
            "executable": sys.executable,
            "platform": "test",
            "packages": {"numpy": True, "scipy": True, "matplotlib": True},
            "package_versions": {"numpy": "2.2.0", "scipy": "1.16.0", "matplotlib": "3.10.0"},
            "tools": {},
            "tool_details": {},
        },
    )
    monkeypatch.setattr(preflight, "_probe", lambda *args: pytest.fail("Inventory executed code"))
    before = core.snapshot(root, ["configs", "docs", "contest.json"])
    assert main(["preflight", str(root), "--level", "inventory"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["resources"] == selection["selected"]
    assert {item["id"] for item in report["checks"] if item["required"]} == {
        "core",
        "science",
        "plots",
    }
    assert report["result"] == "not_tested"
    assert report["human_review"] == "not_asserted"
    assert before == core.snapshot(root, ["configs", "docs", "contest.json"])
    assert not (root / ".contestflow.lock").exists()

    assert main(["resources", str(root), "--select"]) == 0
    assert json.loads(capsys.readouterr().out)["selected"] == []
    assert main(["preflight", str(root)]) == 0
    cleared = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in cleared["checks"] if item["required"]] == ["core"]
