"""Public-domain-style synthetic fixtures; no competition assets are copied."""

from __future__ import annotations

import math

from .core import config, local, require_mutable, write_json, write_text
from .intake import intake
from .project import template


def seed_example(root, kind):
    require_mutable(root)
    if kind not in ("assignment", "forecast"):
        raise ValueError("Unknown example")
    cfg = config(root)
    cfg["example"] = kind
    cfg["title"] = (
        "Synthetic assignment study" if kind == "assignment" else "Synthetic temporal forecast"
    )
    cfg["rules"]["source"] = "Self-authored synthetic example; not a competition rule profile"
    cfg["package"]["include"] += ["data/processed"]
    cfg["package"]["smoke"] = {
        "command": [
            "{python}",
            "src/solver.py",
            "--input",
            "data/processed/input.json",
            "--method",
            "improved",
            "--output",
            "smoke-result.json",
        ],
        "result": "smoke-result.json",
        "timeout_seconds": 60,
    }
    write_json(local(root, "contest.json"), cfg)
    write_text(local(root, "src/solver.py"), template(kind + ".py.txt"))
    if kind == "assignment":
        data = {"costs": [[9, 2, 7, 8], [6, 4, 3, 7], [5, 8, 1, 8], [7, 6, 9, 4]]}
        metric = "cost"
        spec = {
            "label": "Total cost",
            "unit": "cost units",
            "direction": "min",
            "definition": "Sum of original matrix costs over a valid one-to-one assignment",
            "aggregation": "One synthetic instance; not an across-instance mean",
        }
        statement = "# Synthetic assignment\n\nAssign four workers to four tasks, one each, minimizing the supplied cost matrix. Compare greedy and exact baselines. Verify feasibility and the small-instance optimum independently.\n"
        method = "The baseline selects the lowest-cost available task in row order. The improved method calls SciPy's linear_sum_assignment. A separate exhaustive permutation check is used only as a four-item oracle.\n\nThe objective is $\\min_{\\pi} \\sum_i c_{i,\\pi(i)}$, where $\\pi$ is a permutation."
        scope = "Only one synthetic instance is evaluated. No runtime scalability or competition performance claim follows."
        reference = "[SciPy linear_sum_assignment documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)"
        packages = ["scipy", "numpy"]
    else:
        data = {"values": [10 + 0.8 * i + 0.4 * math.sin(i * 0.7) for i in range(60)], "split": 45}
        metric = "rmse"
        spec = {
            "label": "Holdout RMSE",
            "unit": "series units",
            "direction": "min",
            "definition": "sqrt(mean((prediction - observed)^2)) on chronological indices 45-59",
            "aggregation": "15 held-out timestamps; coefficients fit only on indices 0-44",
        }
        statement = "# Synthetic forecast\n\nFit on timestamps 0-44 only and predict 45-59. Compare a last-value baseline with a linear trend. Report chronological holdout RMSE without training on the holdout.\n"
        method = "The baseline repeats the final training observation. The trend coefficients are fitted with NumPy least squares using only timestamps 0-44. Prediction is evaluated on 45-59. The split is specified before either model is evaluated."
        scope = "This is one synthetic chronological holdout, not rolling validation. It does not demonstrate real-world generalization or uncertainty calibration."
        reference = "[NumPy least-squares documentation](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html)"
        packages = ["numpy"]
    write_json(local(root, "data/processed/input.json"), data)
    statement_path = local(root, "docs/synthetic-problem.md")
    write_text(statement_path, statement)
    imported = intake(root, statement_path)
    write_json(
        local(root, "plans/requirements.json"),
        {
            "schema_version": 1,
            "items": [
                {
                    "id": "Q1",
                    "question": statement,
                    "source": imported["files"][0]["stored"],
                    "acceptance": "Two feasible runs, defined metric, independent validation and honest scope",
                }
            ],
        },
    )
    write_json(
        local(root, "evidence/metrics.json"), {"schema_version": 1, "metrics": {metric: spec}}
    )
    specs = []
    for name in ("baseline", "improved"):
        specs.append(
            {
                "id": name,
                "command": [
                    "{python}",
                    "{workspace}/src/solver.py",
                    "--input",
                    "{workspace}/data/processed/input.json",
                    "--method",
                    name,
                    "--output",
                    "{run_dir}/result.json",
                ],
                "inputs": ["src/solver.py", "data/processed/input.json"],
                "outputs": ["result.json"],
                "packages": packages,
                "timeout_seconds": 60,
            }
        )
    write_json(local(root, "configs/experiments.json"), {"schema_version": 1, "experiments": specs})
    draft = (
        f"# Problem and Scope\n\n{statement.split(chr(10), 2)[-1]}\n\n"
        f"# Method\n\n{method}\n\n# Results\n\n"
        f"The baseline value is {{{{metric:baseline:{metric}}}}}; the improved value is {{{{metric:improved:{metric}}}}}. "
        "Both values are substituted from successful, fingerprint-verified experiments.\n\n"
        "{{table:comparison}}\n\n{{figures}}\n\n"
        f"# Limitations\n\n{scope}\n\n# Reproducibility and Assistance\n\n"
        "This is a synthetic software demonstration, not a contest submission. The example and workflow were prepared with AI assistance. "
        "Automated checks do not constitute human scientific review. Real competitions require their own verified rules and actual-use disclosure.\n\n"
        f"# Method Reference\n\n{reference}\n"
    )
    write_text(local(root, "paper/draft.md"), draft)
    write_text(
        local(root, "docs/REPRODUCE.md"),
        "# Reproduce the packaged example\n\nInstall Python 3.11+ and "
        + ", ".join(packages)
        + ".\n\n"
        "```sh\npython src/solver.py --input data/processed/input.json --method improved --output result.json\n```\n\n"
        "Inspect result.json for feasibility and metrics. This smoke does not rerun every experiment.\n",
    )
    return {"example": kind, "workspace": str(root)}
