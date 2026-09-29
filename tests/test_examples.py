import itertools
import json
import subprocess
import sys

import pytest

from contestflow import core, examples, project

EXPECTED_MATRIX = [[7, 16, 25, 8], [17, 30, 17, 20], [17, 24, 9, 26], [13, 10, 15, 18]]
EXPECTED_IDENTITY = "f517d04a19ce133a5673a051ff32d03d564ee22a56161dff77fc6147f5d08129"


def test_assignment_fixture_has_a_stable_recipe_and_disclosure(tmp_path):
    root = tmp_path / "assignment"
    project.init(root)
    examples.seed_example(root, "assignment")
    data = core.read_json(root / "data/processed/input.json")
    provenance = core.read_json(root / "data/processed/provenance.json")
    assert data == {"costs": EXPECTED_MATRIX}
    assert core.identity(data) == EXPECTED_IDENTITY
    assert provenance["seed"] == 20260929
    assert provenance["canonical_data_sha256"] == EXPECTED_IDENTITY
    assert provenance["input_file_sha256"] == core.digest(root / "data/processed/input.json")
    assert provenance["cost_range_inclusive"] == [1, 30]
    assert "AI-assisted" in core.config(root)["rules"]["source"]
    for name in ("paper/draft.md", "docs/REPRODUCE.md"):
        text = (root / name).read_text(encoding="utf-8")
        assert "20260929" in text and "1664525" in text
        assert "provenance.json" in text
        assert "mathematical originality" in text


def test_assignment_solver_matches_an_independent_enumeration(tmp_path):
    pytest.importorskip("scipy")
    root = tmp_path / "assignment"
    project.init(root)
    examples.seed_example(root, "assignment")
    oracle = min(
        sum(EXPECTED_MATRIX[i][j] for i, j in enumerate(order))
        for order in itertools.permutations(range(4))
    )
    assert oracle == 44
    results = {}
    for method in ("baseline", "improved"):
        output = root / (method + ".json")
        subprocess.run(
            [
                sys.executable,
                str(root / "src/solver.py"),
                "--input",
                str(root / "data/processed/input.json"),
                "--method",
                method,
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
        results[method] = json.loads(output.read_text(encoding="utf-8"))
        assert results[method]["valid"] is True
        assert sorted(results[method]["assignment"]) == [0, 1, 2, 3]
    assert results["baseline"]["metrics"]["cost"] == 66
    assert results["improved"]["metrics"]["cost"] == oracle
    assert results["baseline"]["metrics"]["cost"] > results["improved"]["metrics"]["cost"]
    assert results["improved"]["oracle"] == oracle


def test_forecast_discloses_its_generation_formula(tmp_path):
    root = tmp_path / "forecast"
    project.init(root)
    examples.seed_example(root, "forecast")
    assert "AI-assisted" in core.config(root)["rules"]["source"]
    assert "10 + 0.8*i + 0.4*sin(0.7*i)" in (root / "paper/draft.md").read_text(encoding="utf-8")
