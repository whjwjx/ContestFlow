"""Restricted manuscript AST and bounded, evidence-bound raster resources.

This policy controls document inputs; it is not an operating-system sandbox.
"""

from __future__ import annotations

import base64
import json
import re
import struct
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .core import FlowError, digest, digest_bytes, local, write_json, write_text
from .runner import child_process_options, kill_tree

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 256
MAX_PIXELS = 40_000_000
# Preserve raw nodes so they can be rejected, instead of silently stripping them.
READER = "markdown+raw_html+raw_tex+raw_attribute-native_divs-native_spans-latex_macros"
MATH_COMMANDS = set(
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda "
    "mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega "
    "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega "
    "frac dfrac tfrac sqrt sum prod coprod int iint iiint oint lim min max inf sup "
    "sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh log ln exp det gcd "
    "Pr ker dim deg arg hom mod bmod pmod "
    "left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr "
    "cdot cdots ldots vdots ddots times div pm mp ast star circ bullet "
    "le leq ge geq ne neq approx sim simeq equiv cong propto ll gg prec succ preceq succeq "
    "in notin ni subset supset subseteq supseteq cup cap setminus emptyset varnothing "
    "forall exists neg land lor wedge vee implies iff to mapsto rightarrow leftarrow "
    "leftrightarrow Rightarrow Leftarrow Leftrightarrow longrightarrow longleftarrow "
    "longleftrightarrow Longrightarrow Longleftarrow Longleftrightarrow uparrow downarrow "
    "infty partial nabla ell hbar Re Im aleph angle perp parallel mid vert Vert "
    "langle rangle lvert rvert lVert rVert lceil rceil lfloor rfloor backslash "
    "hat widehat tilde widetilde bar overline underline vec dot ddot acute grave breve check "
    "overbrace underbrace overset underset stackrel "
    "mathrm mathbf mathit mathsf mathtt mathcal mathbb mathfrak boldsymbol "
    "text textrm textbf textit textsf texttt operatorname "
    "displaystyle textstyle scriptstyle scriptscriptstyle limits nolimits "
    "quad qquad enspace thinspace medspace thickspace negthinspace "
    "begin end tag notag nonumber".split()
)
MATH_ENVIRONMENTS = {
    "matrix",
    "pmatrix",
    "bmatrix",
    "Bmatrix",
    "vmatrix",
    "Vmatrix",
    "smallmatrix",
    "cases",
    "aligned",
    "alignedat",
    "gathered",
    "split",
    "array",
}
NODE_TYPES = set(
    "Plain Para LineBlock CodeBlock BlockQuote OrderedList BulletList DefinitionList Header "
    "HorizontalRule Table Div Figure Null Str Emph Underline Strong Strikeout Superscript "
    "Subscript SmallCaps Quoted Cite Code Space SoftBreak LineBreak Math Link Image Note Span "
    "AlignDefault AlignLeft AlignRight AlignCenter DisplayMath InlineMath DoubleQuote SingleQuote "
    "DefaultStyle Example Decimal LowerRoman UpperRoman LowerAlpha UpperAlpha DefaultDelim "
    "Period OneParen TwoParens ColWidthDefault ColWidth NormalCitation AuthorInText "
    "SuppressAuthor".split()
)


def input_snapshot(root):
    """Read/hash bounded input files without invoking Pandoc or executing any program."""
    paths = [local(root, n) for n in ("paper/draft.md", "paper/references.bib", "contest.json")]
    pending = [local(root, "paper/figures")]
    entries = 0
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            entries += 1
            if entries > MAX_FILES:
                raise FlowError(f"Paper resources exceed {MAX_FILES} entries")
            local(root, path.relative_to(root).as_posix())
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                paths.append(path)
            else:
                raise FlowError("Paper inputs must be regular files")
    result, total = {}, 0
    for path in paths:
        name = path.relative_to(root).as_posix()
        size = path.stat().st_size
        limit = MAX_IMAGE_BYTES if name.startswith("paper/figures/") else MAX_TEXT_BYTES
        if size > limit:
            raise FlowError(f"Paper input exceeds {limit} bytes: {name}")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise FlowError("Paper inputs exceed 64 MiB total")
        result[name] = digest(path)
    return dict(sorted(result.items()))


def read_bound_input(root, name, expected):
    data = local(root, name).read_bytes()
    if digest_bytes(data) != expected:
        raise FlowError(f"Paper input changed during build: {name}")
    return data


def run_pandoc(argv, stage, log, timeout=60):
    process = subprocess.Popen(
        argv,
        cwd=stage,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **child_process_options(),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        kill_tree(process)
        process.communicate()
        raise FlowError("Restricted paper conversion timed out") from exc
    except BaseException:
        kill_tree(process)
        process.communicate()
        raise
    write_text(log, stdout + stderr)
    if process.returncode:
        raise FlowError("Restricted paper conversion failed; inspect paper/build/build.log")
    if re.search(r"not found in bibliography|undefined citation|Missing character", stderr, re.I):
        raise FlowError("Missing references or glyphs; inspect paper/build/build.log")


def _load_ast(path):
    if path.stat().st_size > MAX_TOTAL_BYTES:
        raise FlowError("Parsed manuscript exceeds 64 MiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as exc:
        raise FlowError("Invalid or excessively nested manuscript AST") from exc
    if not isinstance(value, dict) or not isinstance(value.get("blocks"), list):
        raise FlowError("Invalid manuscript AST")
    return value


def _math(value):
    if "^^" in value or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise FlowError("Unsupported TeX control syntax in math")
    for match in re.finditer(r"\\([A-Za-z]+|[^A-Za-z])", value):
        command = match.group(1)
        if command not in MATH_COMMANDS and command not in "\\{}_%#$&|!,;: ":
            raise FlowError(f"Unsupported math command: \\{command}")
        if command in {"begin", "end"}:
            environment = re.match(r"\s*\{([A-Za-z]+)\}", value[match.end() :])
            if not environment or environment.group(1) not in MATH_ENVIRONMENTS:
                raise FlowError("Unsupported math environment")


def _attributes(value):
    identifier, classes, pairs = value
    if identifier and not re.fullmatch(r"[\w:.-]+", identifier):
        raise FlowError("Unsupported manuscript identifier")
    if any(not re.fullmatch(r"[\w-]+", item) for item in classes):
        raise FlowError("Unsupported manuscript class")
    for key, val in pairs:
        if key in {"width", "height"} and re.fullmatch(
            r"[0-9]{1,4}(?:\.[0-9]+)?(?:%|px|pt|cm|mm|in)", val
        ):
            continue
        if key in {"entry-spacing", "line-spacing"} and re.fullmatch(r"[0-9]{1,2}", val):
            continue
        raise FlowError(f"Unsupported manuscript attribute: {key}")


def _is_attribute(value):
    return (
        len(value) == 3
        and isinstance(value[0], str)
        and isinstance(value[1], list)
        and all(isinstance(v, str) for v in value[1])
        and isinstance(value[2], list)
        and all(
            isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v)
            for v in value[2]
        )
    )


def _image_name(value):
    decoded = unquote(value)
    if decoded != value or any(c in value for c in "?#%"):
        raise FlowError("Image paths must be literal workspace-relative paths without URL encoding")
    path = value
    # core.local performs portable path, traversal, and link validation when opening.
    if not path.startswith("paper/figures/") or Path(path).suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
    }:
        raise FlowError(
            "Paper images must be PNG/JPEG files under paper/figures; external resources are disabled"
        )
    return path


def validate_ast(document):
    """Validate parsed nodes, including reference images, notes, tables and citations."""
    if document.get("meta"):
        raise FlowError("Manuscript metadata is disabled; use contest.json for paper settings")
    images = set()
    stack = [(document["blocks"], 0)]
    visited = 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if depth > 128 or visited > 200_000:
            raise FlowError("Manuscript AST exceeds structural limits")
        if isinstance(value, dict):
            kind = value.get("t")
            if kind is not None and kind not in NODE_TYPES:
                raise FlowError(f"Unsupported manuscript node: {kind}; raw HTML/TeX is disabled")
            content = value.get("c")
            if kind == "Image":
                images.add(_image_name(content[-1][0]))
            elif kind == "Link":
                target = content[-1][0]
                try:
                    uri = urlsplit(target)
                except ValueError as exc:
                    raise FlowError("Invalid manuscript link") from exc
                if any(ord(c) < 32 or c in "\\{}" for c in target) or not (
                    target.startswith("#") or uri.scheme in {"http", "https", "mailto"}
                ):
                    raise FlowError("Links must be HTTP(S), mailto, or document anchors")
            elif kind == "Math":
                _math(content[1])
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            if _is_attribute(value):
                _attributes(value)
            stack.extend((v, depth + 1) for v in value)
    return images


def _raster(data, suffix):
    if suffix == ".png":
        if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise FlowError("A PNG resource does not contain a PNG header")
        width, height = struct.unpack(">II", data[16:24])
        mime = "image/png"
    else:
        if not data.startswith(b"\xff\xd8"):
            raise FlowError("A JPEG resource does not contain a JPEG header")
        offset, dimensions = 2, None
        while offset + 4 <= len(data):
            if data[offset] != 0xFF:
                break
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in {0xD9, 0xDA}:
                break
            length = int.from_bytes(data[offset : offset + 2], "big")
            if length < 2 or offset + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2} and length >= 8:
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                dimensions = width, height
                break
            offset += length
        if dimensions is None:
            raise FlowError("JPEG resource needs a supported raster frame")
        width, height = dimensions
        mime = "image/jpeg"
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise FlowError("Paper raster dimensions exceed limits")
    return mime


def prepare_document(root, stage, text, executable, inputs, output_format, log, title):
    """Parse, validate, cite, revalidate, then stage exact approved resource bytes."""
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise FlowError("Resolved manuscript exceeds 2 MiB")
    source = stage / "resolved.md"
    write_text(source, text)
    data_dir = stage / "pandoc-data"
    data_dir.mkdir()
    common = [executable, "--sandbox", "--data-dir=" + str(data_dir)]
    ast_path = stage / "parsed.json"
    run_pandoc(
        common + [str(source), "--from=" + READER, "--to=json", "-o", str(ast_path)], stage, log
    )
    document = _load_ast(ast_path)
    validate_ast(document)
    # Only this explicit bibliography is available to built-in citeproc.
    bibliography = read_bound_input(root, "paper/references.bib", inputs["paper/references.bib"])
    bib_path = stage / "references.bib"
    bib_path.write_bytes(bibliography)
    cited_path = stage / "cited.json"
    run_pandoc(
        common
        + [
            str(ast_path),
            "--from=json",
            "--to=json",
            "--citeproc",
            "--bibliography",
            str(bib_path),
            "-o",
            str(cited_path),
        ],
        stage,
        log,
    )
    document = _load_ast(cited_path)
    # --bibliography adds its own metadata; none is passed to the final writer.
    document["meta"] = {}
    names = validate_ast(document)
    replacements = {}
    for name in sorted(names):
        path = local(root, name)
        if name not in inputs or path.stat().st_size > MAX_IMAGE_BYTES:
            raise FlowError("Image is outside the bounded paper input snapshot")
        data = path.read_bytes()
        if digest_bytes(data) != inputs[name]:
            raise FlowError(f"Image changed during build: {name}")
        suffix = path.suffix.lower()
        mime = _raster(data, suffix)
        target = stage / ("image-" + digest_bytes(data) + suffix)
        target.write_bytes(data)
        replacements[name] = (
            "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
            if output_format == "html"
            else target.name
        )
    stack = [document["blocks"]]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if value.get("t") == "Image":
                value["c"][-1][0] = replacements[value["c"][-1][0]]
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    # MetaString is literal text, not Markdown/raw TeX parsed from a --metadata argument.
    document["meta"] = {"title": {"t": "MetaString", "c": title}}
    safe_path = stage / "approved.json"
    write_json(safe_path, document)
    return safe_path, data_dir


def font_settings(settings):
    if settings.get("fontsize") not in ("10pt", "11pt", "12pt"):
        raise FlowError("Paper fontsize must be 10pt, 11pt or 12pt")
    for key in ("cjk_font", "main_font"):
        value = settings.get(key)
        if value not in (None, "") and (
            not isinstance(value, str) or not re.fullmatch(r"[\w .-]{1,100}", value)
        ):
            raise FlowError(f"Use an installed font family name for {key}, not TeX or a file path")
