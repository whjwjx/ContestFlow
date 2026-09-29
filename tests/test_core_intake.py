import json
import zipfile

import pytest

from contestflow import core, intake, project
from contestflow.cli import main


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    project.init(root, "Test")
    return root


@pytest.mark.parametrize(
    "value", ["../escape", "/absolute", "a/../b", "C:/secret", "a\\b", "a//b", "./file"]
)
def test_reject_unsafe_paths(workspace, value):
    with pytest.raises(core.FlowError):
        core.local(workspace, value)


def test_no_overwrite_existing(tmp_path):
    path = tmp_path / "existing"
    path.mkdir()
    (path / "keep.txt").write_text("keep")
    with pytest.raises(core.FlowError):
        project.init(path)
    assert (path / "keep.txt").read_text() == "keep"


def test_workspace_lock(workspace):
    with core.workspace_lock(workspace):
        with pytest.raises(core.FlowError):
            with core.workspace_lock(workspace):
                pass
    assert not (workspace / ".contestflow.lock").exists()


def test_unicode_materials_and_dedup(workspace, tmp_path):
    source = tmp_path / "题目.md"
    source.write_text("# 任务\n比较实验结果。", encoding="utf-8")
    first = intake.intake(workspace, source)
    second = intake.intake(workspace, source)
    assert len(first["files"]) == len(second["files"]) == 1
    assert project.next_task(workspace)["stage"] == "analysis"
    stored = workspace / first["files"][0]["stored"]
    assert stored.read_bytes() == source.read_bytes()
    stored.write_text("tamper")
    with pytest.raises(core.FlowError):
        intake.intake(workspace, source)


def test_prevent_recursive_import(workspace):
    with pytest.raises(core.FlowError):
        intake.intake(workspace, workspace.parent)


def test_docx_picture_and_table_text(workspace, tmp_path):
    source = tmp_path / "problem.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Question</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>42</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>',
        )
        archive.writestr("word/media/image1.png", b"test-image")
    record = intake.intake(workspace, source)["files"][0]
    assert record["images"] == ["image1.png"]
    assert "42" in (workspace / record["extraction"] / "text.md").read_text()
    assert record["visual_review_required"]


def test_zip_inventory_never_extracts(workspace, tmp_path):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape.py", "raise Exception()")
    record = intake.intake(workspace, path)["files"][0]
    assert record["status"] == "inventory_only"
    assert not (workspace / "escape.py").exists()


def test_csv_profile(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("x,y\n1,\n2,3\n", encoding="utf-8")
    profile = intake.inspect_csv(path)
    assert profile["sample_rows"] == 2
    assert profile["missing"]["y"] == 1


def test_frozen_stops_import(workspace, tmp_path):
    core.write_json(workspace / "deliverables/FROZEN.json", {})
    path = tmp_path / "data.txt"
    path.write_text("text")
    with pytest.raises(core.FlowError):
        intake.intake(workspace, path)


def test_cli_start_does_not_invent_solution(tmp_path, capsys):
    source = tmp_path / "statement.md"
    source.write_text("# A new problem\nFind a model for the attached measurements.\n")
    root = tmp_path / "contest"
    assert main(["start", str(root), "--materials", str(source)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["next"]["stage"] == "analysis"
    assert data["next"]["collaboration_mode"] == "team_led"
    assert data["next"]["guidance_only"] is True
    assert data["next"]["agent_execution"] == "proactive_within_scope"
    assert data["next"]["continue_when_unblocked"] is True
    assert data["next"]["human_review"] == "not_asserted"
    assert data["next"]["team_focus"]
    assert core.read_json(root / "plans/requirements.json")["items"] == []
    before = core.snapshot(root, ["src", "configs", "paper", "plans", "docs", "contest.json"])
    assert main(["next", str(root)]) == 0
    capsys.readouterr()
    assert main(["status", str(root)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["human_review"] == "not_asserted"
    assert status["platform_submission"] == "not_observed"
    assert before == core.snapshot(
        root, ["src", "configs", "paper", "plans", "docs", "contest.json"]
    )
    assert main(["run", str(root)]) == 2


def test_refresh_guidance_preserves_existing_team_records(workspace):
    entry = workspace / "AGENTS.md"
    decisions = workspace / "docs/DECISIONS.md"
    core.write_text(entry, "Existing team-specific instructions.\n")
    core.write_text(decisions, "Team feedback: compare the baseline before choosing a model.\n")
    before = core.snapshot(workspace, ["AGENTS.md", "docs/DECISIONS.md"])
    step = project.plan(workspace)
    assert before == core.snapshot(workspace, ["AGENTS.md", "docs/DECISIONS.md"])
    assert core.read_json(workspace / "plans/current.json")["team_focus"] == step["team_focus"]
    assert step["human_review"] == "not_asserted"
    task = (workspace / "docs/AI_TASK.md").read_text(encoding="utf-8")
    assert "Agent 工作闭环" in task
    assert "不停在列计划或报告状态" in task
