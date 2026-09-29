"""Explicit workspace-repository identity and simple Agent collaboration policy."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .core import FlowError, config, require_mutable, write_json
from .toolchain import resolve_tool

MODES = ("off", "local", "team")


def default_policy(mode="off"):
    if mode not in MODES:
        raise FlowError("Git mode must be off, local or team")
    enabled = mode != "off"
    return {
        "mode": mode,
        "repository_root": ".",
        "commit_policy": "milestone" if enabled else "none",
        "push_policy": "task-branches" if mode == "team" else "none",
        "task_branch_pattern": "agent/<member>/<goal>" if enabled else None,
        "protected_branches": ["main", "dev"],
    }


def policy(root):
    value = config(root).get("version_control", default_policy())
    if not isinstance(value, dict) or value.get("mode") not in MODES:
        raise FlowError("contest.json version_control.mode must be off, local or team")
    expected = default_policy(value["mode"])
    if value != expected:
        raise FlowError(
            "contest.json version_control must use the generated policy; "
            "change it with contestflow repo"
        )
    return value


def _run(git, root, *args):
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    try:
        return subprocess.run(
            [git, "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            env=environment,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FlowError(f"Git command failed: {exc}") from exc


def _same_path(left, right):
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
        str(Path(right).resolve())
    )


def _top_level(git, root):
    result = _run(git, root, "rev-parse", "--show-toplevel")
    if result.returncode:
        return None
    value = result.stdout.strip()
    return Path(value).resolve() if value else None


def _update_policy(root, mode):
    settings = config(root)
    settings["version_control"] = default_policy(mode)
    write_json(root / "contest.json", settings)


def validate_target(root, mode):
    """Fail before workspace creation when Git cannot safely own this exact path."""
    if mode not in ("local", "team"):
        raise FlowError("Repository initialization requires local or team mode")
    root = Path(root).resolve()
    git = resolve_tool("git", root)
    probe = root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    found = _top_level(git, probe)
    if found is not None and not _same_path(found, root):
        raise FlowError(
            "Competition workspace is inside a different Git repository. "
            "Use a separate directory or explicitly manage it as part of that repository; "
            "ContestFlow will not create a nested repository."
        )


def enable(root, mode):
    """Initialize or adopt an exact-root repository; never create a nested repository."""
    if mode not in ("local", "team"):
        raise FlowError("Repository initialization requires local or team mode")
    root = Path(root).resolve()
    require_mutable(root)
    git = resolve_tool("git", root)
    found = _top_level(git, root)
    marker = root / ".git"
    if found is not None and not _same_path(found, root):
        raise FlowError(
            "Competition workspace is inside a different Git repository. "
            "Use a separate directory or explicitly manage it as part of that repository; "
            "ContestFlow will not create a nested repository."
        )
    if found is None:
        if marker.exists():
            raise FlowError("Workspace .git exists but Git cannot verify it")
        result = _run(git, root, "init", "--initial-branch=main")
        if result.returncode:
            raise FlowError("Git initialization failed: " + result.stderr.strip()[-1000:])
        found = _top_level(git, root)
    if found is None or not _same_path(found, root):
        raise FlowError("Git repository root does not match the competition workspace")
    _update_policy(root, mode)
    return inspect(root)


def disable(root):
    """Disable Agent-managed commits without deleting repository metadata."""
    require_mutable(root)
    _update_policy(Path(root), "off")
    return inspect(root)


def inspect(root):
    """Return repository identity without exposing remote URLs or changing Git state."""
    root = Path(root).resolve()
    selected = policy(root)
    base = {
        "mode": selected["mode"],
        "workspace_root": str(root),
        "repository_root": None,
        "root_matches": False,
        "commit_policy": selected["commit_policy"],
        "push_policy": selected["push_policy"],
        "task_branch_pattern": selected["task_branch_pattern"],
        "protected_branches": selected["protected_branches"],
        "branch": None,
        "head": None,
        "dirty": None,
        "changes": None,
        "remotes": [],
    }
    if selected["mode"] == "off":
        return {**base, "status": "disabled"}
    try:
        git = resolve_tool("git", root)
        found = _top_level(git, root)
    except FlowError as exc:
        return {**base, "status": "git_unavailable", "detail": str(exc)}
    if found is None:
        return {**base, "status": "missing", "detail": "No Git repository found"}
    result = {**base, "repository_root": str(found), "root_matches": _same_path(found, root)}
    if not result["root_matches"]:
        return {
            **result,
            "status": "mismatch",
            "detail": "Git root differs from the configured competition workspace",
        }
    branch = _run(git, root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _run(git, root, "rev-parse", "--verify", "HEAD")
    changed = _run(git, root, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    remotes = _run(git, root, "remote")
    if changed.returncode or remotes.returncode:
        return {**result, "status": "invalid", "detail": "Git status inspection failed"}
    entries = [item for item in changed.stdout.split("\0") if item]
    return {
        **result,
        "status": "ready",
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "dirty": bool(entries),
        "changes": len(entries),
        "remotes": sorted(line for line in remotes.stdout.splitlines() if line),
    }


def provenance(root):
    """Small path-free Git context for experiment records."""
    state = inspect(root)
    return {
        key: state.get(key) for key in ("mode", "status", "branch", "head", "dirty", "root_matches")
    }
