"""Real Pandoc security regressions using only temporary fixtures and loopback HTTP."""

from __future__ import annotations

import base64
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from contestflow import core, paper_resources, project, reporting

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lxoAAAAASUVORK5CYII="
)


@pytest.fixture
def paper(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    project.init(root, "Test paper")
    core.write_text(root / "paper/draft.md", "# Test\n\nSafe manuscript.\n")
    monkeypatch.setattr(
        reporting,
        "require_evidence",
        lambda root: {
            "context_id": "synthetic-evidence",
            "rows": [],
            "context": {"definitions": {"metrics": {}}},
        },
    )
    monkeypatch.setattr(reporting, "selection_current", lambda root: {"table_style": "three-line"})
    try:
        reporting.pandoc_path(root)
    except core.FlowError:
        pytest.skip("A usable Pandoc is required for real paper-resource integration")
    return root


@contextmanager
def loopback():
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(PNG)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/probe.png", hits
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "text",
    [
        "![outside](../outside.svg)",
        "![outside][ref]\n\n[ref]: ../outside.svg",
        "![outside](/outside.png)",
        "![outside](paper/figures/../../outside.png)",
        "![encoded](paper/figures/%2e%2e/outside.png)",
        "![svg](paper/figures/vector.svg)",
        "![pdf](paper/figures/nested.pdf)",
        "![data](data:image/png;base64,AAAA)",
        "<img src='RESOURCE'>",
        "<style>@import url('RESOURCE');</style>",
        "<svg><image href='RESOURCE'/></svg>",
        "```{=html}\n<img src='RESOURCE'>\n```",
        '![attribute](paper/figures/ok.png){style="background:url(RESOURCE)"}',
        "![attribute](paper/figures/ok.png){onload=alert(1)}",
        "---\nbibliography: RESOURCE\n---\n\ntext",
        "---\nheader-includes: |\n  <script src='RESOURCE'></script>\n---\n\ntext",
        r"$\input{../outside.txt}$",
        r"$\csname input\endcsname{../outside.txt}$",
        r"$^^5cinput{../outside.txt}$",
        r"$\begin{document}x\end{document}$",
        r"\input{../outside.txt}",
    ],
)
def test_unsupported_resources_are_rejected_without_network(paper, text):
    (paper.parent / "outside.svg").write_text("<svg>synthetic-private-marker</svg>")
    (paper / "paper/figures/ok.png").write_bytes(PNG)
    with loopback() as (url, hits):
        core.write_text(paper / "paper/draft.md", text.replace("RESOURCE", url))
        with pytest.raises(core.FlowError):
            reporting.build_paper(paper, "html")
        assert hits == []
    assert not (paper / "paper/build/paper.html").exists()


def test_remote_reference_image_is_rejected_before_any_fetch(paper):
    with loopback() as (url, hits):
        core.write_text(paper / "paper/draft.md", "![network][remote]\n\n[remote]: " + url)
        with pytest.raises(core.FlowError, match="external resources"):
            reporting.build_paper(paper, "html")
        assert hits == []


def test_approved_reference_image_and_links_are_offline_and_bound(paper, monkeypatch):
    image = paper / "paper/figures/extra.png"
    image.write_bytes(PNG)
    with loopback() as (url, hits):
        core.write_text(
            paper / "paper/draft.md",
            (
                "# Test\n\n![local][ref]\n\n[ref]: paper/figures/extra.png\n\n"
                + "[ordinary reference]("
                + url
                + ")\n\n"
                + r"Formula: $\min_{\pi} \sum_i c_{i,\pi(i)}$."
                + "\n\n"
                + "```html\n<img src='"
                + url
                + "'>\n```\n\n"
                + "```tex\n\\input{../example-only.tex}\n```\n"
            ),
        )
        reporting.build_paper(paper, "html")
        assert hits == []
    html = (paper / "paper/build/paper.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," + base64.b64encode(PNG).decode() in html
    assert "&lt;" in html and "&gt;" in html
    assert "<img src='http://127.0.0.1:" not in html
    assert 'href="http://127.0.0.1:' in html
    assert reporting.paper_current(paper)
    manifest = core.read_json(paper / "paper/build/manifest.json")
    assert manifest["context"]["inputs"]["paper/figures/extra.png"] == core.digest(image)
    # Currentness is a pure read; status must not execute conversion programs.
    monkeypatch.setattr(
        paper_resources.subprocess, "Popen", lambda *a, **k: pytest.fail("executed")
    )
    assert reporting.paper_current(paper)
    image.write_bytes(PNG + b"synthetic-change")
    assert not reporting.paper_current(paper)


def test_disguised_svg_is_not_accepted_as_raster(paper):
    (paper / "paper/figures/fake.png").write_text("<svg><image href='http://127.0.0.1'/></svg>")
    core.write_text(paper / "paper/draft.md", "![fake](paper/figures/fake.png)")
    with pytest.raises(core.FlowError, match="PNG header"):
        reporting.build_paper(paper)


def test_input_size_count_and_link_limits(paper, monkeypatch):
    monkeypatch.setattr(paper_resources, "MAX_TEXT_BYTES", 1)
    with pytest.raises(core.FlowError, match="exceeds"):
        paper_resources.input_snapshot(paper)
    monkeypatch.setattr(paper_resources, "MAX_TEXT_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(paper_resources, "MAX_FILES", 0)
    (paper / "paper/figures/one.png").write_bytes(PNG)
    with pytest.raises(core.FlowError, match="entries"):
        paper_resources.input_snapshot(paper)


def test_symlink_image_is_rejected(paper):
    target = paper.parent / "outside.png"
    target.write_bytes(PNG)
    link = paper / "paper/figures/link.png"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")
    with pytest.raises(core.FlowError, match="Links"):
        paper_resources.input_snapshot(paper)


def test_user_data_template_and_title_are_not_interpreted_as_instructions(paper, monkeypatch):
    settings = core.config(paper)
    settings["title"] = "<script>title marker</script> \\input{outside}"
    core.write_json(paper / "contest.json", settings)
    for directory in (paper / "appdata/pandoc/templates", paper / "xdg/pandoc/templates"):
        directory.mkdir(parents=True)
        (directory / "default.html5").write_text("UNTRUSTED_USER_TEMPLATE")
    monkeypatch.setenv("APPDATA", str(paper / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(paper / "xdg"))
    reporting.build_paper(paper)
    html = (paper / "paper/build/paper.html").read_text(encoding="utf-8")
    assert "UNTRUSTED_USER_TEMPLATE" not in html
    assert "<script>title marker</script>" not in html
    assert "&lt;script&gt;title marker&lt;/script&gt;" in html


def test_bibliography_links_do_not_fetch_and_content_is_rechecked(paper):
    with loopback() as (url, hits):
        core.write_text(
            paper / "paper/references.bib",
            (
                "@misc{test, title={Synthetic reference}, author={Example, A}, year={2026}, url={"
                + url
                + "}}\n"
            ),
        )
        core.write_text(paper / "paper/draft.md", "# Test\n\nCited source [@test].")
        reporting.build_paper(paper)
        assert hits == []
    assert reporting.paper_current(paper)


@pytest.mark.parametrize(
    "settings",
    [
        {"fontsize": r"11pt}\\input{outside}"},
        {"fontsize": "11pt", "main_font": r"Name}\\input{outside}"},
        {"fontsize": "11pt", "cjk_font": "../font.ttf"},
    ],
)
def test_template_font_parameters_reject_tex_and_paths(settings):
    with pytest.raises(core.FlowError):
        paper_resources.font_settings(settings)


def test_bibliography_cannot_introduce_unsafe_math(paper):
    core.write_text(
        paper / "paper/references.bib",
        r"@misc{test, title={$\input{../outside.txt}$}, author={Example}, year={2026}}",
    )
    core.write_text(paper / "paper/draft.md", "Cited source [@test].")
    with pytest.raises(core.FlowError):
        reporting.build_paper(paper)


def test_malformed_link_has_actionable_error():
    document = {
        "meta": {},
        "blocks": [
            {
                "t": "Para",
                "c": [
                    {
                        "t": "Link",
                        "c": [["", [], []], [{"t": "Str", "c": "source"}], ["http://[", ""]],
                    }
                ],
            }
        ],
    }
    with pytest.raises(core.FlowError, match="link"):
        paper_resources.validate_ast(document)


@pytest.mark.parametrize("name", ["paper/draft.md", "contest.json"])
def test_transient_input_replacement_cannot_match_original_identity(paper, monkeypatch, name):
    original = (paper / name).read_bytes()
    replacement = (
        original.replace(b"Safe manuscript", b"TRANSIENT_SYNTHETIC_REPLACEMENT")
        if name.endswith(".md")
        else original.replace(b"Test paper", b"TRANSIENT_TITLE")
    )
    assert replacement != original
    real_read = paper_resources.Path.read_bytes

    def read_bytes(path):
        if path == paper / name:
            # Simulate reading a temporary replacement whose on-disk bytes were restored.
            assert path.read_text(encoding="utf-8").encode("utf-8") == original
            return replacement
        return real_read(path)

    monkeypatch.setattr(paper_resources.Path, "read_bytes", read_bytes)
    with pytest.raises(core.FlowError, match="input changed"):
        reporting.build_paper(paper)
    assert (paper / name).read_text(encoding="utf-8").encode("utf-8") == original
    assert not (paper / "paper/build/paper.html").exists()
