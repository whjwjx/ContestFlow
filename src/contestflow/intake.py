"""Read-only source import and bounded extraction. Imported code is never run."""

from __future__ import annotations

import csv
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .core import (
    FlowError,
    digest,
    journal,
    local,
    read_json,
    require_mutable,
    safe_relative,
    write_json,
    write_text,
)

LIMIT = 256 * 1024 * 1024


def inspect_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        missing = {name: 0 for name in columns}
        count = 0
        for row in reader:
            if count >= 10000:
                return {
                    "columns": columns,
                    "sample_rows": count,
                    "truncated": True,
                    "missing": missing,
                }
            for name in columns:
                missing[name] += int(row.get(name) in (None, ""))
            count += 1
        return {"columns": columns, "sample_rows": count, "truncated": False, "missing": missing}


def extract_docx(path, output):
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > LIMIT:
            raise FlowError("DOCX expanded size exceeds intake limit")
        xml = archive.read("word/document.xml")
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise FlowError("Unexpected DTD in DOCX")
        tree = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = [
            "".join(t.text or "" for t in p.findall(".//w:t", ns))
            for p in tree.findall(".//w:p", ns)
        ]
        write_text(output / "text.md", "\n\n".join(paragraphs))
        images = []
        for info in archive.infolist():
            if info.filename.startswith("word/media/") and not info.is_dir():
                safe_relative(info.filename)
                name = Path(info.filename).name
                if Path(name).suffix.lower() not in (
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".emf",
                    ".wmf",
                ):
                    continue
                target = output / name
                target.write_bytes(archive.read(info))
                images.append(name)
    return {
        "text": "text.md",
        "images": images,
        "visual_review_required": True,
        "note": "Tables are flattened into paragraphs; formulas/diagrams require original document inspection.",
    }


def extract(path, output):
    output.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt", ".json", ".yaml", ".yml"):
        write_text(output / "text.md", path.read_text(encoding="utf-8-sig"))
        return {"text": "text.md", "visual_review_required": False}
    if suffix == ".csv":
        return {"csv_profile": inspect_csv(path), "visual_review_required": False}
    if suffix == ".docx":
        return extract_docx(path, output)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return {
                "status": "optional_dependency_missing",
                "dependency": "contestflow-local[documents]",
                "visual_review_required": True,
            }
        reader = PdfReader(path)
        if len(reader.pages) > 500:
            raise FlowError("PDF exceeds 500-page extraction limit")
        text = []
        for i, page in enumerate(reader.pages, 1):
            text.append(
                f"## Page {i}\n\n{page.extract_text() or '[No text: inspect rendered page]'}"
            )
        write_text(output / "text.md", "\n\n".join(text))
        return {
            "text": "text.md",
            "pages": len(reader.pages),
            "visual_review_required": True,
            "note": "PDF images and formulas must be inspected in the original/rendered pages.",
        }
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return {
                "status": "inventory_only",
                "members": [i.filename for i in archive.infolist()],
                "expanded_bytes": sum(i.file_size for i in archive.infolist()),
                "note": "Archive not extracted or executed. Inspect paths, license and contents first.",
            }
    return {"status": "original_only", "visual_review_required": True}


def intake(root: Path, source: Path):
    require_mutable(root)
    source = source.absolute()
    if (
        not source.exists()
        or source.is_symlink()
        or getattr(source, "is_junction", lambda: False)()
    ):
        raise FlowError("Input missing or a symbolic link/junction")
    if source.is_dir() and root.resolve().is_relative_to(source.resolve()):
        raise FlowError("Source directory contains the workspace; refusing recursive import")
    candidates = [source] if source.is_file() else sorted(source.rglob("*"))
    inputs = []
    for path in candidates:
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise FlowError(f"Source contains a link: {path}")
        if path.is_file():
            inputs.append(path)
    if not inputs or len(inputs) > 2000 or sum(p.stat().st_size for p in inputs) > LIMIT:
        raise FlowError("Intake requires 1-2000 files and at most 256 MiB; split large datasets")
    manifest_path = local(root, "materials/manifest.json")
    manifest = (
        read_json(manifest_path) if manifest_path.exists() else {"schema_version": 1, "files": []}
    )
    known = {item["stored"] for item in manifest["files"]}
    for path in inputs:
        sha = digest(path)
        stored = f"materials/imports/{sha[:16]}/{path.name}"
        target = local(root, stored)
        if stored in known:
            if not target.exists() or digest(target) != sha:
                raise FlowError(f"Previously imported file changed: {stored}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and digest(target) != sha:
            raise FlowError("Import identity collision")
        shutil.copy2(path, target)
        extraction = local(root, f"materials/extracted/{sha[:16]}")
        try:
            details = extract(target, extraction)
        except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
            details = {
                "status": "extraction_failed",
                "error": str(exc),
                "visual_review_required": True,
            }
        manifest["files"].append(
            {
                "stored": stored,
                "original_name": path.name,
                "sha256": sha,
                "bytes": path.stat().st_size,
                "extraction": str(extraction.relative_to(root).as_posix()),
                **details,
            }
        )
        known.add(stored)
    write_json(manifest_path, manifest)
    journal(root, "intake", {"files": len(manifest["files"]), "code_executed": False})
    return manifest
