"""Inspect actual wheel/sdist content and hashes without extracting archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN = {".git", ".venv", ".contestflow", "__pycache__", "workspaces", "output", "reports"}
REQUIRED = {
    "contestflow/preflight.py",
    "contestflow/preflight_probe.py",
    "contestflow/toolchain.py",
    "contestflow/resources.py",
    "contestflow/paper_resources.py",
    "contestflow/version_control.py",
    "contestflow/templates/resources.json",
    "contestflow/templates/workspace-agents.md",
}
MAX_TOTAL = 16 * 1024 * 1024


def check_members(members, kind):
    total = 0
    names = set()
    normalized_names = set()
    roots = set()
    for name, data in members:
        path = PurePosixPath(name)
        raw_parts = name.split("/")
        if (
            not name
            or path.is_absolute()
            or "\\" in name
            or ":" in name
            or any(p in ("..", ".", "") for p in raw_parts)
        ):
            raise ValueError(f"Unsafe archive member: {name}")
        roots.add(raw_parts[0])
        parts = raw_parts[1:] if kind == "sdist" else raw_parts
        normalized = "/".join(parts)
        if not normalized or normalized.casefold() in names:
            raise ValueError(f"Duplicate archive member: {name}")
        names.add(normalized.casefold())
        normalized_names.add(normalized)
        if any(p.casefold() in FORBIDDEN or p.casefold().startswith(".env") for p in parts):
            raise ValueError(f"Private/cache directory in release: {name}")
        if normalized.casefold().endswith((".local.json", ".pyc", ".pyo")):
            raise ValueError(f"Local/cache file in release: {name}")
        total += len(data)
        if total > MAX_TOTAL:
            raise ValueError("Release exceeds expected 16 MiB source-only size")
    if kind == "sdist" and len(roots) != 1:
        raise ValueError("Source distribution must have one top-level directory")
    required = {("src/" + name) if kind == "sdist" else name for name in REQUIRED}
    missing = required - normalized_names
    if missing:
        raise ValueError("Missing package content: " + ", ".join(sorted(missing)))
    if not any(name.endswith("/LICENSE") or name == "LICENSE" for name in normalized_names):
        raise ValueError("License missing from distribution")
    if kind == "sdist":
        for required_file in (
            "docs/git-collaboration.md",
            "skills/contestflow/SKILL.md",
            "skills/contestflow/agents/openai.yaml",
            "skills/contestflow/references/setup-and-resources.md",
            "skills/contestflow/references/research-and-evidence.md",
            "skills/contestflow/references/paper-and-delivery.md",
        ):
            if required_file not in normalized_names:
                raise ValueError(f"Skill content missing: {required_file}")
    return {"members": len(names), "expanded_bytes": total}


def inspect(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if sum(info.file_size for info in infos) > MAX_TOTAL:
                raise ValueError("Oversized wheel")
            if any(stat.S_ISLNK(info.external_attr >> 16) for info in infos):
                raise ValueError("Wheel contains symbolic link")
            members = [(info.orig_filename, archive.read(info)) for info in infos]
        kind = "wheel"
    else:
        with tarfile.open(path, "r:gz") as archive:
            infos = [info for info in archive.getmembers() if not info.isdir()]
            if any(not info.isfile() for info in infos):
                raise ValueError("Source distribution contains non-regular file")
            if sum(info.size for info in infos) > MAX_TOTAL:
                raise ValueError("Oversized source distribution")
            members = [(info.name, archive.extractfile(info).read()) for info in infos]
        kind = "sdist"
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        **check_members(members, kind),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = list(args.directory.glob("*.whl"))
    sources = list(args.directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise SystemExit("Use a dedicated directory containing exactly one wheel and one sdist")
    print(json.dumps([inspect(path) for path in wheels + sources], indent=2))


if __name__ == "__main__":
    main()
