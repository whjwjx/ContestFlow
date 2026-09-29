"""Portable, declarative tools and palettes; selection never installs or executes code."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from .core import FlowError, identity, journal, local, read_json, require_mutable, write_json

CHECK_IDS = frozenset(
    {"core", "science", "plots", "documents-html", "documents-pdf", "delivery", "gpu"}
)
DEFAULT_PALETTES = ("palette.journal", "palette.contrast", "palette.mono")
COMMON_FIELDS = {
    "id",
    "kind",
    "title",
    "source_url",
    "purpose",
    "requirements",
    "checks",
    "reuse",
    "status",
}


def _validate(data, label):
    if not isinstance(data, dict) or set(data) != {"schema_version", "resources"}:
        raise FlowError(f"{label} must contain schema_version and resources")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise FlowError(f"Unsupported {label} schema_version")
    if not isinstance(data["resources"], list):
        raise FlowError(f"{label} resources must be a list")
    ids = set()
    for item in data["resources"]:
        if not isinstance(item, dict) or not COMMON_FIELDS <= set(item):
            raise FlowError(f"{label} resource is missing required fields")
        if set(item) - COMMON_FIELDS - {"colors"}:
            raise FlowError(f"{label} resource contains unsupported fields")
        resource_id = item["id"]
        if not isinstance(resource_id, str) or not re.fullmatch(
            r"(?:tool|palette)\.[a-z0-9][a-z0-9_-]{0,47}", resource_id
        ):
            raise FlowError(f"Invalid resource id: {resource_id!r}")
        if resource_id in ids:
            raise FlowError(f"Duplicate resource id: {resource_id}")
        ids.add(resource_id)
        if item["kind"] not in ("tool", "palette") or not resource_id.startswith(
            item["kind"] + "."
        ):
            raise FlowError(f"Resource kind must agree with id: {resource_id}")
        for field in ("title", "source_url", "purpose", "reuse", "status"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise FlowError(f"Resource {resource_id} needs nonempty {field}")
        try:
            source = urlsplit(item["source_url"])
            valid_source = source.scheme in ("https", "http") and source.hostname
        except ValueError:
            valid_source = False
        if not valid_source:
            raise FlowError(f"Resource {resource_id} needs an HTTP(S) source_url")
        if item["status"] not in ("collected", "tested", "project_used"):
            raise FlowError(f"Invalid resource status: {resource_id}")
        for field in ("requirements", "checks"):
            values = item[field]
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise FlowError(f"Resource {resource_id} {field} must be a list of strings")
            if len(set(values)) != len(values):
                raise FlowError(f"Resource {resource_id} has duplicate {field}")
        if set(item["checks"]) - CHECK_IDS:
            raise FlowError(f"Resource {resource_id} contains unknown check IDs")
        if item["kind"] == "palette":
            colors = item.get("colors")
            if (
                not isinstance(colors, list)
                or not 1 <= len(colors) <= 12
                or any(
                    not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                    for color in colors
                )
            ):
                raise FlowError(f"Palette {resource_id} needs 1-12 hexadecimal colors")
        elif "colors" in item:
            raise FlowError(f"Tool {resource_id} cannot define colors")
    return data["resources"]


def catalog(root: Path | None = None):
    """Return bundled resources plus a workspace's validated, shareable additions."""
    bundled = json.loads(
        files("contestflow").joinpath("templates", "resources.json").read_text(encoding="utf-8")
    )
    entries = list(_validate(bundled, "bundled catalog"))
    if root is not None:
        custom = local(root, "configs/resource-library.json")
        if custom.exists():
            entries.extend(_validate(read_json(custom), "configs/resource-library.json"))
    combined = {"schema_version": 1, "resources": entries}
    _validate(combined, "combined catalog")
    return combined


def _selection(root):
    path = local(root, "configs/resources.json")
    if not path.exists():
        return []
    data = read_json(path)
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "selected"}
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise FlowError("configs/resources.json needs schema_version 1 and selected")
    return _check_selection(data["selected"], catalog(root))


def _check_selection(ids, data):
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
        raise FlowError("Selected resource IDs must be a list of strings")
    if len(set(ids)) != len(ids):
        raise FlowError("Selected resource IDs must be unique")
    known = {item["id"] for item in data["resources"]}
    missing = set(ids) - known
    if missing:
        raise FlowError(f"Unknown selected resource IDs: {', '.join(sorted(missing))}")
    return ids


def select_resources(root: Path, ids: list[str]):
    """Save the complete explicit choice, preserving figure choices until re-review."""
    require_mutable(root)
    ids = _check_selection(ids, catalog(root))
    record = {"schema_version": 1, "selected": ids}
    write_json(local(root, "configs/resources.json"), record)
    journal(root, "resource_selection", {"selected": ids, "human_review": "not_asserted"})
    return record


def selected_resources(root: Path):
    entries = {item["id"]: item for item in catalog(root)["resources"]}
    return [entries[resource_id] for resource_id in _selection(root)]


def selected_checks(root: Path):
    return sorted({check for item in selected_resources(root) for check in item["checks"]})


def palette_resources(root: Path | None = None):
    """No explicit palette choice preserves the original three chart variants."""
    selected = selected_resources(root) if root is not None else []
    palettes = [item for item in selected if item["kind"] == "palette"]
    if palettes:
        return palettes
    entries = {item["id"]: item for item in catalog(root)["resources"]}
    return [entries[resource_id] for resource_id in DEFAULT_PALETTES]


def palette_context(root: Path | None = None):
    definitions = palette_resources(root)
    return {"definitions": definitions, "definitions_id": identity(definitions)}


def palette_colors(root: Path | None = None):
    return {item["id"].removeprefix("palette."): item["colors"] for item in palette_resources(root)}
