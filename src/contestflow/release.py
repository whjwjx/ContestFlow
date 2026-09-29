"""Explicit allowlists, actual archive validation, isolated smoke tests, byte freeze."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from .core import (
    FlowError,
    config,
    digest,
    digest_bytes,
    identity,
    journal,
    local,
    now,
    read_json,
    require_mutable,
    safe_relative,
    snapshot,
    write_json,
)
from .evidence import require_evidence
from .reporting import paper_current
from .runner import child_process_options, result_valid

FORBIDDEN_PARTS = {
    ".contestflow",
    ".git",
    ".venv",
    "__pycache__",
    "materials",
    "reviews",
    "deliverables",
}
MANIFEST = "MANIFEST.json"


def publication_files(root):
    settings = config(root)["package"]
    includes = settings.get("include", [])
    if not includes:
        raise FlowError("Configure an explicit package.include allowlist")
    members = snapshot(root, includes)
    members = {
        name: sha
        for name, sha in members.items()
        if not (
            {part.casefold() for part in safe_relative(name).parts}
            & {"__pycache__", ".pytest_cache", ".ruff_cache"}
        )
        and not name.casefold().endswith((".pyc", ".pyo"))
    }
    build_manifest = local(root, "paper/build/manifest.json")
    if build_manifest.exists():
        current_outputs = set(read_json(build_manifest)["artifacts"]) | {
            "paper/build/manifest.json"
        }
        members = {
            name: sha
            for name, sha in members.items()
            if not name.startswith("paper/build/") or name in current_outputs
        }
    for name in members:
        path = safe_relative(name)
        if (
            {part.casefold() for part in path.parts} & FORBIDDEN_PARTS
            or name.casefold().startswith("data/raw/")
            or name == MANIFEST
            or any(p.casefold().startswith(".env") for p in path.parts)
            or name.casefold().endswith(".local.json")
        ):
            raise FlowError(f"Private or reserved path in package: {name}")
    return members


def release_context(root):
    require_evidence(root)
    if not paper_current(root):
        raise FlowError("Paper missing or stale; rebuild and review the actual output")
    if config(root)["package"].get("require_pdf", True):
        paper = read_json(local(root, "paper/build/manifest.json"))
        if "paper/build/paper.pdf" not in paper["artifacts"]:
            raise FlowError("PDF is required by the current package configuration")
    return {
        "files": publication_files(root),
        "config": config(root),
        "paper_manifest": digest(local(root, "paper/build/manifest.json")),
    }


def scan_private(root, names):
    markers = config(root)["package"].get("private_markers", [])
    findings = []
    patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"sk-[A-Za-z0-9_-]{25,}"]
    for name in names:
        data = local(root, name).read_bytes()
        for marker in markers:
            if marker and (marker.casefold() in name.casefold() or marker.encode("utf-8") in data):
                findings.append(name + ": configured private marker")
        if any(re.search(pattern, data) for pattern in patterns):
            findings.append(name + ": possible secret")
    return findings


def verify_archive(path: Path, limit_mb=50):
    if not isinstance(limit_mb, (int, float)) or not 0 < limit_mb <= 2048:
        raise FlowError("Archive limit must be in (0, 2048] MiB")
    if path.stat().st_size > limit_mb * 1024 * 1024:
        raise FlowError("Archive exceeds configured compressed size limit")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (
                len(names) > 10000
                or len(set(names)) != len(names)
                or len({n.casefold() for n in names}) != len(names)
            ):
                raise FlowError("Duplicate/case-colliding members or excessive member count")
            for info in infos:
                safe_relative(info.filename)
                if info.is_dir() or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise FlowError("Directory or symlink members are not allowed")
            if sum(info.file_size for info in infos) > 512 * 1024 * 1024:
                raise FlowError("Expanded archive exceeds 512 MiB limit")
            if MANIFEST not in names or archive.getinfo(MANIFEST).file_size > 8 * 1024 * 1024:
                raise FlowError("Missing or excessive archive manifest")
            import json

            manifest = json.loads(archive.read(MANIFEST))
            members = manifest.get("members", {})
            if manifest.get("schema_version") != 1 or set(names) != set(members) | {MANIFEST}:
                raise FlowError("Archive member set does not match manifest")
            for name, expected in members.items():
                data = archive.read(name)
                if len(data) != expected["bytes"] or digest_bytes(data) != expected["sha256"]:
                    raise FlowError(f"Archive member hash/size mismatch: {name}")
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise FlowError(f"Invalid archive: {exc}") from exc
    return manifest


def package(root):
    require_mutable(root)
    ctx = release_context(root)
    findings = scan_private(root, ctx["files"])
    if findings:
        raise FlowError("Privacy scan failed: " + "; ".join(findings))
    context_id = identity(ctx)
    folder = local(root, "deliverables")
    target = folder / f"candidate-{context_id[:16]}.zip"
    if target.exists():
        verify_archive(target, config(root)["rules"]["max_archive_mb"])
        raise FlowError(
            "This candidate already exists. Verify it, or change inputs for a new candidate."
        )
    members = {}
    for name, sha in ctx["files"].items():
        members[name] = {"sha256": sha, "bytes": local(root, name).stat().st_size}
    manifest = {
        "schema_version": 1,
        "context_id": context_id,
        "members": members,
        "human_review": "not_asserted",
        "platform_submission": "not_observed",
    }
    import json

    staging = target.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(members):
                archive.write(local(root, name), name)
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        verify_archive(staging, config(root)["rules"]["max_archive_mb"])
        if identity(release_context(root)) != context_id:
            raise FlowError("Inputs changed during packaging")
        staging.rename(target)
    finally:
        staging.unlink(missing_ok=True)
    record = {
        "schema_version": 1,
        "path": target.relative_to(root).as_posix(),
        "sha256": digest(target),
        "context_id": context_id,
        "created_at": now(),
    }
    write_json(folder / "candidate.json", record)
    journal(root, "package", {"sha256": record["sha256"], "members": len(members)})
    return record


def smoke_archive(root, archive_path, manifest, allow_exec):
    spec = config(root)["package"].get("smoke")
    if not spec:
        raise FlowError("Configure package.smoke.command and package.smoke.result first")
    if not allow_exec:
        raise FlowError("Package smoke runs code: review it and pass --allow-exec")
    if not isinstance(spec.get("command"), list) or not spec["command"]:
        raise FlowError("Smoke command must be an argv list")
    result_name = spec.get("result", "smoke-result.json")
    safe_relative(result_name)
    if result_name in manifest["members"]:
        raise FlowError("Smoke output must be newly generated, not a prepackaged result")
    with tempfile.TemporaryDirectory(prefix="contestflow-smoke-") as tmp:
        unpack = Path(tmp)
        with zipfile.ZipFile(archive_path) as archive:
            for name in manifest["members"]:
                path = local(unpack, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
        argv = [
            str(arg).replace("{python}", sys.executable).replace("{workspace}", str(unpack))
            for arg in spec["command"]
        ]
        from .runner import kill_tree

        options = child_process_options()
        with (unpack / "smoke.log").open("wb") as log:
            proc = subprocess.Popen(argv, cwd=unpack, stdout=log, stderr=log, **options)
            try:
                code = proc.wait(timeout=min(float(spec.get("timeout_seconds", 60)), 180))
            except subprocess.TimeoutExpired as exc:
                kill_tree(proc)
                raise FlowError("Actual-package smoke timed out") from exc
        if code:
            raise FlowError(
                "Actual-package smoke failed: "
                + (unpack / "smoke.log").read_text(errors="replace")[-2000:]
            )
        result = result_valid(read_json(local(unpack, result_name)))
        expected = spec.get("expected_metrics", {})
        for name, value in expected.items():
            if name not in result["metrics"] or abs(result["metrics"][name] - value) > float(
                spec.get("tolerance", 1e-8)
            ):
                raise FlowError("Actual-package smoke metric mismatch")
    return {
        "status": "passed",
        "result": result,
        "scope": "configured smoke only; not all experiments",
    }


def verify(root, smoke=False, allow_exec=False, persist=True):
    candidate = read_json(local(root, "deliverables/candidate.json"))
    frozen_path = local(root, "deliverables/FROZEN.json")
    if frozen_path.exists() and read_json(frozen_path)["candidate"] != candidate:
        raise FlowError("Candidate metadata differs from the frozen release")
    archive = local(root, candidate["path"])
    manifest = verify_archive(archive, config(root)["rules"]["max_archive_mb"])
    if digest(archive) != candidate["sha256"] or manifest["context_id"] != candidate["context_id"]:
        raise FlowError("Candidate identity mismatch")
    ctx = release_context(root)
    if identity(ctx) != candidate["context_id"]:
        raise FlowError("Candidate stale relative to source/evidence/paper")
    packaged = {name: entry["sha256"] for name, entry in manifest["members"].items()}
    if packaged != ctx["files"]:
        raise FlowError("Archive payload differs from the current allowlisted source files")
    report = {
        "schema_version": 1,
        "archive_sha256": candidate["sha256"],
        "context_id": candidate["context_id"],
        "automatic_checks": "passed",
        "human_review": "not_asserted",
        "platform_submission": "not_observed",
        "rules_review": config(root)["rules"]["review_status"],
        "smoke": {"status": "not_run"},
        "checked_at": now(),
    }
    if smoke:
        report["smoke"] = smoke_archive(root, archive, manifest, allow_exec)
    if persist and not local(root, "deliverables/FROZEN.json").exists():
        write_json(local(root, "deliverables/verification.json"), report)
    return report


def freeze(root, confirm=False):
    require_mutable(root)
    if not confirm:
        raise FlowError(
            "Freeze requires explicit --confirm; it does not assert scientific approval"
        )
    report_path = local(root, "deliverables/verification.json")
    previous = read_json(report_path)
    candidate = read_json(local(root, "deliverables/candidate.json"))
    if (
        previous.get("archive_sha256") != candidate["sha256"]
        or previous.get("automatic_checks") != "passed"
    ):
        raise FlowError("Verify this exact candidate first")
    if config(root)["package"].get("smoke") and previous.get("smoke", {}).get("status") != "passed":
        raise FlowError("Configured actual-package smoke has not passed")
    fresh = verify(root, persist=False)
    frozen = {
        "schema_version": 1,
        "candidate": candidate,
        "frozen_at": now(),
        "context_id": fresh["context_id"],
        "verification": previous,
        "human_review": "not_asserted",
        "platform_submission": "not_observed",
    }
    write_json(local(root, "deliverables/FROZEN.json"), frozen)
    return frozen
