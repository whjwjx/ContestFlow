"""Filesystem contracts and identities shared by every stage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class FlowError(Exception):
    """An actionable workflow error, not an internal traceback."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(value: bytes):
    return hashlib.sha256(value).hexdigest()


def digest(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(value):
    return digest_bytes(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    )


def read_json(path: Path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig"),
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
        )
    except (OSError, ValueError) as exc:
        raise FlowError(f"Cannot read JSON {path}: {exc}") from exc


def write_text(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".flow-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def safe_name(name: str):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise FlowError(f"Invalid identifier: {name!r}")
    if name.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"{base}{i}" for base in ("COM", "LPT") for i in range(1, 10)),
    }:
        raise FlowError(f"Reserved identifier: {name}")
    return name


def safe_relative(name: str):
    p = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or p.is_absolute()
        or any(part in (".", "..", "") for part in name.split("/"))
    ):
        raise FlowError(f"Unsafe relative path: {name!r}")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"{base}{i}" for base in ("COM", "LPT") for i in range(1, 10)),
    }
    for part in p.parts:
        if (
            part.endswith((".", " "))
            or part.split(".")[0].upper() in reserved
            or any(ord(c) < 32 or c in '<>"|?*' for c in part)
        ):
            raise FlowError(f"Nonportable archive/workspace path: {name!r}")
    return p


def local(root: Path, name: str):
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise FlowError("Managed workspace root must not be a link")
    parts = safe_relative(name).parts
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise FlowError(f"Links are not accepted in managed artifacts: {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise FlowError(f"Path escapes workspace: {name}")
    return path


def files_under(root: Path, relative: str):
    target = local(root, relative)
    if not target.exists():
        raise FlowError(f"Missing input: {relative}")
    if target.is_file():
        return [target]
    found = []
    for item in sorted(target.rglob("*")):
        local(root, item.relative_to(root).as_posix())
        if item.is_file():
            found.append(item)
    return found


def snapshot(root: Path, names):
    result = {}
    for name in names:
        for path in files_under(root, name):
            result[path.relative_to(root).as_posix()] = digest(path)
    return dict(sorted(result.items()))


def config(root: Path):
    value = read_json(local(root, "contest.json"))
    if value.get("schema_version") != 1:
        raise FlowError("Unsupported contest.json schema_version")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise FlowError("contest.json needs a title")
    return value


def require_mutable(root: Path):
    config(root)
    if local(root, "deliverables/FROZEN.json").exists():
        raise FlowError(
            "This workspace is frozen. Start a new workspace/version; do not overwrite it."
        )


@contextmanager
def workspace_lock(root: Path):
    path = local(root, ".contestflow.lock")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise FlowError(
            "Workspace busy. Inspect .contestflow.lock before removing a stale lock."
        ) from exc
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(f"pid={os.getpid()} time={now()}\n")
        yield
    finally:
        path.unlink(missing_ok=True)


def journal(root: Path, action: str, detail):
    path = local(root, "docs/events.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"time": now(), "actor": "automation", "action": action, "detail": detail},
                ensure_ascii=False,
            )
            + "\n"
        )
