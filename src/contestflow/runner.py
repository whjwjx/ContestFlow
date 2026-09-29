"""Bounded subprocess experiments, immutable attempts, verified resume."""

from __future__ import annotations

import importlib.metadata
import math
import os
import platform
import signal
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .core import (
    FlowError,
    config,
    digest,
    identity,
    journal,
    local,
    now,
    read_json,
    require_mutable,
    safe_name,
    snapshot,
    write_json,
)


def experiments(root):
    items = read_json(local(root, "configs/experiments.json")).get("experiments", [])
    settings = config(root)
    limit = settings["budget"].get("max_experiments", 20)
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise FlowError("max_experiments must be 1-1000")
    if not items or len(items) > limit:
        raise FlowError("Configure at least one experiment within max_experiments")
    seen = set()
    for item in items:
        name = safe_name(item.get("id", ""))
        if name in seen:
            raise FlowError(f"Duplicate experiment id: {name}")
        seen.add(name)
        command = item.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(s, str) and s for s in command)
        ):
            raise FlowError(f"{name}: command must be a nonempty argv list; no shell strings")
        if not item.get("inputs") or not isinstance(item["inputs"], list):
            raise FlowError(f"{name}: explicit inputs are required")
        outputs = item.get("outputs", ["result.json"])
        if "result.json" not in outputs:
            raise FlowError("Every experiment must produce result.json")
        for output in outputs:
            local(root, output)
        timeout = item.get("timeout_seconds", settings["budget"]["timeout_seconds"])
        if (
            not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 0 < timeout <= 86400
        ):
            raise FlowError("timeout_seconds must be finite and in (0, 86400]")
    return items


def fingerprint(root, spec):
    versions = {}
    for name in spec.get("packages", []):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    context = {
        "schema_version": 1,
        "spec": spec,
        "inputs": snapshot(root, spec["inputs"]),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": versions,
        "environment": {
            key: identity(os.environ.get(key)) for key in spec.get("environment_keys", [])
        },
    }
    return identity(context), context


def result_valid(value):
    metrics = value.get("metrics")
    if value.get("valid") is not True or not isinstance(metrics, dict) or not metrics:
        raise FlowError("result.json needs valid=true and nonempty metrics")
    for name, number in metrics.items():
        if (
            not isinstance(number, (float, int))
            or isinstance(number, bool)
            or not math.isfinite(number)
        ):
            raise FlowError(f"Metric {name} is not a finite number")
    return value


def fresh_record(root, record, spec):
    key, _ = fingerprint(root, spec)
    if record.get("fingerprint") != key or record.get("status") != "success":
        return False
    expected = record.get("artifacts", {})
    if not expected or any(
        not local(root, name).is_file() or digest(local(root, name)) != sha
        for name, sha in expected.items()
    ):
        return False
    result = result_valid(read_json(local(root, record["result"])))
    return result == record.get("result_data")


def latest(root, spec):
    folder = local(root, f"runs/{spec['id']}")
    paths = sorted(folder.glob("*/record.json"), reverse=True) if folder.exists() else []
    if not paths:
        return {"id": spec["id"], "status": "missing"}
    record = read_json(paths[0])
    try:
        fresh = fresh_record(root, record, spec)
    except FlowError:
        fresh = False
    if record.get("status") == "success" and not fresh:
        return {**record, "status": "stale"}
    return record


def current_runs(root):
    return [latest(root, spec) for spec in experiments(root)]


def child_process_options():
    """Keep internal preflight descendants inside the externally supervised session."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if os.environ.get("CONTESTFLOW_PREFLIGHT_CHILD") == "1":
        if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
            raise FlowError("Internal preflight mode requires an isolated session/group leader")
        return {}
    return {"start_new_session": True}


def kill_tree(process):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        if os.environ.get("CONTESTFLOW_PREFLIGHT_CHILD") == "1":
            # An internal timeout aborts the entire disposable probe, including
            # this leader and sibling work. This also clears grandchildren after
            # the direct child exits. Never signal a shared host session.
            if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
                raise FlowError("Refusing to terminate an unisolated host process group")
            os.killpg(os.getpgrp(), signal.SIGKILL)
            raise FlowError("Preflight process group terminated")  # unreachable after SIGKILL
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def run_one(root: Path, spec, force=False):
    from .version_control import provenance

    previous = latest(root, spec)
    if previous["status"] == "success" and not force:
        return {**previous, "reused": True}
    key, context = fingerprint(root, spec)
    attempt = str(time.time_ns()) + "-" + uuid.uuid4().hex[:8]
    relative = f"runs/{spec['id']}/{attempt}"
    run_dir = local(root, relative)
    run_dir.mkdir(parents=True)
    substitutions = {
        "{python}": sys.executable,
        "{workspace}": str(root.resolve()),
        "{run_dir}": str(run_dir.resolve()),
    }
    argv = list(spec["command"])
    for token, value in substitutions.items():
        argv = [arg.replace(token, value) for arg in argv]
    timeout = spec.get("timeout_seconds", config(root)["budget"]["timeout_seconds"])
    record = {
        "schema_version": 1,
        "id": spec["id"],
        "attempt": attempt,
        "fingerprint": key,
        "context": context,
        "repository": provenance(root),
        "started_at": now(),
        "command": argv,
        "status": "running",
        "reused": False,
    }
    write_json(run_dir / "record.json", record)
    start = time.monotonic()
    try:
        with (run_dir / "stdout.log").open("wb") as out, (run_dir / "stderr.log").open("wb") as err:
            options = child_process_options()
            process = subprocess.Popen(
                argv, cwd=root, stdout=out, stderr=err, shell=False, **options
            )
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                kill_tree(process)
                record["status"] = "timeout"
            else:
                record["exit_code"] = code
                record["status"] = "error" if code else "success"
        if record["status"] == "success":
            result = result_valid(read_json(local(root, relative + "/result.json")))
            names = [relative + "/" + n for n in spec.get("outputs", ["result.json"])]
            record.update(
                result_data=result,
                result=relative + "/result.json",
                artifacts=snapshot(root, names),
            )
            after, _ = fingerprint(root, spec)
            if after != key:
                raise FlowError("Inputs changed during execution; result cannot be accepted")
    except (OSError, FlowError, ValueError) as exc:
        record["status"] = "error"
        record["error"] = str(exc)
    record.update(elapsed_seconds=round(time.monotonic() - start, 6), finished_at=now())
    write_json(run_dir / "record.json", record)
    return record


def run(root, allow_exec=False, workers=None, force=False):
    require_mutable(root)
    if not allow_exec:
        raise FlowError(
            "Review configs/experiments.json first, then pass --allow-exec. This is not a sandbox."
        )
    specs = experiments(root)
    workers = workers if workers is not None else config(root)["budget"]["workers"]
    if not isinstance(workers, int) or not 1 <= workers <= 16:
        raise FlowError("workers must be 1-16")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(lambda spec: run_one(root, spec, force=force), specs))
    journal(
        root,
        "run",
        {
            "statuses": {r["id"]: r["status"] for r in records},
            "reused": sum(bool(r.get("reused")) for r in records),
        },
    )
    return records
