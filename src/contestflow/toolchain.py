"""Read-only bounded tool discovery and explicit, machine-local preferences."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from .core import FlowError, identity, local, read_json, require_mutable, write_json

TOOLS = ("pandoc", "xelatex", "git", "nvidia-smi")
ENVIRONMENT = {"pandoc": "PANDOC", "xelatex": "XELATEX", "git": "GIT", "nvidia-smi": "NVIDIA_SMI"}
CONFIG_NAME = "tools.local.json"


def _name(name):
    if name not in TOOLS:
        raise FlowError("Supported tools: " + ", ".join(TOOLS))
    return name


def _absolute(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise FlowError(f"{label} must be a nonempty absolute path")
    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        raise FlowError(f"{label} must be an absolute path: {value}")
    return path.resolve()


def user_config_path():
    override = os.environ.get("CONTESTFLOW_USER_CONFIG")
    if override is not None:
        return _absolute(override, "CONTESTFLOW_USER_CONFIG")
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "ContestFlow" / CONFIG_NAME


def _read_settings(path):
    if not path.exists():
        return {"schema_version": 1, "tools": {}, "search_dirs": []}
    value = read_json(path)
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        raise FlowError(f"{path}: expected an object with schema_version 1")
    if value["schema_version"] != 1:
        raise FlowError(f"{path}: unsupported schema_version")
    unknown = set(value) - {"schema_version", "tools", "search_dirs"}
    if unknown:
        raise FlowError(f"{path}: unknown fields: {', '.join(sorted(unknown))}")
    tools = value.get("tools", {})
    directories = value.get("search_dirs", [])
    if not isinstance(tools, dict) or not isinstance(directories, list):
        raise FlowError(f"{path}: tools must be an object and search_dirs a list")
    for name, executable in tools.items():
        _name(name)
        _absolute(executable, f"{path}: tools.{name}")
    for directory in directories:
        _absolute(directory, f"{path}: search_dirs entry")
    return {"schema_version": 1, "tools": dict(tools), "search_dirs": list(directories)}


def _settings(root=None):
    layers = [("user-config", user_config_path())]
    if root is not None:
        layers.append(("workspace-config", local(Path(root), CONFIG_NAME)))
    result = {"schema_version": 1, "tools": {}, "search_dirs": []}
    sources = {}
    for source, path in layers:
        settings = _read_settings(path)
        for name, value in settings["tools"].items():
            result["tools"][name] = str(_absolute(value, name))
            sources[name] = source
        for value in settings["search_dirs"]:
            directory = str(_absolute(value, "search_dirs entry"))
            if directory not in result["search_dirs"]:
                result["search_dirs"].append(directory)
    return result, sources


def load_settings(root=None):
    """Return merged, validated settings; never write or cache discoveries."""
    return _settings(root)[0]


def _executable(path):
    return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))


def _filenames(name):
    return (name + ".exe", name) if os.name == "nt" else (name,)


def _candidates(directories, name, source):
    found = {}
    for directory in directories:
        for filename in _filenames(name):
            path = Path(directory) / filename
            if _executable(path):
                path = path.resolve()
                found.setdefault(os.path.normcase(str(path)), {"path": str(path), "source": source})
    return list(found.values())


def _result(name, candidates, detail=""):
    status = "found" if len(candidates) == 1 else "ambiguous" if candidates else "missing"
    return {
        "name": name,
        "status": status,
        "path": candidates[0]["path"] if status == "found" else None,
        "source": candidates[0]["source"] if candidates else None,
        "candidates": candidates,
        "detail": detail
        or (
            "File located; version and functionality have not been tested."
            if status == "found"
            else "Multiple candidates; select one with the tools command."
            if status == "ambiguous"
            else "Not discovered. Configure its full executable path or add a search directory."
        ),
    }


def _explicit(name, value, source):
    try:
        path = _absolute(value, source)
        if not _executable(path):
            raise FlowError(f"Configured executable is missing or not executable: {path}")
        return _result(name, [{"path": str(path), "source": source}])
    except (FlowError, OSError) as exc:
        return {
            "name": name,
            "status": "invalid",
            "path": None,
            "source": source,
            "candidates": [],
            "detail": str(exc) + ". Fix or remove this explicit setting; no fallback was selected.",
        }


def _bundled_pandoc_dirs():
    try:
        spec = importlib.util.find_spec("pypandoc")
    except (ImportError, ValueError):
        return []
    if spec is None:
        return []
    # get_pandoc_path imports the package and runs candidate programs. Discovery does neither.
    return [Path(folder) / "files" for folder in (spec.submodule_search_locations or ())] + [
        Path(folder) / "bin" for folder in (spec.submodule_search_locations or ())
    ]


def _registered_candidates(name):
    if os.name != "nt":
        return []
    import winreg

    candidates = []
    key_name = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + name + ".exe"
    # Exact application records only: no enumeration of the registry or uninstall inventory.
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ | view) as key:
                    value, kind = winreg.QueryValueEx(key, "")
                if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                    continue
                found = _explicit(name, value, "windows-app-paths")
                if found["status"] == "found":
                    candidates.extend(found["candidates"])
            except OSError:
                continue
    return candidates


def _known_directories(name):
    if os.name != "nt":
        return [
            Path(p)
            for p in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/Library/TeX/texbin")
        ]
    locations = []
    for variable, relative in (
        (
            "ProgramFiles",
            {
                "pandoc": "Pandoc",
                "xelatex": "MiKTeX/miktex/bin/x64",
                "git": "Git/cmd",
                "nvidia-smi": "NVIDIA Corporation/NVSMI",
            },
        ),
        (
            "ProgramFiles(x86)",
            {"pandoc": "Pandoc", "xelatex": "MiKTeX/miktex/bin", "git": "Git/cmd"},
        ),
        (
            "LOCALAPPDATA",
            {
                "pandoc": "Pandoc",
                "xelatex": "Programs/MiKTeX/miktex/bin/x64",
                "git": "Programs/Git/cmd",
            },
        ),
        ("APPDATA", {"pandoc": "Pandoc"}),
        ("SystemRoot", {"nvidia-smi": "System32"}),
    ):
        if os.environ.get(variable) and name in relative:
            locations.append(Path(os.environ[variable]) / relative[name])
    if name == "xelatex":
        texlive = Path(os.environ.get("SystemDrive", "C:") + "/texlive")
        if texlive.is_dir():
            # Enumerate only release directories at this one known installation location.
            for entry in sorted(texlive.iterdir()):
                if entry.name.isdigit() and len(entry.name) == 4 and entry.is_dir():
                    locations.extend((entry / "bin/windows", entry / "bin/win32"))
    return locations


def discover_tool(name, root=None):
    """Locate one supported tool without executing it or scanning whole drives."""
    _name(name)
    try:
        settings, sources = _settings(root)
        if name in settings["tools"]:
            return _explicit(name, settings["tools"][name], sources[name])
        variable = ENVIRONMENT[name]
        if variable in os.environ:
            return _explicit(name, os.environ[variable], "environment:" + variable)
        executable_dir = Path(sys.executable).resolve().parent
        nearby = _candidates(
            [executable_dir, executable_dir / "Scripts", executable_dir / "bin"],
            name,
            "python-environment",
        )
        if nearby:
            return _result(name, nearby)
        # Search explicit absolute PATH entries in order. Do not inherit Windows'
        # implicit current-directory lookup, or empty/relative PATH entries.
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory or not Path(directory).is_absolute():
                continue
            on_path = _candidates([directory], name, "PATH")
            if on_path:
                return _result(name, on_path[:1])
        if name == "pandoc":
            bundled = _candidates(_bundled_pandoc_dirs(), name, "pypandoc-bundled")
            if bundled:
                return _result(name, bundled)
        extra = []
        for directory in settings["search_dirs"]:
            base = Path(directory)
            extra.extend((base, base / "bin", base / "Scripts", base / "cmd"))
        candidates = _candidates(extra, name, "search_dirs")
        candidates += _registered_candidates(name)
        candidates += _candidates(_known_directories(name), name, "known-installation")
        unique = {os.path.normcase(c["path"]): c for c in candidates}
        return _result(name, list(unique.values()))
    except (FlowError, OSError) as exc:
        return {
            "name": name,
            "status": "invalid",
            "path": None,
            "source": "configuration",
            "candidates": [],
            "detail": str(exc),
        }


def resolve_tool(name, root=None):
    found = discover_tool(name, root)
    if found["status"] != "found":
        paths = ", ".join(candidate["path"] for candidate in found["candidates"])
        raise FlowError(
            f"{name}: {found['status']}. {found['detail']}"
            + (f" Candidates: {paths}" if paths else "")
        )
    return found["path"]


def tool_identity(name, root=None):
    """Opaque identity for artifact manifests; local paths stay out of shared evidence."""
    found = discover_tool(name, root)
    values = []
    for candidate in found["candidates"]:
        path = Path(candidate["path"])
        try:
            stat = path.stat()
            values.append({"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        except OSError:
            values.append({"path": str(path), "missing": True})
    return {"status": found["status"], "identity": identity(values)}


def configure(root=None, tool=None, path=None, search_dir=None, unset=None):
    """Persist only explicit preferences, never discovered paths or shared contest settings."""
    changing = any(value is not None for value in (tool, path, search_dir, unset))
    if (tool is None) != (path is None):
        raise FlowError("Set both tool and path")
    if unset is not None and tool is not None:
        raise FlowError("Choose setting a tool or unsetting it")
    if root is not None:
        root = Path(root)
        if changing:
            require_mutable(root)
        target = local(root, CONFIG_NAME)
    else:
        target = user_config_path()
    settings = _read_settings(target)
    if tool is not None:
        _name(tool)
        found = _explicit(tool, path, "explicit")
        if found["status"] != "found":
            raise FlowError(found["detail"])
        settings["tools"][tool] = found["path"]
    if unset is not None:
        _name(unset)
        settings["tools"].pop(unset, None)
    if search_dir is not None:
        directory = _absolute(search_dir, "search_dir")
        if not directory.is_dir():
            raise FlowError(f"Search directory does not exist: {directory}")
        if str(directory) not in settings["search_dirs"]:
            settings["search_dirs"].append(str(directory))
    if changing:
        write_json(target, settings)
    return {
        "file": str(target),
        "scope": "workspace" if root is not None else "user",
        "settings": settings,
        "written": changing,
    }
