"""LibreOffice markup/final page renders (plan §17.3)."""

from __future__ import annotations

import copy

import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from redline_guard.ooxml import enable_track_revisions, load_docx, q, w_attr
from redline_guard.resolution_log import DEFAULT_AUTHOR
from redline_guard.resolve import clean_docx, list_revisions

SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
]
PAGE_NUMBER = re.compile(r"^\d+$")


@dataclass
class RenderFailure:
    kind: str
    location: str
    story: str
    paragraph: int
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Page:
    number: int
    image: str
    final_image: str
    before_image: str
    diff_image: str
    changed_fraction: float | None
    sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RenderReport:
    ok: bool
    pages: list[Page] = field(default_factory=list)
    page_count: int = 0
    final_page_count: int = 0
    original_page_count: int = 0
    failures: list[RenderFailure] = field(default_factory=list)
    markup_text: str = ""
    final_text: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "pages": [p.to_dict() for p in self.pages],
            "page_count": self.page_count,
            "final_page_count": self.final_page_count,
            "original_page_count": self.original_page_count,
            "failures": [f.to_dict() for f in self.failures],
            "markup_text": self.markup_text,
            "final_text": self.final_text,
        }


def renderer_available() -> dict[str, str | None]:
    runtime = Path(sys.executable).resolve().parents[2]
    bundled_lo = runtime / "native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS/soffice"
    bundled_poppler = runtime / "native/poppler/poppler/bin"
    return {
        "soffice": _find_tool("REDLINE_SOFFICE", "soffice", [str(bundled_lo), *SOFFICE_CANDIDATES]),
        "pdftoppm": _find_tool("REDLINE_PDFTOPPM", "pdftoppm", [str(bundled_poppler / "pdftoppm")]),
        "pdftotext": _find_tool("REDLINE_PDFTOTEXT", "pdftotext", [str(bundled_poppler / "pdftotext")]),
    }


def render_docx(
    path: str | Path,
    out_dir: str | Path,
    original: str | Path | None = None,
    author: str = DEFAULT_AUTHOR,
) -> RenderReport:
    report = RenderReport(ok=True)
    out_dir = Path(out_dir).resolve()
    tools = renderer_available()
    missing = [name for name, loc in tools.items() if not loc or not Path(loc).exists()]
    if missing:
        names = ", ".join(missing)
        report.ok = False
        report.failures.append(
            RenderFailure(
                kind="renderer_missing",
                location="",
                story="",
                paragraph=0,
                message=f"{names} not found. Install LibreOffice and poppler, or set REDLINE_SOFFICE / REDLINE_PDFTOPPM / REDLINE_PDFTOTEXT.",
            )
        )
        return report

    out_dir.mkdir(parents=True, exist_ok=True)
    # A reused QA directory must not keep images from an earlier, longer file.
    prior = out_dir / "pages.json"
    if prior.exists():
        import json
        try:
            previous = json.loads(prior.read_text())
            for page in previous.get("pages", []):
                for field in ("image", "final_image", "before_image", "diff_image"):
                    old = page.get(field)
                    if not old:
                        continue
                    target = Path(old).resolve()
                    if target.parent != out_dir or not re.fullmatch(r"page-\d+(?:\.final|\.before|\.diff)?\.png", target.name):
                        raise ValueError("Previous page manifest points outside its QA directory.")
                    target.unlink(missing_ok=True)
            prior.unlink()
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            report.ok = False
            report.failures.append(RenderFailure("render_failed", "", "", 0, f"Cannot safely reuse page directory: {exc}"))
            return report
    elif any(out_dir.iterdir()):
        report.ok = False
        report.failures.append(RenderFailure("render_failed", "", "", 0, "Page directory is not empty and has no page manifest; choose a new directory."))
        return report
    work = Path(tempfile.mkdtemp(prefix="redline_render_", dir=str(out_dir)))
    try:
        jobs = _prepare_sources(path, original, work)
        pdfs = _convert(tools["soffice"], jobs, work, report)
        if report.failures:
            report.ok = False
            return report
        markup_pdf = pdfs["markup"]
        final_pdf = pdfs["final"]
        before_pdf = pdfs.get("before")
        markup_pngs = _raster(tools["pdftoppm"], markup_pdf, work / "markup", 110)
        final_pngs = _raster(tools["pdftoppm"], final_pdf, work / "final", 110)
        before_pngs = _raster(tools["pdftoppm"], before_pdf, work / "before", 110) if before_pdf else []
        markup_gray = _raster_gray(tools["pdftoppm"], markup_pdf, work / "markup_g", 50)
        before_gray = _raster_gray(tools["pdftoppm"], before_pdf, work / "before_g", 50) if before_pdf else []
        report.page_count = len(markup_pngs)
        report.final_page_count = len(final_pngs)
        report.original_page_count = len(before_pngs)
        if not markup_pngs or not final_pngs or (original is not None and not before_pngs):
            raise ValueError("Renderer produced no pages for a required view.")
        report.markup_text = _extract_text(tools["pdftotext"], markup_pdf, path)
        report.final_text = _extract_text(tools["pdftotext"], final_pdf, path)
        full_markup = _extract_text(tools["pdftotext"], markup_pdf, path, exclude_headers=False)
        full_final = _extract_text(tools["pdftotext"], final_pdf, path, exclude_headers=False)
        pages: list[Page] = []
        for i in range(1, max(len(markup_pngs), len(final_pngs), len(before_pngs)) + 1):
            src = markup_pngs[i - 1] if i <= len(markup_pngs) else None
            image = out_dir / f"page-{i:02d}.png"
            final_image = out_dir / f"page-{i:02d}.final.png"
            before_image = out_dir / f"page-{i:02d}.before.png"
            diff_image = out_dir / f"page-{i:02d}.diff.png"
            if src is not None:
                shutil.copyfile(src, image)
            if i <= len(final_pngs):
                shutil.copyfile(final_pngs[i - 1], final_image)
            changed = None
            before_path = ""
            diff_path = ""
            if i <= len(before_pngs):
                shutil.copyfile(before_pngs[i - 1], before_image)
                compared = src
                if compared is None:
                    width, height, _ = _read_png_rgb(before_pngs[i - 1])
                    compared = work / f"blank-{i}.png"
                    _write_png(compared, width, height, b"\xff" * (width * height * 3))
                _write_diff(compared, before_pngs[i - 1], diff_image)
                before_path = str(before_image)
                diff_path = str(diff_image)
                if i <= len(markup_gray) and i <= len(before_gray):
                    changed = _changed_fraction(markup_gray[i - 1], before_gray[i - 1])
            elif original is not None:
                changed = None
            pages.append(
                Page(
                    number=i,
                    image=str(image) if src is not None else "",
                    final_image=str(final_image) if i <= len(final_pngs) else "",
                    before_image=before_path,
                    diff_image=diff_path,
                    changed_fraction=changed,
                    sha256=_sha256(image) if src is not None else "",
                )
            )
        report.pages = pages
        _mechanical_checks(path, report, author, markup_text=full_markup, final_text=full_final)
        (out_dir / "pages.json").write_text(
            __import__("json").dumps({"pages": [p.to_dict() for p in pages]}, indent=2) + "\n"
        )
        report.ok = not report.failures
        return report
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.ok = False
        report.failures.append(RenderFailure("render_failed", "", "", 0, f"Render could not finish: {exc}"))
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _find_tool(env_key: str, name: str, extras: list[str]) -> str | None:
    env = os.environ.get(env_key)
    if env is not None:
        return env
    for candidate in extras:
        if candidate and Path(candidate).exists():
            return candidate
    return shutil.which(name)


def _prepare_sources(path: str | Path, original: str | Path | None, work: Path) -> dict[str, Path]:
    markup = work / "markup.docx"
    final = work / "final.docx"
    _force_markup_visible(path, markup)
    clean_docx(markup, final)
    jobs = {"markup": markup, "final": final}
    if original is not None:
        before = work / "before.docx"
        orig_final = work / "orig_final.docx"
        _force_markup_visible(original, before)
        clean_docx(before, orig_final)
        jobs["before"] = before
        jobs["orig_final"] = orig_final
    return jobs


def _force_markup_visible(src: str | Path, dest: Path) -> None:
    with zipfile.ZipFile(src) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    enable_track_revisions(files)
    data = files.get("word/settings.xml")
    if data:
        text = data.decode("utf-8")
        text = re.sub(r'(w:markup=")(?:false|0|off)(")', r"\1true\2", text)
        text = re.sub(r'(w:insDel=")(?:false|0|off)(")', r"\1true\2", text)
        text = re.sub(r'(w:formatting=")(?:false|0|off)(")', r"\1true\2", text)
        text = re.sub(r'(w:comments=")(?:false|0|off)(")', r"\1true\2", text)
        files["word/settings.xml"] = text.encode("utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in files.items():
            zf.writestr(name, payload)


def _convert(soffice: str, jobs: dict[str, Path], work: Path, report: RenderReport) -> dict[str, Path]:
    pdf_dir = work / "pdf"
    pdf_dir.mkdir()
    profile = work / "lo-profile"
    profile.mkdir()
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_dir),
        *[str(p) for p in jobs.values()],
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        (work.parent / "renderer.log").write_bytes(result.stdout + b"\n" + result.stderr)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        (work.parent / "renderer.log").write_text(str(exc) + "\n" + repr(getattr(exc, "stderr", b"")))
        report.failures.append(
            RenderFailure(
                kind="render_failed",
                location="",
                story="",
                paragraph=0,
                message=f"soffice failed ({exc}). Command: {' '.join(cmd)}",
            )
        )
        return {}
    pdfs: dict[str, Path] = {}
    for key, src in jobs.items():
        pdf = pdf_dir / (src.stem + ".pdf")
        if not pdf.exists():
            report.failures.append(
                RenderFailure(
                    kind="render_failed",
                    location="",
                    story="",
                    paragraph=0,
                    message=f"soffice did not produce {pdf.name}. Command: {' '.join(cmd)}",
                )
            )
            return {}
        pdfs[key] = pdf
    return pdfs


def _raster(pdftoppm: str, pdf: Path, dest_dir: Path, dpi: int) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    prefix = dest_dir / "page"
    subprocess.run([pdftoppm, "-r", str(dpi), str(pdf), str(prefix)], check=True, capture_output=True, timeout=60)
    pngs: list[Path] = []
    for ppm in sorted(dest_dir.glob("page*.ppm")):
        width, height, rgb = _read_pnm(ppm.read_bytes(), 3)
        dest = ppm.with_suffix(".png")
        _write_png(dest, width, height, rgb)
        pngs.append(dest)
    return pngs if pngs else sorted(dest_dir.glob("page*.png"))


def _raster_gray(pdftoppm: str, pdf: Path, dest_dir: Path, dpi: int) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    prefix = dest_dir / "page"
    subprocess.run([pdftoppm, "-gray", "-r", str(dpi), str(pdf), str(prefix)], check=True, capture_output=True, timeout=60)
    return sorted(dest_dir.glob("page*.pgm")) + sorted(dest_dir.glob("page*.png"))


def _extract_text(pdftotext: str, pdf: Path, docx: str | Path, exclude_headers: bool = True) -> str:
    proc = subprocess.run([pdftotext, "-layout", str(pdf), "-"], check=True, capture_output=True, timeout=60)
    raw = proc.stdout.decode("utf-8", errors="replace")
    skip = _header_footer_lines(docx) if exclude_headers else set()
    kept = []
    for line in raw.splitlines():
        compact = " ".join(line.split())
        if not compact or compact in skip or PAGE_NUMBER.match(compact):
            continue
        kept.append(compact)
    return "\n".join(kept)


def _header_footer_lines(path: str | Path) -> set[str]:
    skip: set[str] = set()
    package = load_docx(path)
    for story in package.stories:
        if not (story.name.startswith("header") or story.name.startswith("footer")):
            continue
        for para in story.paragraphs:
            text = " ".join(para.accept_text.split())
            if text:
                skip.add(text)
            text = " ".join(para.reject_text.split())
            if text:
                skip.add(text)
    return skip


def _mechanical_checks(path: str | Path, report: RenderReport, author: str, markup_text: str | None = None, final_text: str | None = None) -> None:
    markup = " ".join(_rendered_text(report.markup_text if markup_text is None else markup_text).split())
    final = " ".join(_rendered_text(report.final_text if final_text is None else final_text).split())
    _check_render_complete(path, report, markup, final)
    revisions = [rev for rev in list_revisions(path) if rev.author == author and rev.kind in {"ins", "del"}]
    for rev in revisions:
        missing = None
        for segment in _render_segments(rev.text):
            for needle in _needles(segment, 100, 50):
                if needle and needle not in markup:
                    missing = needle
                    break
            if missing:
                break
        if missing:
            report.failures.append(
                RenderFailure(
                    kind="render_markup_missing",
                    location=rev.location,
                    story=rev.story,
                    paragraph=rev.paragraph,
                    message=f"markup render is missing {rev.kind} text {missing!r}",
                )
            )
    seen: set[tuple[str, int]] = set()
    for rev in revisions:
        if (rev.story, rev.paragraph) in seen:
            continue
        seen.add((rev.story, rev.paragraph))
        package = load_docx(path)
        try:
            story = package.story(rev.story)
            para = next(p for p in story.paragraphs if p.index == rev.paragraph)
        except (KeyError, StopIteration):
            continue
        missing = None
        for segment in _wording_segments(para):
            for needle in _needles(segment, 200, 100):
                if needle and needle not in final:
                    missing = needle
                    break
            if missing:
                break
        if missing:
            report.failures.append(
                RenderFailure(
                    kind="render_wording_missing",
                    location=para.location,
                    story=para.story,
                    paragraph=para.index,
                    message=f"final render is missing accepted wording {missing!r}",
                )
            )


_FIELD_MARK = "\ue000"


def _render_segments(text: str) -> list[str]:
    """Wording as pdftotext can be expected to show it, split at symbol glyphs.

    A non-breaking hyphen (U+2011) renders as a plain hyphen, a soft hyphen
    (U+00AD) as nothing, and a ``w:sym`` glyph (a private-use code point) as
    whatever the Symbol or Wingdings font maps it to, so the text on either
    side of a symbol is checked on its own and the symbol itself is not looked
    for. Empty segments are dropped.
    """
    from redline_guard.ooxml import NO_BREAK_HYPHEN, PRIVATE_USE, SOFT_HYPHEN

    text = text.replace(NO_BREAK_HYPHEN, "-").replace(SOFT_HYPHEN, "")
    segments: list[str] = [""]
    for ch in text:
        if ord(ch) in PRIVATE_USE:
            segments.append("")
        else:
            segments[-1] += ch
    return [segment for segment in segments if segment]


def _rendered_text(text: str) -> str:
    """The renderer's text, normalised the way ``_render_segments`` normalises wording."""
    from redline_guard.ooxml import NO_BREAK_HYPHEN, SOFT_HYPHEN

    return text.replace(NO_BREAK_HYPHEN, "-").replace(SOFT_HYPHEN, "")


def _wording_segments(para) -> list[str]:
    """The paragraph's accepted wording split at field results and symbols.

    PAGE, NUMPAGES, DATE and other fields are regenerated by the renderer, so
    their cached result in the XML is not something the final view must show;
    the text on either side of a field is checked on its own. Special hyphens
    and symbol glyphs are normalised by ``_render_segments``.
    """
    from xml.etree import ElementTree as ET

    from redline_guard.ooxml import paragraph_texts

    if not para.accept_text:
        return []  # nothing survives (a deleted row, an emptied paragraph): the model's view wins
    if para.element.find(f".//{q('fldSimple')}") is None and para.element.find(f".//{q('fldChar')}") is None:
        return _render_segments(para.accept_text)  # no fields: the paragraph model's text, row context included
    el = copy.deepcopy(para.element)
    for fld in list(el.iter(q("fldSimple"))):
        for t in list(fld.iter(q("t"))) + list(fld.iter(q("delText"))):
            t.text = ""
        run = ET.SubElement(fld, q("r"))
        ET.SubElement(run, q("t")).text = _FIELD_MARK
    inside = False
    for run in list(el.iter(q("r"))):
        char = run.find(q("fldChar"))
        if char is not None:
            kind = char.get(w_attr("fldCharType"), "")
            if kind == "begin":
                inside = True
                ET.SubElement(run, q("t")).text = _FIELD_MARK
            elif kind == "end":
                inside = False
            continue
        if inside:
            for t in list(run.iter(q("t"))) + list(run.iter(q("delText"))):
                t.text = ""
    _reject_text, accept_text, _revisions = paragraph_texts(el)
    return [piece for segment in accept_text.split(_FIELD_MARK) for piece in _render_segments(segment)]


def _needles(text: str, limit: int, half: int) -> list[str]:
    compact = " ".join((text or "").split())
    if not compact:
        return []
    if len(compact) <= limit:
        return [compact]
    return [compact[:half], compact[-half:]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_png_rgb(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos = 8
    width = height = 0
    raw = b""
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height = struct.unpack(">II", chunk[:8])
        elif tag == b"IDAT":
            raw += chunk
        elif tag == b"IEND":
            break
    pixels = zlib.decompress(raw)
    rows = []
    stride = width * 3
    offset = 0
    prev = bytearray(stride)
    for _ in range(height):
        filt = pixels[offset]
        row = bytearray(pixels[offset + 1 : offset + 1 + stride])
        offset += 1 + stride
        if filt == 1:
            for i in range(stride):
                row[i] = (row[i] + (row[i - 3] if i >= 3 else 0)) & 255
        elif filt == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif filt == 3:
            for i in range(stride):
                left = row[i - 3] if i >= 3 else 0
                row[i] = (row[i] + ((left + prev[i]) // 2)) & 255
        elif filt == 4:
            for i in range(stride):
                a = row[i - 3] if i >= 3 else 0
                b = prev[i]
                c = prev[i - 3] if i >= 3 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pred) & 255
        rows.append(bytes(row))
        prev = row
    return width, height, b"".join(rows)


def _write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    raw = b""
    stride = width * 3
    for y in range(height):
        raw += b"\x00" + rgb[y * stride : (y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _write_diff(markup: Path, before: Path, dest: Path) -> None:
    try:
        w1, h1, a = _read_png_rgb(markup)
        w2, h2, b = _read_png_rgb(before)
    except ValueError:
        shutil.copyfile(markup, dest)
        return
    width, height = min(w1, w2), min(h1, h2)
    out = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            i = (y * w1 + x) * 3
            j = (y * w2 + x) * 3
            k = (y * width + x) * 3
            if a[i : i + 3] != b[j : j + 3]:
                out[k : k + 3] = b"\xff\x00\x00"
            else:
                out[k : k + 3] = a[i : i + 3]
    _write_png(dest, width, height, bytes(out))


def _changed_fraction(a: Path, b: Path) -> float:
    pa = _read_gray(a)
    pb = _read_gray(b)
    if pa is None or pb is None:
        return 0.0
    (w1, h1, da), (w2, h2, db) = pa, pb
    width, height = min(w1, w2), min(h1, h2)
    if width == 0 or height == 0:
        return 0.0
    changed = 0
    total = width * height
    for y in range(height):
        for x in range(width):
            if da[y * w1 + x] != db[y * w2 + x]:
                changed += 1
    return changed / total


def _read_gray(path: Path) -> tuple[int, int, bytes] | None:
    data = path.read_bytes()
    if data.startswith(b"P5"):
        return _read_pnm(data, 1)
    if data.startswith(b"\x89PNG"):
        w, h, rgb = _read_png_rgb(path)
        gray = bytes((rgb[i] + rgb[i + 1] + rgb[i + 2]) // 3 for i in range(0, len(rgb), 3))
        return w, h, gray
    return None


def _read_pnm(data: bytes, channels: int) -> tuple[int, int, bytes]:
    header, _, rest = data.partition(b"\n")
    while rest.startswith(b"#"):
        rest = rest.split(b"\n", 1)[1]
    dims, _, rest = rest.partition(b"\n")
    while dims.startswith(b"#"):
        dims, _, rest = rest.partition(b"\n")
    width, height = [int(p) for p in dims.split()]
    maxv, _, pixels = rest.partition(b"\n")
    return width, height, pixels[: width * height * channels]


def _check_render_complete(path: str | Path, report: RenderReport, markup: str, final: str) -> None:
    """The renderer must show the end of the body (probe finding 1.2.6).

    LibreOffice drops every paragraph after an inline text box that directly
    follows a table, so a page set can look complete and still miss the tail
    of the document. The last body paragraph with wording is looked for in
    both views; a miss fails closed as ``render_incomplete``.
    """
    package = load_docx(path)
    try:
        body = package.story("body")
    except KeyError:
        return
    # The last paragraph without tracked changes reads the same in both views;
    # a paragraph with a replacement shows struck and inserted words interleaved
    # in the markup view, so its accepted wording is not one string there.
    tail = next((p for p in reversed(body.paragraphs) if p.accept_text.strip() and not p.revisions and p.accept_text == p.reject_text), None)
    if tail is None:
        return
    segments = [s for s in _wording_segments(tail) if s.strip()]
    needles = _needles(segments[-1], 60, 30) if segments else []
    if not needles:
        return
    needle = needles[-1]
    for view, text in (("markup", markup), ("final", final)):
        if needle not in text:
            report.failures.append(
                RenderFailure(
                    kind="render_incomplete",
                    location=tail.location,
                    story=tail.story,
                    paragraph=tail.index,
                    message=(
                        f"the {view} render stops before the end of the document: {needle!r} is not on any page "
                        "(LibreOffice drops what follows a text box placed directly after a table; put a paragraph between them or render in Word)"
                    ),
                )
            )
