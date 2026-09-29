import json
import os
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from contestflow import core, project, reporting, toolchain


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTESTFLOW_USER_CONFIG", str(tmp_path / "user/tools.local.json"))
    monkeypatch.setenv("PATH", "")
    for variable in toolchain.ENVIRONMENT.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(toolchain.sys, "executable", str(tmp_path / "python/python.exe"))
    monkeypatch.setattr(toolchain, "_known_directories", lambda name: [])
    monkeypatch.setattr(toolchain, "_registered_candidates", lambda name: [])
    monkeypatch.setattr(toolchain, "_bundled_pandoc_dirs", lambda: [])
    root = tmp_path / "workspace"
    project.init(root)
    return root


def executable(directory, name="pandoc", content="fake binary"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".exe" if os.name == "nt" else name)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path.resolve()


def test_nondefault_unicode_space_path_shared_with_builder(isolated, tmp_path):
    path = executable(tmp_path / "科研 工具目录")
    original = (isolated / "contest.json").read_bytes()
    toolchain.configure(isolated, "pandoc", str(path))
    found = toolchain.discover_tool("pandoc", isolated)
    assert found["status"] == "found"
    assert found["source"] == "workspace-config"
    assert reporting.pandoc_path(isolated) == str(path)
    assert (isolated / "contest.json").read_bytes() == original
    assert "*.local.json" in (isolated / ".gitignore").read_text()


def test_explicit_precedence_and_unset(isolated, tmp_path, monkeypatch):
    user = executable(tmp_path / "user-bin")
    workspace = executable(tmp_path / "workspace-bin")
    environment = executable(tmp_path / "env-bin")
    monkeypatch.setenv("PANDOC", str(environment))
    toolchain.configure(tool="pandoc", path=str(user))
    assert toolchain.resolve_tool("pandoc", isolated) == str(user)
    toolchain.configure(isolated, "pandoc", str(workspace))
    assert toolchain.resolve_tool("pandoc", isolated) == str(workspace)
    toolchain.configure(isolated, unset="pandoc")
    assert toolchain.resolve_tool("pandoc", isolated) == str(user)
    toolchain.configure(unset="pandoc")
    assert toolchain.resolve_tool("pandoc", isolated) == str(environment)


def test_stale_explicit_path_does_not_fall_back(isolated, tmp_path, monkeypatch):
    path = executable(tmp_path / "configured")
    fallback = executable(tmp_path / "path")
    toolchain.configure(isolated, "pandoc", str(path))
    path.unlink()
    monkeypatch.setenv("PATH", str(fallback.parent))
    found = toolchain.discover_tool("pandoc", isolated)
    assert found["status"] == "invalid"
    assert found["path"] is None
    assert found["source"] == "workspace-config"
    with pytest.raises(core.FlowError, match="invalid"):
        reporting.pandoc_path(isolated)


def test_invalid_environment_does_not_fall_back(isolated, tmp_path, monkeypatch):
    fallback = executable(tmp_path / "path")
    monkeypatch.setenv("PATH", str(fallback.parent))
    monkeypatch.setenv("PANDOC", "relative/pandoc")
    assert toolchain.discover_tool("pandoc", isolated)["status"] == "invalid"


def test_search_is_shallow_and_reports_ambiguity(isolated, tmp_path):
    directory = tmp_path / "custom tools"
    a = executable(directory / "bin")
    b = executable(directory / "Scripts")
    executable(directory / "deep/nested/bin", "xelatex")
    toolchain.configure(isolated, search_dir=str(directory))
    found = toolchain.discover_tool("pandoc", isolated)
    assert found["status"] == "ambiguous"
    assert {candidate["path"] for candidate in found["candidates"]} == {str(a), str(b)}
    assert toolchain.discover_tool("xelatex", isolated)["status"] == "missing"
    with pytest.raises(core.FlowError, match="Candidates"):
        toolchain.resolve_tool("pandoc", isolated)


def test_known_locations_and_user_search_have_same_priority(isolated, tmp_path, monkeypatch):
    a = executable(tmp_path / "known")
    b = executable(tmp_path / "extra")
    monkeypatch.setattr(toolchain, "_known_directories", lambda name: [a.parent])
    toolchain.configure(isolated, search_dir=str(b.parent))
    assert toolchain.discover_tool("pandoc", isolated)["status"] == "ambiguous"


def test_path_order_and_environment_directory_priority(isolated, tmp_path, monkeypatch):
    first = executable(tmp_path / "first")
    second = executable(tmp_path / "second")
    monkeypatch.setenv("PATH", os.pathsep.join([str(first.parent), str(second.parent)]))
    assert toolchain.resolve_tool("pandoc", isolated) == str(first)
    local = executable(tmp_path / "venv/Scripts")
    monkeypatch.setattr(toolchain.sys, "executable", str(local.parent / "python.exe"))
    assert toolchain.resolve_tool("pandoc", isolated) == str(local)
    assert toolchain.discover_tool("pandoc", isolated)["source"] == "python-environment"


def test_bundled_pandoc_discovered_without_import_or_execution(isolated, tmp_path, monkeypatch):
    package = tmp_path / "site-packages/pypandoc"
    bundled = executable(package / "files")
    monkeypatch.undo()
    monkeypatch.setenv("CONTESTFLOW_USER_CONFIG", str(tmp_path / "user/tools.local.json"))
    monkeypatch.setenv("PATH", "")
    for variable in toolchain.ENVIRONMENT.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(toolchain.sys, "executable", str(tmp_path / "empty/python.exe"))
    monkeypatch.setattr(
        toolchain.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(submodule_search_locations=[str(package)]),
    )
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: pytest.fail("discovery executed a candidate")
    )
    found = toolchain.discover_tool("pandoc", isolated)
    assert found["path"] == str(bundled)
    assert found["source"] == "pypandoc-bundled"


@pytest.mark.parametrize(
    "settings",
    [
        [],
        {"schema_version": True},
        {"schema_version": 2},
        {"schema_version": 1, "typo": {}},
        {"schema_version": 1, "tools": []},
        {"schema_version": 1, "tools": {"unknown": "/tool"}},
        {"schema_version": 1, "tools": {"pandoc": "relative"}},
        {"schema_version": 1, "search_dirs": "a-directory"},
        {"schema_version": 1, "search_dirs": [12]},
    ],
)
def test_bad_settings_block_without_rewriting(isolated, settings):
    path = isolated / toolchain.CONFIG_NAME
    core.write_json(path, settings)
    before = path.read_bytes()
    assert toolchain.discover_tool("pandoc", isolated)["status"] == "invalid"
    with pytest.raises(core.FlowError):
        toolchain.configure(isolated, unset="pandoc")
    assert path.read_bytes() == before


def test_configuration_preserves_other_tools_and_searches(isolated, tmp_path):
    pandoc = executable(tmp_path / "pandoc-bin")
    git = executable(tmp_path / "git-bin", "git")
    directory = tmp_path / "search"
    directory.mkdir()
    toolchain.configure(tool="git", path=str(git), search_dir=str(directory))
    toolchain.configure(isolated, "pandoc", str(pandoc))
    loaded = toolchain.load_settings(isolated)
    assert loaded == {
        "schema_version": 1,
        "tools": {"git": str(git), "pandoc": str(pandoc)},
        "search_dirs": [str(directory.resolve())],
    }
    assert toolchain.configure(isolated)["written"] is False


def test_configure_requires_real_absolute_paths(isolated, tmp_path):
    with pytest.raises(core.FlowError):
        toolchain.configure(isolated, tool="pandoc", path="relative")
    with pytest.raises(core.FlowError):
        toolchain.configure(isolated, tool="pandoc", path=str(tmp_path))
    with pytest.raises(core.FlowError):
        toolchain.configure(isolated, search_dir=str(tmp_path / "missing"))
    with pytest.raises(core.FlowError):
        toolchain.configure(isolated, tool="pandoc")
    assert not (isolated / toolchain.CONFIG_NAME).exists()


def test_frozen_workspace_rejects_changes_but_allows_reading(isolated, tmp_path):
    path = executable(tmp_path / "tools")
    toolchain.configure(isolated, "pandoc", str(path))
    core.write_json(isolated / "deliverables/FROZEN.json", {})
    before = (isolated / toolchain.CONFIG_NAME).read_bytes()
    with pytest.raises(core.FlowError, match="frozen"):
        toolchain.configure(isolated, unset="pandoc")
    assert toolchain.resolve_tool("pandoc", isolated) == str(path)
    assert (isolated / toolchain.CONFIG_NAME).read_bytes() == before


def test_tool_change_invalidates_paper_without_exporting_paths(isolated, tmp_path, monkeypatch):
    a = executable(tmp_path / "工具 A")
    b = executable(tmp_path / "工具 B")
    monkeypatch.setattr(reporting, "require_evidence", lambda root: {"context_id": "evidence"})
    monkeypatch.setattr(reporting, "selection_current", lambda root: {"table_style": "plain"})
    toolchain.configure(isolated, "pandoc", str(a))
    context = reporting.paper_context(isolated)
    output = isolated / "paper/build/paper.html"
    core.write_text(output, "paper")
    core.write_json(
        output.parent / "manifest.json",
        {
            "context_id": core.identity(context),
            "artifacts": {"paper/build/paper.html": core.digest(output)},
        },
    )
    assert reporting.paper_current(isolated)
    assert str(tmp_path) not in json.dumps(context)
    toolchain.configure(isolated, "pandoc", str(b))
    assert not reporting.paper_current(isolated)
    first = toolchain.tool_identity("pandoc", isolated)
    b.write_text("different tool binary", encoding="utf-8")
    assert toolchain.tool_identity("pandoc", isolated) != first


def test_discovery_is_read_only_and_does_not_cache(isolated, tmp_path, monkeypatch):
    path = executable(tmp_path / "path")
    monkeypatch.setenv("PATH", str(path.parent))
    before = sorted(p.relative_to(isolated).as_posix() for p in isolated.rglob("*"))
    assert toolchain.resolve_tool("pandoc", isolated) == str(path)
    assert before == sorted(p.relative_to(isolated).as_posix() for p in isolated.rglob("*"))
    assert not toolchain.user_config_path().exists()
    path.unlink()
    assert toolchain.discover_tool("pandoc", isolated)["status"] == "missing"


def test_path_does_not_implicitly_execute_workspace_candidates(isolated, tmp_path, monkeypatch):
    executable(isolated)
    correct = executable(tmp_path / "installed")
    monkeypatch.chdir(isolated)
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", str(correct.parent)]))
    assert toolchain.resolve_tool("pandoc", isolated) == str(correct)


@pytest.mark.skipif(os.name != "nt", reason="Windows App Paths registry integration")
def test_exact_registry_records_discover_custom_installation(tmp_path, monkeypatch):
    path = executable(tmp_path / "自定义 注册目录")
    visited = []

    def open_key(hive, key, reserved, access):
        visited.append(key)
        return nullcontext("record")

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        HKEY_LOCAL_MACHINE=2,
        KEY_WOW64_64KEY=4,
        KEY_WOW64_32KEY=8,
        KEY_READ=16,
        REG_SZ=1,
        REG_EXPAND_SZ=2,
        OpenKey=open_key,
        QueryValueEx=lambda key, name: (str(path), 1),
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    candidates = toolchain._registered_candidates("pandoc")
    assert {candidate["path"] for candidate in candidates} == {str(path)}
    assert len(visited) == 4
    assert all(key.endswith("App Paths\\pandoc.exe") for key in visited)
