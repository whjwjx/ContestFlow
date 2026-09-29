"""Exercise distribution inspection against private and unsafe archive entries."""

import importlib.util
import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_artifacts", Path(__file__).resolve().parents[1] / "scripts/check_release_artifacts.py"
)
artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifacts)


def wheel(path, extra=None, missing=None):
    with zipfile.ZipFile(path, "w") as archive:
        for name in artifacts.REQUIRED - {missing}:
            archive.writestr(name, "public source")
        archive.writestr("contestflow_local.dist-info/licenses/LICENSE", "MIT")
        if extra:
            name, data = extra
            if isinstance(name, str):
                info = zipfile.ZipInfo()
                info.filename = name
                name = info
            archive.writestr(name, data)
    return path


def test_inspects_actual_wheel(tmp_path):
    result = artifacts.inspect(wheel(tmp_path / "release.whl"))
    assert result["members"] == len(artifacts.REQUIRED) + 1
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize(
    "name",
    [
        "../private.txt",
        "contestflow/../private.txt",
        "contestflow\\private.txt",
        "contestflow/.env",
        "contestflow/tools.local.json",
        "workspaces/team.txt",
        "CONTESTFLOW/preflight.py",
        "/absolute.txt",
        "C:/private.txt",
    ],
)
def test_rejects_private_or_nonportable_member(tmp_path, name):
    with pytest.raises(ValueError):
        artifacts.inspect(wheel(tmp_path / "bad.whl", (name, "synthetic")))


def test_detects_missing_new_module(tmp_path):
    with pytest.raises(ValueError, match="Missing package"):
        artifacts.inspect(wheel(tmp_path / "old.whl", missing="contestflow/paper_resources.py"))


def test_rejects_archive_links(tmp_path):
    link = zipfile.ZipInfo("contestflow/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="symbolic link"):
        artifacts.inspect(wheel(tmp_path / "link.whl", (link, "../outside")))
    path = tmp_path / "link.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("release/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../outside"
        archive.addfile(info)
    with pytest.raises(ValueError, match="non-regular"):
        artifacts.inspect(path)


def test_sdist_requires_complete_skill(tmp_path):
    path = tmp_path / "incomplete.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in sorted({"src/" + p for p in artifacts.REQUIRED} | {"LICENSE"}):
            data = b"public"
            info = tarfile.TarInfo("release/" + name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="Skill content missing"):
        artifacts.inspect(path)
