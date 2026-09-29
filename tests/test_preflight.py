import json
import sys

import pytest

from contestflow import core, preflight, project, release
from contestflow.cli import main


@pytest.fixture
def isolated_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTESTFLOW_USER_CONFIG", str(tmp_path / "user-tools.local.json"))


def environment():
    names = ("pandoc", "xelatex", "git", "nvidia-smi")
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": "test",
        "packages": {name: True for name in preflight.PACKAGES},
        "package_versions": {
            "numpy": "2.2.0",
            "scipy": "1.16.0",
            "matplotlib": "3.10.0",
            "pypdf": "6.0.0",
            "pypandoc": "1.15",
        },
        "tools": {name: "/not/executed/" + name for name in names},
        "tool_details": {
            name: {
                "name": name,
                "path": "/not/executed/" + name,
                "status": "found",
                "source": "fixture",
                "candidates": [],
                "detail": "",
            }
            for name in names
        },
    }


def test_inventory_never_runs_probes_or_creates_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "inventory", lambda root: environment())
    monkeypatch.setattr(preflight, "_probe", lambda *args: pytest.fail("Inventory executed code"))
    before = list(tmp_path.iterdir())
    report = preflight.preflight(profile="full-html")
    assert report["result"] == "not_tested"
    assert report["human_review"] == "not_asserted"
    assert report["submission_readiness"] == "not_assessed"
    assert list(tmp_path.iterdir()) == before


def test_optional_gpu_missing_does_not_fail_core(monkeypatch):
    env = environment()
    env["tool_details"]["nvidia-smi"].update(path=None, status="missing")
    monkeypatch.setattr(preflight, "inventory", lambda root: env)
    report = preflight.preflight(profile="core")
    gpu = next(item for item in report["checks"] if item["id"] == "gpu")
    assert gpu["status"] == "not_needed"
    assert report["result"] == "not_tested"


def test_missing_required_tool_gives_nonzero_exit(monkeypatch, capsys):
    env = environment()
    env["tool_details"]["pandoc"].update(
        path=None, status="invalid", detail="Configured path moved"
    )
    monkeypatch.setattr(preflight, "inventory", lambda root: env)
    assert main(["preflight", "--profile", "documents-html"]) == 1
    report = json.loads(capsys.readouterr().out)
    item = next(item for item in report["checks"] if item["id"] == "documents-html")
    assert item["status"] == "missing"
    assert "Configured path moved" in item["detail"][0]


def test_selected_resource_adds_required_checks(tmp_path, monkeypatch):
    from contestflow import resources

    root = tmp_path / "workspace"
    project.init(root)
    resources.select_resources(root, ["palette.project-p7"])
    monkeypatch.setattr(preflight, "inventory", lambda root: environment())
    report = preflight.preflight(root)
    assert {"core", "science", "plots"} <= {
        item["id"] for item in report["checks"] if item["required"]
    }
    assert report["resources"] == ["palette.project-p7"]


def test_import_failure_blocks_rehearsal_and_keeps_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "inventory", lambda root: environment())
    called = []

    def probe(name, folder, settings):
        called.append(name)
        return {
            "status": "failed" if name == "science" else "passed",
            "detail": "binary import/ABI failure" if name == "science" else {},
        }

    monkeypatch.setattr(preflight, "_probe", probe)
    output = tmp_path / "local-report"
    report = preflight.preflight(level="rehearsal", output=output)
    assert "rehearsal" not in called
    assert report["result"] == "failed"
    assert report["checks"][-1]["status"] == "not_tested"
    assert core.read_json(output / "report.local.json")["result"] == "failed"
    with pytest.raises(core.FlowError, match="new directory"):
        preflight.preflight(output=output)


def test_actual_core_and_archive_probe_in_unicode_directory(tmp_path, isolated_tools):
    root = tmp_path / "比赛 工作区"
    project.init(root)
    before = core.snapshot(root, ["contest.json", "configs", "src", "paper", "docs"])
    report = preflight.preflight(
        root, profile="delivery", level="functional", output=tmp_path / "检查 结果"
    )
    assert report["result"] == "passed"
    assert (tmp_path / "检查 结果/delivery/sample.zip").is_file()
    assert report["human_review"] == "not_asserted"
    assert before == core.snapshot(root, ["contest.json", "configs", "src", "paper", "docs"])


def test_frozen_workspace_stays_readonly(tmp_path, isolated_tools):
    root = tmp_path / "workspace"
    project.init(root)
    core.write_json(root / "deliverables/FROZEN.json", {})
    with pytest.raises(core.FlowError, match="frozen"):
        preflight.preflight(root, output=root / ".contestflow/new-report")
    report = preflight.preflight(root, level="functional")
    core_check = next(item for item in report["checks"] if item["id"] == "core")
    assert core_check["detail"]["workspace_write"] == "not_needed_frozen"
    assert not (root / ".contestflow").exists()


def test_private_preflight_artifacts_cannot_be_packaged(tmp_path):
    root = tmp_path / "workspace"
    project.init(root)
    core.write_text(root / ".contestflow/preflight/probe.log", "local installation path")
    cfg = core.config(root)
    cfg["package"]["include"] = [".contestflow"]
    core.write_json(root / "contest.json", cfg)
    with pytest.raises(core.FlowError, match="Private"):
        release.publication_files(root)


def test_saved_profile_and_bad_schema(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    project.init(root)
    monkeypatch.setattr(preflight, "inventory", lambda root: environment())
    core.write_json(root / "configs/preflight.json", {"schema_version": 1, "profile": "gpu"})
    assert preflight.preflight(root)["profile"] == "gpu"
    core.write_json(root / "configs/preflight.json", {"schema_version": 7})
    with pytest.raises(core.FlowError, match="schema_version"):
        preflight.preflight(root)


def test_probe_timeout_terminates_process_tree(tmp_path, monkeypatch):
    class Process:
        returncode = 1
        calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise preflight.subprocess.TimeoutExpired("probe", timeout)
            return "", "terminated"

    process = Process()
    killed = []
    monkeypatch.setattr(preflight.subprocess, "Popen", lambda *a, **k: process)
    from contestflow import runner

    monkeypatch.setattr(runner, "kill_tree", lambda item: killed.append(item))
    result = preflight._probe("science", tmp_path / "probe", {})
    assert killed == [process]
    assert result["status"] == "failed"
    assert "Timed out" in result["detail"]


def test_invalid_level_and_profile_fail_before_execution():
    with pytest.raises(core.FlowError):
        preflight.preflight(level="unbounded")
    with pytest.raises(core.FlowError):
        preflight.preflight(profile=["core"])


def test_cli_search_directory_and_resource_selection(tmp_path, isolated_tools, monkeypatch, capsys):
    from contestflow import toolchain

    root = tmp_path / "workspace"
    project.init(root)
    search = tmp_path / "Tools 中文"
    search.mkdir()
    assert main(["tools", str(root), "--search-dir", str(search)]) == 0
    capsys.readouterr()
    assert toolchain.load_settings(root)["search_dirs"] == [str(search.resolve())]
    assert main(["resources", str(root), "--select", "palette.project-p7"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(preflight, "inventory", lambda root: environment())
    assert main(["preflight", str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["resources"] == ["palette.project-p7"]
    assert next(item for item in report["checks"] if item["id"] == "plots")["required"]


def test_pypandoc_binary_distribution_version_is_recorded(monkeypatch):
    original = preflight.importlib.metadata.version

    def version(name):
        if name == "pypandoc":
            raise preflight.importlib.metadata.PackageNotFoundError(name)
        if name == "pypandoc_binary":
            return "1.17"
        return original(name)

    monkeypatch.setattr(preflight.importlib.metadata, "version", version)
    monkeypatch.setattr(preflight, "discover_tool", lambda name, root: {"path": None})
    assert preflight.inventory()["package_versions"]["pypandoc"] == "1.17"


def test_cli_json_is_utf8_under_legacy_pipe_encoding(tmp_path):
    import os
    import subprocess

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "ascii"
    result = subprocess.run(
        [sys.executable, "-m", "contestflow", "resources"], env=env, capture_output=True, check=True
    )
    report = json.loads(result.stdout.decode("utf-8"))
    assert any(any(ord(char) > 127 for char in item["title"]) for item in report["resources"])
