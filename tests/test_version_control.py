import json
import shutil
import subprocess

import pytest

from contestflow import core, project, runner, version_control
from contestflow.cli import main

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")


def git(root, *args):
    return subprocess.run(
        [shutil.which("git"), "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_local_mode_initializes_the_exact_workspace_and_keeps_private_data_ignored(tmp_path):
    root = tmp_path / "contest"
    result = project.init(root, "Test", git_mode="local")

    state = result["repository"]
    assert state["status"] == "ready"
    assert state["root_matches"] is True
    assert state["repository_root"] == str(root.resolve())
    assert state["mode"] == "local"
    assert state["branch"] == "main"
    assert state["head"] is None
    assert state["dirty"] is True

    private_paths = [
        "materials/private.txt",
        "data/raw/private.csv",
        "runs/run/log.txt",
        "reviews/review.json",
        "deliverables/candidate.zip",
        "tools.local.json",
        ".contestflow/report.local.json",
    ]
    for relative in private_paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private", encoding="utf-8")

    listed = git(root, "status", "--porcelain", "--untracked-files=all").stdout
    assert "contest.json" in listed
    for relative in private_paths:
        assert relative not in listed


def test_nested_repository_is_rejected_without_changing_workspace_policy(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    git(parent, "init", "--initial-branch=main")
    root = parent / "new" / "contest"
    project.init(root)

    with pytest.raises(core.FlowError, match="inside a different Git repository"):
        version_control.enable(root, "local")

    assert not (root / ".git").exists()
    assert version_control.policy(root)["mode"] == "off"


def test_git_precheck_does_not_leave_partial_new_workspace(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    git(parent, "init", "--initial-branch=main")
    root = parent / "contest"

    with pytest.raises(core.FlowError, match="inside a different Git repository"):
        project.init(root, git_mode="local")

    assert not root.exists()


def test_missing_git_does_not_leave_partial_new_workspace(tmp_path, monkeypatch):
    root = tmp_path / "contest"

    def missing(*_args, **_kwargs):
        raise core.FlowError("git unavailable")

    monkeypatch.setattr(version_control, "resolve_tool", missing)
    with pytest.raises(core.FlowError, match="git unavailable"):
        project.init(root, git_mode="local")

    assert not root.exists()


def test_team_mode_reports_remote_name_without_exposing_remote_url(tmp_path):
    root = tmp_path / "contest"
    project.init(root, git_mode="team")
    remote_url = "https://example.invalid/private-team-repository.git"
    git(root, "remote", "add", "origin", remote_url)

    state = version_control.inspect(root)
    assert state["push_policy"] == "task-branches"
    assert state["task_branch_pattern"] == "agent/<member>/<goal>"
    assert state["remotes"] == ["origin"]
    assert remote_url not in json.dumps(state)


def test_team_task_branch_can_be_pushed_without_publishing_protected_branches(tmp_path):
    root = tmp_path / "contest"
    remote = tmp_path / "team.git"
    project.init(root, git_mode="team")
    git(root, "config", "user.name", "ContestFlow Test")
    git(root, "config", "user.email", "contestflow@example.invalid")
    git(root, "switch", "-c", "agent/alice/baseline")
    git(
        root,
        "add",
        "--",
        ".gitignore",
        "AGENTS.md",
        "contest.json",
        "configs",
        "docs",
        "evidence",
        "paper",
        "plans",
    )
    git(root, "commit", "-m", "chore: establish contest workspace")
    subprocess.run(
        [shutil.which("git"), "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "agent/alice/baseline")

    refs = subprocess.run(
        [
            shutil.which("git"),
            "--git-dir",
            str(remote),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    assert refs == ["agent/alice/baseline"]
    state = version_control.inspect(root)
    assert state["branch"] == "agent/alice/baseline"
    assert state["head"]
    assert state["dirty"] is False


def test_disable_leaves_repository_and_turns_off_agent_git_actions(tmp_path):
    root = tmp_path / "contest"
    project.init(root, git_mode="local")

    state = version_control.disable(root)

    assert (root / ".git").is_dir()
    assert state["status"] == "disabled"
    assert state["commit_policy"] == "none"
    assert state["push_policy"] == "none"


def test_cli_start_can_enable_and_explicitly_disable_git_mode(tmp_path, capsys):
    material = tmp_path / "problem.md"
    material.write_text("# Problem", encoding="utf-8")
    root = tmp_path / "contest"

    assert (
        main(
            [
                "start",
                str(root),
                "--materials",
                str(material),
                "--git-mode",
                "local",
            ]
        )
        == 0
    )
    enabled = json.loads(capsys.readouterr().out)
    assert enabled["repository"]["status"] == "ready"
    assert enabled["repository"]["mode"] == "local"

    assert (
        main(
            [
                "start",
                str(root),
                "--materials",
                str(material),
                "--git-mode",
                "off",
            ]
        )
        == 0
    )
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["repository"]["status"] == "disabled"
    assert (root / ".git").is_dir()


def test_run_record_includes_path_free_repository_provenance(tmp_path):
    root = tmp_path / "contest"
    project.init(root, git_mode="local")
    core.write_text(
        root / "src/solve.py",
        "import json,sys\nfrom pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps({'valid':True,'metrics':{'score':2}}))\n",
    )
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

    record = runner.run(root, allow_exec=True)[0]

    assert record["repository"] == {
        "mode": "local",
        "status": "ready",
        "branch": "main",
        "head": None,
        "dirty": True,
        "root_matches": True,
    }
    assert str(root) not in json.dumps(record["repository"])
