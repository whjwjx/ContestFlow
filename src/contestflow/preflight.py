"""Inventory, bounded functional probes, and synthetic toolchain rehearsals."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .core import FlowError, config, digest, identity, local, now, read_json, write_json
from .toolchain import discover_tool

GROUPS = {
    "core": {
        "packages": {},
        "tools": [],
        "fix": "Use Python >=3.11 and a writable working directory.",
    },
    "science": {
        "packages": {"numpy": "1.26", "scipy": "1.11"},
        "tools": [],
        "fix": "Install the science extra into the interpreter shown in this report.",
    },
    "plots": {
        "packages": {"matplotlib": "3.8"},
        "tools": [],
        "fix": "Install the science extra and a Chinese font; inspect the generated PNG/PDF.",
    },
    "documents-html": {
        "packages": {},
        "tools": ["pandoc"],
        "fix": "Install the documents extra or configure the Pandoc executable.",
    },
    "documents-pdf": {
        "packages": {"pypdf": "6.19"},
        "tools": ["pandoc", "xelatex"],
        "fix": "Configure Pandoc/XeLaTeX and paper.cjk_font; check TeX packages and fonts.",
    },
    "delivery": {
        "packages": {},
        "tools": [],
        "fix": "Check temporary-directory permissions and the reported archive error.",
    },
    "gpu": {
        "packages": {},
        "tools": ["nvidia-smi"],
        "fix": "Configure the NVIDIA tool/driver only if the selected method needs it.",
    },
}
PROFILES = {
    "core": ["core"],
    "science": ["core", "science"],
    "plots": ["core", "science", "plots"],
    "documents-html": ["core", "documents-html"],
    "documents-pdf": ["core", "documents-pdf"],
    "delivery": ["core", "delivery"],
    "gpu": ["core", "gpu"],
    "full-html": ["core", "science", "plots", "documents-html", "delivery"],
    "full-pdf": ["core", "science", "plots", "documents-html", "documents-pdf", "delivery"],
}
TIMEOUTS = {
    "core": 15,
    "science": 30,
    "plots": 45,
    "documents-html": 45,
    "documents-pdf": 90,
    "delivery": 20,
    "gpu": 15,
    "rehearsal": 180,
}
PACKAGES = ("numpy", "scipy", "matplotlib", "pypdf", "pypandoc")


def inventory(root=None):
    """No version commands, numerical imports, installs, or writes."""
    packages, versions = {}, {}
    for name in PACKAGES:
        try:
            packages[name] = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError, AttributeError):
            packages[name] = False
        versions[name] = None
        distributions = ("pypandoc", "pypandoc_binary") if name == "pypandoc" else (name,)
        for distribution in distributions:
            try:
                versions[name] = importlib.metadata.version(distribution)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
    details = {
        name: discover_tool(name, root) for name in ("pandoc", "xelatex", "git", "nvidia-smi")
    }
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
        "package_versions": versions,
        "tools": {name: item["path"] for name, item in details.items()},
        "tool_details": details,
        "note": "Inventory only. Found does not mean functional; optional tools are not requirements.",
    }


def _profile(root, requested):
    if requested is not None:
        value = requested
    elif root is not None and local(root, "configs/preflight.json").exists():
        saved = read_json(local(root, "configs/preflight.json"))
        if (
            not isinstance(saved, dict)
            or type(saved.get("schema_version")) is not int
            or saved["schema_version"] != 1
        ):
            raise FlowError("Invalid configs/preflight.json schema_version")
        if set(saved) - {"schema_version", "profile"}:
            raise FlowError("Unknown configs/preflight.json fields")
        value = saved.get("profile", "core")
    else:
        value = "core"
    if not isinstance(value, str) or value not in PROFILES:
        raise FlowError(f"Unknown preflight profile: {value!r}")
    return value


def _selection(root):
    if root is None:
        return []
    from .resources import selected_resources

    return selected_resources(root)


def _availability(group, env):
    issues = []
    if group == "core" and sys.version_info < (3, 11):
        issues.append("Python >=3.11 is required")
    for name, minimum in GROUPS[group]["packages"].items():
        if not env["packages"].get(name):
            issues.append(f"{name}: missing")
            continue
        version = env["package_versions"].get(name)
        match = re.match(r"^(\d+)(?:\.(\d+))?", version or "")
        if match:
            actual = tuple(int(x or 0) for x in match.groups())
            required = tuple(int(x) for x in (minimum + ".0").split(".")[:2])
            if actual < required:
                issues.append(f"{name}: {version} < required {minimum}")
    for name in GROUPS[group]["tools"]:
        item = env["tool_details"][name]
        if item["status"] != "found":
            issues.append(f"{name}: {item['status']}; {item.get('detail', '')}")
    return issues


def _probe(group, folder, settings):
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / "probe.local.json", settings)
    env = os.environ.copy()
    # Keep the same package source when called from an editable checkout as well as a wheel.
    env["PYTHONPATH"] = (
        str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["MPLCONFIGDIR"] = str(folder / "matplotlib-cache")
    env["CONTESTFLOW_PREFLIGHT_CHILD"] = "1"
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "contestflow.preflight_probe", group, "probe.local.json"],
        cwd=folder,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **options,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=TIMEOUTS[group])
    except subprocess.TimeoutExpired:
        from .runner import kill_tree

        kill_tree(process)
        stdout, stderr = process.communicate()
        timed_out = True
    (folder / "probe.log").write_text(stdout + stderr, encoding="utf-8")
    result_path = folder / "result.local.json"
    detail = read_json(result_path) if result_path.exists() else {}
    passed = not timed_out and process.returncode == 0 and detail.get("passed") is True
    return {
        "status": "passed" if passed else "failed",
        "detail": detail
        if passed
        else (
            f"Timed out after {TIMEOUTS[group]} seconds"
            if timed_out
            else (stderr or stdout or "Probe produced no success record")[-6000:]
        ),
        "log": f"{group}/probe.log",
        "timeout_seconds": TIMEOUTS[group],
    }


def preflight(root=None, profile=None, level="inventory", output=None):
    if level not in ("inventory", "functional", "rehearsal"):
        raise FlowError("level must be inventory, functional, or rehearsal")
    root = Path(root).absolute() if root is not None else None
    settings = config(root) if root is not None else {}
    selected = _selection(root)
    profile = _profile(root, profile)
    groups = set(PROFILES[profile])
    for item in selected:
        groups.update(item["checks"])
    if groups - GROUPS.keys():
        raise FlowError("Selected resources refer to unknown preflight checks")
    if "plots" in groups:
        groups.update(("core", "science"))
    if level == "rehearsal":
        groups.update(PROFILES["full-pdf" if "documents-pdf" in groups else "full-html"])
    env = inventory(root)
    checks = []
    for group in GROUPS:
        issues = _availability(group, env) if group in groups else []
        checks.append(
            {
                "id": group,
                "required": group in groups,
                "status": (
                    "not_needed" if group not in groups else "missing" if issues else "not_tested"
                ),
                "detail": issues
                or ("Selected; functional probe not run" if group in groups else "Not selected"),
                "remedy": GROUPS[group]["fix"] if group in groups else None,
            }
        )
    report = {
        "schema_version": 1,
        "created_at": now(),
        "profile": profile,
        "level": level,
        "checker": {
            "version": __version__,
            "implementation": {
                name: digest(Path(__file__).with_name(name))
                for name in ("preflight.py", "preflight_probe.py", "toolchain.py")
            },
        },
        "environment": env,
        "resources": [item["id"] for item in selected],
        "resource_fingerprint": identity(selected),
        "checks": checks,
        "human_review": "not_asserted",
        "submission_readiness": "not_assessed",
        "note": "Only the selected capabilities are checked. Inspect visual output and competition rules as a team.",
        "artifacts_retained": output is not None,
    }
    probe_settings = {
        "tools": env["tools"],
        "paper": settings.get("paper", {}),
        "workspace": str(root) if root else None,
        "workspace_frozen": bool(root and local(root, "deliverables/FROZEN.json").exists()),
        "format": "pdf" if "documents-pdf" in groups else "html",
        "resource_files": {
            name: read_json(local(root, name))
            for name in ("configs/resources.json", "configs/resource-library.json")
            if root and local(root, name).exists()
        },
    }
    if output is not None:
        output = Path(output).absolute()
        # Local paths, versions and logs belong in an explicitly chosen fresh folder.
        if output.exists():
            raise FlowError(f"Preflight output must be a new directory: {output}")
        if root:
            try:
                output.resolve().relative_to(root.resolve())
            except ValueError:
                pass
            else:
                from .core import require_mutable

                require_mutable(root)
        output.mkdir(parents=True)
        _execute(report, probe_settings, output, level)
        write_json(output / "report.local.json", report)
        report["report_path"] = str(output / "report.local.json")
    elif level != "inventory":
        with tempfile.TemporaryDirectory(prefix="contestflow-preflight-") as temporary:
            _execute(report, probe_settings, Path(temporary), level)
    report["result"] = _result(report)
    if output is not None:
        write_json(output / "report.local.json", report)
    return report


def _execute(report, settings, folder, level):
    if level == "inventory":
        return
    report["disk_free_bytes"] = shutil.disk_usage(folder).free
    for item in report["checks"]:
        if item["status"] != "not_tested":
            continue
        try:
            item.update(_probe(item["id"], folder / item["id"], settings))
        except (OSError, FlowError) as exc:
            item.update(status="failed", detail=str(exc))
    if level == "rehearsal":
        if any(c["required"] and c["status"] != "passed" for c in report["checks"]):
            report["checks"].append(
                {
                    "id": "rehearsal",
                    "required": True,
                    "status": "not_tested",
                    "detail": "Resolve failed or missing prerequisites before the full rehearsal.",
                }
            )
        else:
            try:
                outcome = _probe("rehearsal", folder / "rehearsal", settings)
            except (OSError, FlowError) as exc:
                outcome = {"status": "failed", "detail": str(exc)}
            report["checks"].append({"id": "rehearsal", "required": True, **outcome})


def _result(report):
    selected = [item for item in report["checks"] if item["required"]]
    if any(item["status"] in ("failed", "missing") for item in selected):
        return "failed"
    if any(item["status"] == "not_tested" for item in selected):
        return "not_tested"
    return "passed"
