"""One Markdown source, evidence substitutions, Pandoc builds, content identities."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .charts import selection_current
from .core import (
    FlowError,
    config,
    digest,
    identity,
    journal,
    local,
    read_json,
    require_mutable,
    snapshot,
    write_json,
    write_text,
)
from .evidence import require_evidence


def pandoc_path():
    found = os.environ.get("PANDOC") or shutil.which("pandoc")
    if found and Path(found).is_file():
        return found
    try:
        import pypandoc

        return pypandoc.get_pandoc_path()
    except (ImportError, OSError) as exc:
        raise FlowError(
            "Pandoc missing. Install [documents], or set PANDOC to its executable."
        ) from exc


def paper_context(root):
    evidence = require_evidence(root)
    selection = selection_current(root)
    inputs = snapshot(
        root, ["paper/draft.md", "paper/references.bib", "paper/figures", "contest.json"]
    )
    return {
        "inputs": inputs,
        "evidence_id": evidence["context_id"],
        "selection": selection,
        "builder": digest(Path(__file__)),
    }


def paper_current(root):
    path = local(root, "paper/build/manifest.json")
    try:
        record = read_json(path)
        return (
            record["context_id"] == identity(paper_context(root))
            and bool(record["artifacts"])
            and all(digest(local(root, name)) == sha for name, sha in record["artifacts"].items())
        )
    except (FlowError, OSError, KeyError):
        return False


def resolved_markdown(root):
    evidence = require_evidence(root)
    rows = {row["experiment"]: row for row in evidence["rows"]}
    metrics = evidence["context"]["definitions"]["metrics"]
    text = local(root, "paper/draft.md").read_text(encoding="utf-8")
    if re.search(r"\b(TODO|TBD|PLACEHOLDER)\b", text, re.I):
        raise FlowError("Manuscript still contains TODO/TBD/PLACEHOLDER")

    def number(match):
        experiment, metric = match.group(1), match.group(2)
        if experiment not in rows or metric not in metrics:
            raise FlowError(f"Unknown evidence reference: {match.group(0)}")
        return format(rows[experiment][metric], ".6g")

    text = re.sub(r"\{\{metric:([A-Za-z0-9_-]+):([A-Za-z0-9_-]+)\}\}", number, text)
    table = [
        "| Experiment | "
        + " | ".join(f"{s['label']} ({s['unit']})" for s in metrics.values())
        + " |",
        "|---|" + "---:|" * len(metrics),
    ]
    for name, row in rows.items():
        table.append(
            "| " + name + " | " + " | ".join(format(row[k], ".6g") for k in metrics) + " |"
        )
    text = text.replace("{{table:comparison}}", "\n".join(table))
    figures = [
        f"![{spec['label']}](paper/figures/{name}.png){{width=90%}}"
        for name, spec in metrics.items()
    ]
    text = text.replace("{{figures}}", "\n\n".join(figures))
    if re.search(r"\{\{[^{}]+\}\}", text):
        raise FlowError("Unresolved manuscript template expression")
    return text


def build_paper(root, output_format="html"):
    require_mutable(root)
    if output_format not in ("html", "pdf"):
        raise FlowError("Supported paper formats: html, pdf")
    ctx = paper_context(root)
    context_id = identity(ctx)
    text = resolved_markdown(root)
    executable = pandoc_path()
    settings = config(root)["paper"]
    build_dir = local(root, "paper/build")
    build_dir.mkdir(parents=True, exist_ok=True)
    previous_path = build_dir / "manifest.json"
    previous = read_json(previous_path) if previous_path.exists() else {}
    artifacts = previous.get("artifacts", {}) if paper_current(root) else {}
    with tempfile.TemporaryDirectory(prefix="compile-", dir=build_dir) as temp:
        stage = Path(temp)
        source = stage / "resolved.md"
        write_text(source, text)
        target = stage / ("paper." + output_format)
        argv = [
            executable,
            str(source),
            "--from=markdown",
            "--standalone",
            "--citeproc",
            "--resource-path",
            str(root),
            "--bibliography",
            str(root / "paper/references.bib"),
            "--metadata",
            "title=" + config(root)["title"],
            "-o",
            str(target),
        ]
        if output_format == "pdf":
            engine = shutil.which("xelatex")
            if not engine:
                raise FlowError("XeLaTeX missing; install a TeX distribution or build HTML first")
            argv += [
                "--pdf-engine=" + engine,
                "--pdf-engine-opt=-no-shell-escape",
                "-V",
                "geometry:margin=24mm",
                "-V",
                "fontsize=" + settings["fontsize"],
            ]
            for key, variable in (("cjk_font", "CJKmainfont"), ("main_font", "mainfont")):
                if settings.get(key):
                    argv += ["-V", variable + "=" + settings[key]]
            if ctx["selection"]["table_style"] == "striped":
                header = stage / "table.tex"
                write_text(
                    header,
                    "\\usepackage{colortbl}\n\\usepackage{etoolbox}\n"
                    "\\definecolor{tablerow}{HTML}{EEF4F1}\n"
                    "\\AtBeginEnvironment{longtable}{\\rowcolors{2}{tablerow}{white}}\n",
                )
                argv += ["--include-in-header", str(header)]
        else:
            argv += ["--embed-resources"]
            css = stage / "paper.css"
            write_text(
                css,
                "body{max-width:820px;margin:40px auto;padding:0 24px;font:16px/1.75 Georgia,'Microsoft YaHei',serif;color:#222}"
                "img{max-width:100%;height:auto}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccc}"
                "thead{border-top:2px solid #222;border-bottom:1px solid #222}"
                + (
                    "tbody tr:nth-child(even){background:#eef4f1}"
                    if ctx["selection"]["table_style"] == "striped"
                    else ""
                ),
            )
            argv += ["--css", str(css)]
        options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = subprocess.Popen(
            argv,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **options,
        )
        try:
            stdout, stderr = process.communicate(timeout=180)
        except subprocess.TimeoutExpired as exc:
            from .runner import kill_tree

            kill_tree(process)
            stdout, stderr = process.communicate()
            write_text(build_dir / "build.log", stdout + stderr)
            raise FlowError("Paper build timed out after 180 seconds") from exc
        result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        write_text(build_dir / "build.log", result.stdout + result.stderr)
        if result.returncode or not target.is_file():
            raise FlowError("Paper build failed; inspect paper/build/build.log")
        if re.search(
            r"not found in bibliography|undefined citation|Missing character", result.stderr, re.I
        ):
            raise FlowError("Missing references or glyphs; inspect paper/build/build.log")
        if identity(paper_context(root)) != context_id:
            raise FlowError("Paper inputs changed during build")
        final = build_dir / target.name
        os.replace(target, final)
        write_text(build_dir / "resolved.md", text)
    artifacts[final.relative_to(root).as_posix()] = digest(final)
    artifacts["paper/build/resolved.md"] = digest(build_dir / "resolved.md")
    record = {
        "schema_version": 1,
        "context_id": context_id,
        "context": ctx,
        "artifacts": artifacts,
        "visual_review": "required",
        "human_review": "not_asserted",
    }
    write_json(previous_path, record)
    journal(root, "paper_build", {"format": output_format, "context_id": context_id})
    return {"file": str(final), "sha256": digest(final), "visual_review": "required"}
