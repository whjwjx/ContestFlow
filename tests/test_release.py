import json
import subprocess
import time
import zipfile
from types import SimpleNamespace

import pytest

from contestflow import core, project, release, runner


def archive(path, names, overrides=None):
    manifest = {
        "schema_version": 1,
        "members": {
            name: {"sha256": core.digest_bytes(data), "bytes": len(data)} for name, data in names
        },
    }
    if overrides:
        overrides(manifest)
    with zipfile.ZipFile(path, "w") as result:
        for name, data in names:
            result.writestr(name, data)
        result.writestr("MANIFEST.json", json.dumps(manifest))


def test_archive_actual_bytes(tmp_path):
    path = tmp_path / "ok.zip"
    archive(path, [("src/solver.py", b"pass\n")])
    assert "src/solver.py" in release.verify_archive(path)["members"]


@pytest.mark.parametrize(
    "name", ["../outside", "C:/secret", "folder\\file", "/absolute", "a/../../b"]
)
def test_unsafe_archive_names(tmp_path, name):
    path = tmp_path / "bad.zip"
    archive(path, [(name, b"content")])
    with pytest.raises(core.FlowError):
        release.verify_archive(path)


def test_duplicate_archive_members(tmp_path):
    path = tmp_path / "bad.zip"
    with pytest.warns(UserWarning):
        archive(path, [("a.txt", b"x"), ("a.txt", b"x")])
    with pytest.raises(core.FlowError):
        release.verify_archive(path)


def test_case_collision(tmp_path):
    path = tmp_path / "bad.zip"
    archive(path, [("A.txt", b"x"), ("a.txt", b"x")])
    with pytest.raises(core.FlowError):
        release.verify_archive(path)


def test_hash_mismatch(tmp_path):
    path = tmp_path / "bad.zip"
    archive(path, [("a.txt", b"x")], lambda m: m["members"]["a.txt"].update(sha256="wrong"))
    with pytest.raises(core.FlowError):
        release.verify_archive(path)


def test_member_missing_from_manifest(tmp_path):
    path = tmp_path / "bad.zip"
    archive(path, [("a.txt", b"x")], lambda m: m["members"].clear())
    with pytest.raises(core.FlowError):
        release.verify_archive(path)


def test_resigned_payload_must_match_source(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    project.init(root)
    core.write_text(root / "source.txt", "original")
    ctx = {"files": {"source.txt": core.digest(root / "source.txt")}}
    monkeypatch.setattr(release, "release_context", lambda _: ctx)
    path = root / "deliverables/wrong.zip"
    archive(path, [("source.txt", b"changed")], lambda m: m.update(context_id=core.identity(ctx)))
    core.write_json(
        root / "deliverables/candidate.json",
        {
            "path": "deliverables/wrong.zip",
            "sha256": core.digest(path),
            "context_id": core.identity(ctx),
        },
    )
    with pytest.raises(core.FlowError, match="payload differs"):
        release.verify(root)


def test_private_paths_case_insensitive(tmp_path):
    root = tmp_path / "workspace"
    project.init(root)
    core.write_text(root / ".ENV", "SECRET=value")
    cfg = core.config(root)
    cfg["package"]["include"] = [".ENV"]
    core.write_json(root / "contest.json", cfg)
    with pytest.raises(core.FlowError):
        release.publication_files(root)


def test_generated_python_cache_not_packaged(tmp_path):
    root = tmp_path / "workspace"
    project.init(root)
    core.write_text(root / "src/solver.py", "pass\n")
    core.write_text(root / "src/__pycache__/solver.pyc", "generated cache")
    cfg = core.config(root)
    cfg["package"]["include"] = ["src"]
    core.write_json(root / "contest.json", cfg)
    assert set(release.publication_files(root)) == {"src/solver.py"}


def test_obsolete_build_outputs_not_packaged(tmp_path):
    root = tmp_path / "workspace"
    project.init(root)
    core.write_text(root / "paper/build/paper.pdf", "current")
    core.write_text(root / "paper/build/paper.html", "stale")
    core.write_text(root / "paper/build/build.log", "local paths")
    core.write_json(
        root / "paper/build/manifest.json",
        {"artifacts": {"paper/build/paper.pdf": core.digest(root / "paper/build/paper.pdf")}},
    )
    cfg = core.config(root)
    cfg["package"]["include"] = ["paper"]
    core.write_json(root / "contest.json", cfg)
    members = release.publication_files(root)
    assert "paper/build/paper.pdf" in members
    assert "paper/build/paper.html" not in members
    assert "paper/build/build.log" not in members


@pytest.mark.parametrize("name", ["CON.txt", "dir/file.", "dir/file ", "a?b", "nul"])
def test_nonportable_archive_names(tmp_path, name):
    path = tmp_path / "bad.zip"
    archive(path, [(name, b"content")])
    with pytest.raises(core.FlowError):
        release.verify_archive(path)


def smoke_fixture(tmp_path, monkeypatch, script="pass\n", **settings):
    path = tmp_path / "smoke.zip"
    archive(path, [("src/solver.py", script.encode("utf-8"))])
    spec = {
        "command": ["{python}", "src/solver.py"],
        "result": "smoke-result.json",
        "timeout_seconds": 60,
        **settings,
    }
    monkeypatch.setattr(release, "config", lambda root: {"package": {"smoke": spec}})
    return path, release.verify_archive(path)


@pytest.mark.parametrize(
    "field,value",
    [
        *(
            ("timeout_seconds", value)
            for value in (
                "nan",
                "10",
                float("nan"),
                -1,
                0,
                float("inf"),
                181,
                True,
                False,
                None,
                10**1000,
            )
        ),
        *(
            ("command", value)
            for value in (
                [],
                "python solver.py",
                ["python", None],
                ["python", 1],
                ["python", ""],
                ["python", " "],
                ["python", "\0"],
            )
        ),
        *(
            ("result", value)
            for value in (
                None,
                7,
                "../outside.json",
                "/absolute.json",
                "src/solver.py",
                "SRC/SOLVER.PY",
                "src",
                "src/solver.py/new.json",
                "smoke.log",
                "SMOKE.LOG",
                "MANIFEST.json",
            )
        ),
        *(
            ("expected_metrics", value)
            for value in (
                None,
                [],
                {"score": float("nan")},
                {"score": float("inf")},
                {"": 1},
                {"score": True},
                {"score": "1"},
                {3: 1},
                {"score": 10**1000},
            )
        ),
        *(
            ("tolerance", value)
            for value in ("nan", float("nan"), -1, float("inf"), True, 10**1000)
        ),
    ],
)
def test_invalid_smoke_settings_never_start_code(tmp_path, monkeypatch, field, value):
    path, manifest = smoke_fixture(tmp_path, monkeypatch, **{field: value})
    monkeypatch.setattr(
        release.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("invalid spec spawned")
    )
    with pytest.raises(core.FlowError):
        release.smoke_archive(tmp_path, path, manifest, allow_exec=True)


@pytest.mark.parametrize("spec", [None, [], "command", {"result": "x.json"}])
def test_malformed_smoke_spec_never_starts_code(tmp_path, monkeypatch, spec):
    monkeypatch.setattr(release, "config", lambda root: {"package": {"smoke": spec}})
    monkeypatch.setattr(
        release.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("invalid spec spawned")
    )
    with pytest.raises(core.FlowError):
        release.smoke_archive(tmp_path, tmp_path / "absent.zip", {"members": {}}, True)


def test_smoke_zero_tolerance_and_upper_timeout_are_valid(tmp_path, monkeypatch):
    script = (
        "import json; from pathlib import Path; "
        "Path('smoke-result.json').write_text(json.dumps({'valid':True,'metrics':{'cost':44}}))"
    )
    path, manifest = smoke_fixture(
        tmp_path,
        monkeypatch,
        script,
        expected_metrics={"cost": 44},
        tolerance=0,
        timeout_seconds=180,
    )
    result = release.smoke_archive(tmp_path, path, manifest, allow_exec=True)
    assert result["status"] == "passed"
    assert result["result"]["metrics"] == {"cost": 44}


@pytest.mark.parametrize("mode", ["timeout", "wait-error", "interrupt"])
def test_actual_smoke_failures_terminate_process_tree(tmp_path, monkeypatch, mode):
    monkeypatch.delenv("CONTESTFLOW_PREFLIGHT_CHILD", raising=False)
    ready = tmp_path / "child-ready.txt"
    escaped = tmp_path / "escaped.txt"
    descendant = (
        "from pathlib import Path; import time; "
        f"Path({str(ready)!r}).write_text('ready'); time.sleep(2); "
        f"Path({str(escaped)!r}).write_text('escaped')"
    )
    script = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); time.sleep(60)"
    )
    path, manifest = smoke_fixture(tmp_path, monkeypatch, script, timeout_seconds=1)
    launched = []
    original_popen = subprocess.Popen

    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        launched.append(process)
        if mode != "timeout":
            original_wait = process.wait

            def interrupted_wait(timeout):
                deadline = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                process.wait = original_wait
                assert ready.exists(), "test child did not start"
                if mode == "interrupt":
                    raise KeyboardInterrupt()
                raise OSError("simulated wait failure")

            process.wait = interrupted_wait
        return process

    monkeypatch.setattr(
        release,
        "subprocess",
        SimpleNamespace(Popen=popen, TimeoutExpired=subprocess.TimeoutExpired),
    )
    expected = {"timeout": core.FlowError, "wait-error": OSError, "interrupt": KeyboardInterrupt}
    try:
        with pytest.raises(expected[mode]):
            release.smoke_archive(tmp_path, path, manifest, allow_exec=True)
        assert launched and launched[0].poll() is not None
        assert ready.exists(), "test descendant must actually run before cleanup"
        time.sleep(2.2)
        assert not escaped.exists(), "descendant survived smoke cleanup"
    finally:
        if launched and launched[0].poll() is None:
            runner.kill_tree(launched[0])
