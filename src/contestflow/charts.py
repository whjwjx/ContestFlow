"""Evidence-bound scientific variants and a fully offline review page."""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

from .core import (
    FlowError,
    config,
    digest,
    identity,
    journal,
    local,
    read_json,
    require_mutable,
    safe_name,
    write_json,
    write_text,
)
from .evidence import require_evidence
from .project import template
from .resources import palette_colors, palette_context

# Kept for callers that use the original default palette mapping.
PALETTES = palette_colors()


def render(root, evidence, metric, kind, palette, output):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError as exc:
        raise FlowError("Install contestflow-local[science] to render figures") from exc
    spec = evidence["context"]["definitions"]["metrics"][metric]
    rows = evidence["rows"]
    values = [row[metric] for row in rows]
    labels = ["\n".join(textwrap.wrap(row["experiment"], 24)) for row in rows]
    available = {font.name for font in font_manager.fontManager.ttflist}
    configured_font = config(root).get("paper", {}).get("cjk_font", "")
    if configured_font and configured_font not in available:
        raise FlowError(f"Configured figure font is unavailable: {configured_font}")
    preferred = configured_font or next(
        (
            name
            for name in (
                "Noto Sans CJK SC",
                "Source Han Sans SC",
                "Microsoft YaHei",
                "SimHei",
                "PingFang SC",
            )
            if name in available
        ),
        "DejaVu Sans",
    )
    with plt.rc_context(
        {
            "font.family": [preferred, "DejaVu Sans"],
            "font.size": 11,
            "axes.unicode_minus": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    ):
        fig, ax = plt.subplots(figsize=(7.2, max(3.2, len(rows) * 0.55)), layout="constrained")
        selected_colors = palette_colors(root)[palette]
        colors = [selected_colors[i % len(selected_colors)] for i in range(len(rows))]
        if kind == "bar":
            ax.barh(labels, values, color=colors, height=0.56)
        else:
            ax.scatter(values, labels, c=colors, s=72, zorder=3)
            ax.grid(axis="x", color="#DEDEDE", linewidth=0.6)
        ax.set_xlabel(f"{spec['label']} ({spec['unit']})")
        ax.invert_yaxis()
        ax.margins(x=0.15)
        if kind == "bar" and min(values) >= 0:
            ax.set_xlim(left=0)
        for y, value in enumerate(values):
            ax.annotate(
                f"{value:.5g}",
                (value, y),
                xytext=(7, 0),
                textcoords="offset points",
                va="center",
                fontsize=10,
            )
        fig.savefig(output.with_suffix(".png"), dpi=180)
        fig.savefig(output.with_suffix(".pdf"), metadata={"CreationDate": None, "ModDate": None})
        plt.close(fig)


def _font_context(root):
    return {"cjk_font": config(root).get("paper", {}).get("cjk_font", "")}


def review_current(root):
    data = read_json(local(root, "reviews/manifest.json"))
    if data.get("review_id") != identity({k: v for k, v in data.items() if k != "review_id"}):
        raise FlowError("Review manifest changed; regenerate it")
    evidence = require_evidence(root)
    if data["evidence_id"] != evidence["context_id"] or data["renderer"] != digest(Path(__file__)):
        raise FlowError("Figure review is stale; regenerate charts and choose again")
    if data.get("resources") != palette_context(root):
        raise FlowError("Figure resources changed; regenerate charts and choose again")
    if data.get("font_config") != _font_context(root):
        raise FlowError("Figure font configuration changed; regenerate charts and choose again")
    for name, sha in data["artifacts"].items():
        if digest(local(root, name)) != sha:
            raise FlowError(f"Review image changed: {name}")
    return data


def apply_selection(root, selection, origin="imported-file"):
    require_mutable(root)
    review = review_current(root)
    if selection.get("review_id") != review["review_id"]:
        raise FlowError("Selection belongs to a different review/data version")
    choices = selection.get("choices", {})
    if set(choices) != set(review["metrics"]):
        raise FlowError("Selection must cover exactly the current metric figures")
    style = selection.get("table_style", "three-line")
    if style not in ("three-line", "striped"):
        raise FlowError("Unknown table style")
    staged = []
    for metric, variant_id in choices.items():
        item = next(
            (x for x in review["variants"] if x["id"] == variant_id and x["metric"] == metric), None
        )
        if item is None:
            raise FlowError(f"Unknown variant for {metric}")
        staged.append((metric, item))
    artifacts = {}
    for metric, item in staged:
        for extension in ("png", "pdf"):
            target = local(root, f"paper/figures/{metric}.{extension}")
            shutil.copy2(local(root, item[extension]), target)
            artifacts[target.relative_to(root).as_posix()] = digest(target)
    record = {
        "schema_version": 1,
        "review_id": review["review_id"],
        "choices": choices,
        "table_style": style,
        "origin": origin,
        "human_review": "not_asserted",
        "artifacts": artifacts,
    }
    write_json(local(root, "reviews/selection.json"), record)
    journal(root, "figure_selection", {"origin": origin, "review_id": review["review_id"]})
    return record


def selection_current(root):
    review = review_current(root)
    choice = read_json(local(root, "reviews/selection.json"))
    if choice["review_id"] != review["review_id"]:
        raise FlowError("Selection stale")
    if set(choice.get("choices", {})) != set(review["metrics"]):
        raise FlowError("Selection does not cover the current figures")
    expected = {}
    for metric, variant_id in choice["choices"].items():
        variant = next(
            (v for v in review["variants"] if v["metric"] == metric and v["id"] == variant_id), None
        )
        if variant is None:
            raise FlowError("Selection references an unknown variant")
        for ext in ("png", "pdf"):
            expected[f"paper/figures/{metric}.{ext}"] = review["artifacts"][variant[ext]]
    if choice.get("artifacts") != expected:
        raise FlowError("Selected figure bytes do not match the chosen variants")
    for name, sha in choice["artifacts"].items():
        if digest(local(root, name)) != sha:
            raise FlowError("Integrated figure changed; reselect and rebuild")
    return choice


def charts(root):
    require_mutable(root)
    evidence = require_evidence(root)
    metrics = evidence["context"]["definitions"]["metrics"]
    palettes = palette_colors(root)
    resources = palette_context(root)
    folder = local(root, "reviews/images")
    folder.mkdir(parents=True, exist_ok=True)
    review = {
        "schema_version": 1,
        "evidence_id": evidence["context_id"],
        "renderer": digest(Path(__file__)),
        "resources": resources,
        "font_config": _font_context(root),
        "metrics": metrics,
        "variants": [],
        "artifacts": {},
    }
    for metric in metrics:
        safe_name(metric)
        for kind in ("bar", "dot"):
            for palette in palettes:
                name = f"{metric}-{kind}-{palette}"
                render(root, evidence, metric, kind, palette, folder / name)
                item = {"id": name, "metric": metric, "kind": kind, "palette": palette}
                for ext in ("png", "pdf"):
                    path = folder / f"{name}.{ext}"
                    relative = path.relative_to(root).as_posix()
                    item[ext] = relative
                    review["artifacts"][relative] = digest(path)
                review["variants"].append(item)
    review["review_id"] = identity(review)
    write_json(local(root, "reviews/manifest.json"), review)
    payload = {**review, "rows": evidence["rows"]}
    body = template("review.html").replace(
        "__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    )
    write_text(local(root, "reviews/index.html"), body)
    first_palette = next(iter(palettes))
    first = {metric: f"{metric}-bar-{first_palette}" for metric in metrics}
    if not local(root, "reviews/selection.json").exists():
        apply_selection(
            root, {"review_id": review["review_id"], "choices": first}, "automatic-default"
        )
    journal(root, "charts", {"variants": len(review["variants"]), "review_id": review["review_id"]})
    return {"page": str(root / "reviews/index.html"), "review_id": review["review_id"]}
