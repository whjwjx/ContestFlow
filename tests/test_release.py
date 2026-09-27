import json
import zipfile

import pytest

from contestflow import core, project, release


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
