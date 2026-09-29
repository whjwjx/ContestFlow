"""Fixed small local probes; never loads competition code or arbitrary resource commands."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

from .core import FlowError, digest_bytes, read_json, write_json


def core_probe(settings):
    target = Path("sample.csv")
    target.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert sum(int(row["y"]) for row in rows) == 6
    writable = "not_selected"
    if settings.get("workspace"):
        if settings.get("workspace_frozen"):
            writable = "not_needed_frozen"
        else:
            with tempfile.TemporaryDirectory(
                prefix=".preflight-", dir=settings["workspace"]
            ) as temp:
                path = Path(temp) / "roundtrip.txt"
                path.write_text("环境检查", encoding="utf-8")
                assert path.read_text(encoding="utf-8") == "环境检查"
            writable = "passed"
    return {"csv_roundtrip": True, "workspace_write": writable}


def science_probe(settings):
    import numpy as np
    import scipy
    from scipy.linalg import solve

    matrix = np.array([[3.0, 1.0], [1.0, 2.0]])
    vector = np.array([9.0, 8.0])
    answer = solve(matrix, vector)
    assert np.allclose(matrix @ answer, vector)
    assert np.allclose(answer, [2.0, 3.0])
    return {"numpy": np.__version__, "scipy": scipy.__version__, "linear_system": "passed"}


def plots_probe(settings):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    configured = settings.get("paper", {}).get("cjk_font")
    names = (
        [configured]
        if configured
        else ["Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "SimHei", "PingFang SC"]
    )
    available = {font.name for font in font_manager.fontManager.ttflist}
    family = next((name for name in names if name in available), None)
    if family is None:
        raise FlowError("No selected Chinese font found. Install one or set paper.cjk_font.")
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=r"Glyph .* missing")
        with plt.rc_context(
            {
                "font.family": [family, "DejaVu Sans"],
                "axes.unicode_minus": False,
                "font.size": 11,
                "pdf.fonttype": 42,
            }
        ):
            fig, ax = plt.subplots(figsize=(6, 3), layout="constrained")
            ax.plot([-1, 0, 1], [1, 0, 1], "o-", color="#0072B2", label="示例数据")
            ax.set(xlabel="横轴 / s", ylabel="结果", title="科研绘图检查")
            ax.legend()
            fig.savefig("figure.png", dpi=180)
            fig.savefig("figure.pdf")
            plt.close(fig)
    assert Path("figure.png").stat().st_size > 100
    assert Path("figure.pdf").read_bytes().startswith(b"%PDF")
    return {
        "matplotlib": matplotlib.__version__,
        "font": family,
        "artifacts": ["figure.png", "figure.pdf"],
        "visual_review": "required",
    }


def run_tool(argv):
    result = subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if result.returncode:
        raise FlowError((result.stderr or result.stdout or "Tool exited unsuccessfully")[-6000:])
    return result


def documents_probe(settings, pdf=False):
    tools = settings["tools"]
    version = run_tool([tools["pandoc"], "--version"]).stdout.splitlines()[0]
    Path("sample.md").write_text(
        "# 工具链预演\n\n中文、公式 $x^2 + y^2 = 25$ 与表格。\n\n"
        "| Item | Value |\n|---|---:|\n| Synthetic | 42 |\n\n"
        "本地虚构示例引用，仅测试排版 [@fixture]。\n",
        encoding="utf-8",
    )
    Path("sample.bib").write_text(
        "@misc{fixture, title={Synthetic preflight fixture}, author={ContestFlow}, year={2026}}\n",
        encoding="utf-8",
    )
    target = "sample.pdf" if pdf else "sample.html"
    argv = [
        tools["pandoc"],
        "sample.md",
        "--standalone",
        "--citeproc",
        "--bibliography=sample.bib",
        "-o",
        target,
    ]
    details = {"pandoc": version, "artifacts": [target], "visual_review": "required"}
    if pdf:
        tex_version = run_tool([tools["xelatex"], "--version"]).stdout
        from .paper_resources import font_settings
        from .reporting import paper_font_settings, preflight_pdf_engine_options

        paper = paper_font_settings(
            {"fontsize": "11pt", **settings.get("paper", {})},
            Path("sample.md").read_text(encoding="utf-8"),
        )
        font_settings(paper)
        cjk = paper["cjk_font"]
        argv += [
            "--pdf-engine=" + tools["xelatex"],
            "--pdf-engine-opt=-no-shell-escape",
            "-V",
            "CJKmainfont=" + cjk,
            "-V",
            "geometry:margin=24mm",
        ]
        argv += preflight_pdf_engine_options(tools["xelatex"])
        argv += ["-V", "fontsize=" + paper["fontsize"]]
        main_font = settings.get("paper", {}).get("main_font")
        if main_font:
            argv += ["-V", "mainfont=" + main_font]
        details.update(xelatex=tex_version.splitlines()[0], cjk_font=cjk)
    result = run_tool(argv)
    if any(
        marker in result.stderr.lower()
        for marker in ("missing character", "not found in bibliography", "undefined citation")
    ):
        raise FlowError(result.stderr[-6000:])
    if pdf:
        import pypdf

        reader = pypdf.PdfReader(target)
        assert reader.pages and "42" in "".join(page.extract_text() or "" for page in reader.pages)
        details["pages"] = len(reader.pages)
    else:
        text = Path(target).read_text(encoding="utf-8")
        assert "工具链预演" in text and "42" in text and 'id="ref-fixture"' in text
    return details


def delivery_probe(settings):
    from .release import verify_archive

    members = {
        "data/example.txt": b"42\n",
        "src/check.py": b"from pathlib import Path\nassert Path('data/example.txt').read_text().strip() == '42'\n",
    }
    manifest = {
        "schema_version": 1,
        "members": {
            name: {"sha256": digest_bytes(data), "bytes": len(data)}
            for name, data in members.items()
        },
    }
    with zipfile.ZipFile("sample.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        archive.writestr("MANIFEST.json", json.dumps(manifest))
    verify_archive(Path("sample.zip"))
    extracted = Path("extracted")
    with zipfile.ZipFile("sample.zip") as archive:
        archive.extractall(extracted)
    result = subprocess.run(
        [sys.executable, "src/check.py"], cwd=extracted, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return {"archive_hashes": "passed", "extracted_example": "passed"}


def rehearsal_probe(settings):
    from . import charts, evidence, examples, project, release, reporting, runner, toolchain
    from .core import config

    root = Path("competition-demo").absolute()
    project.init(root, "Synthetic preflight rehearsal")
    examples.seed_example(root, "forecast")
    cfg = config(root)
    cfg["paper"].update(settings.get("paper", {}))
    cfg["package"]["require_pdf"] = settings["format"] == "pdf"
    write_json(root / "contest.json", cfg)
    for name in ("pandoc", "xelatex"):
        if settings["tools"].get(name):
            toolchain.configure(root, tool=name, path=settings["tools"][name])
    for name, value in settings.get("resource_files", {}).items():
        write_json(root / name, value)
    records = runner.run(root, allow_exec=True)
    assert all(record["status"] == "success" for record in records)
    evidence.compare(root)
    charts.charts(root)
    reporting.build_paper(root, settings["format"])
    release.package(root)
    checked = release.verify(root, smoke=True, allow_exec=True)
    assert checked["smoke"]["status"] == "passed"
    return {
        "purpose": "synthetic_toolchain_rehearsal",
        "format": settings["format"],
        "archive_smoke": "passed",
        "human_review": "not_asserted",
        "visual_review": "required",
        "workspace": "competition-demo",
    }


def main():
    name, source = sys.argv[1:]
    settings = read_json(Path(source))
    probes = {
        "core": core_probe,
        "science": science_probe,
        "plots": plots_probe,
        "documents-html": documents_probe,
        "documents-pdf": lambda s: documents_probe(s, pdf=True),
        "delivery": delivery_probe,
        "rehearsal": rehearsal_probe,
        "gpu": lambda s: {
            "driver_query": run_tool(
                [
                    s["tools"]["nvidia-smi"],
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader",
                ]
            ).stdout.strip(),
            "note": "Driver query only; framework/CUDA workloads are not tested.",
        },
    }
    detail = probes[name](settings)
    write_json(Path("result.local.json"), {"passed": True, **detail})


if __name__ == "__main__":
    main()
