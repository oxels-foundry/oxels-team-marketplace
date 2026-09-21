"""OOXML helpers for reading and writing tracked-change markup in .docx files."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
XML_SPACE = f"{{{XML_NS}}}space"

ET.register_namespace("w", W_NS)

_XMLNS_PREFIX = re.compile(r"\sxmlns:([A-Za-z0-9]+)=[\"']([^\"']+)[\"']")

# Word's mc:Ignorable list names these prefixes. ElementTree invents ns1/ns2
# unless they are registered, which is what triggers the Styles repair dialog.
_WORD_NS_PREFIXES = {
    "w": W_NS,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "o": "urn:schemas-microsoft-com:office:office",
    "v": "urn:schemas-microsoft-com:vml",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "sl": "http://schemas.openxmlformats.org/schemaLibrary/2006/main",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}

SKIP_TAGS = {
    f"{W}pPr",
    f"{W}rPr",
    f"{W}sectPr",
    f"{W}tblPr",
    f"{W}tblGrid",
    f"{W}trPr",
    f"{W}tcPr",
    f"{W}proofErr",
    f"{W}bookmarkStart",
    f"{W}bookmarkEnd",
    f"{W}commentRangeStart",
    f"{W}commentRangeEnd",
    f"{W}commentReference",
    f"{W}lastRenderedPageBreak",
}

WRAPPER_TAGS = {
    f"{W}hyperlink",
    f"{W}sdt",
    f"{W}sdtContent",
    f"{W}smartTag",
    f"{W}fldSimple",
    f"{W}customXml",
}

INS_TAGS = {f"{W}ins", f"{W}moveTo"}
DEL_TAGS = {f"{W}del", f"{W}moveFrom"}
FORMAT_CHANGE_TAGS = {
    f"{W}rPrChange",
    f"{W}pPrChange",
    f"{W}sectPrChange",
    f"{W}tblPrChange",
    f"{W}trPrChange",
    f"{W}tcPrChange",
    f"{W}tblGridChange",
}
MOVE_RANGE_TAGS = {
    f"{W}moveFromRangeStart",
    f"{W}moveFromRangeEnd",
    f"{W}moveToRangeStart",
    f"{W}moveToRangeEnd",
}


def q(tag: str) -> str:
    return f"{W}{tag}"


def w_attr(name: str) -> str:
    return f"{W}{name}"


def on_off(el: ET.Element | None) -> bool:
    if el is None:
        return False
    val = el.get(w_attr("val"))
    if val is None:
        return True
    return val not in {"0", "false", "off", "False"}


@dataclass
class Revision:
    kind: str
    rev_id: str
    author: str
    date: str
    text: str


@dataclass
class CharRef:
    char: str
    text_node: ET.Element
    offset: int
    run: ET.Element
    in_ins: bool
    in_del: bool
    ins_el: ET.Element | None
    del_el: ET.Element | None


@dataclass
class ParagraphView:
    story: str
    index: int
    element: ET.Element
    part_name: str
    reject_text: str
    accept_text: str
    revisions: list[Revision] = field(default_factory=list)
    label: str = ""
    # The package this paragraph was read from, so an editor holding only the
    # paragraph can still consult other parts (styles.xml for style ids).
    package: "DocxPackage | None" = field(default=None, repr=False, compare=False)

    @property
    def location(self) -> str:
        if self.story == "body":
            return f"body paragraph {self.index}"
        return f"{self.story} paragraph {self.index}"


@dataclass
class Story:
    name: str
    part_name: str
    root: ET.Element
    paragraphs: list[ParagraphView]


@dataclass
class DocxPackage:
    path: Path
    files: dict[str, bytes]
    stories: list[Story]

    def story(self, name: str) -> Story:
        for item in self.stories:
            if item.name == name or item.part_name == name:
                return item
        raise KeyError(f"No story named {name!r}")

    def body_paragraphs(self) -> list[ParagraphView]:
        return self.story("body").paragraphs

    def all_paragraphs(self) -> list[ParagraphView]:
        out: list[ParagraphView] = []
        for story in self.stories:
            out.extend(story.paragraphs)
        return out


def load_docx(path: str | Path) -> DocxPackage:
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    stories = _parse_stories(files)
    package = DocxPackage(path=path, files=files, stories=stories)
    for story in stories:
        for paragraph in story.paragraphs:
            paragraph.package = package
    return package


def refuse_overwrite(input_path: str | Path, output_path: str | Path, error_cls: type[Exception] = ValueError) -> None:
    """Writers must not replace the file they are reading, nor a finalized send file.

    A file with a finalize manifest beside it (``<out>.finalize.json``) has been
    through the send gate, maybe attested; writing over it would silently
    replace what was checked. A plain existing output is replaced
    as before.
    """
    output = Path(output_path)
    if output.resolve() == Path(input_path).resolve():
        raise error_cls("Refusing to overwrite the input file; pass a different output path.")
    manifest = Path(f"{output}.finalize.json")
    if output.exists() and manifest.exists():
        raise error_cls(
            f"Refusing to overwrite {output.name}: it is a finalized send file ({_manifest_status(manifest)}); write to a new path."
        )


def _manifest_status(manifest: Path) -> str:
    import json

    try:
        status = json.loads(manifest.read_text()).get("status")
    except (OSError, ValueError, AttributeError):
        return "manifest unreadable"
    return f"status {status}" if status else "no status"


def save_docx(package: DocxPackage, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in package.files.items():
            zf.writestr(name, data)


def write_tree(root: ET.Element, original: bytes | None = None) -> bytes:
    _register_namespaces(original)
    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True, default_namespace=None)
    xml = buf.getvalue()
    xml = xml.replace(
        b"<?xml version='1.0' encoding='UTF-8'?>",
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    )
    xml = xml.replace(
        b'<?xml version="1.0" encoding="UTF-8"?>',
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    )
    if original:
        xml = _restore_root_namespaces(xml, original)
    return xml


def _opening_tag(xml: str) -> str:
    start = 0
    if xml.startswith("<?xml"):
        start = xml.find("<", xml.find("?>") + 2)
    else:
        start = xml.find("<")
    if start < 0:
        raise ValueError("XML has no opening tag")
    end = xml.find(">", start)
    return xml[start : end + 1]


def _restore_root_namespaces(serialized: bytes, original: bytes) -> bytes:
    """Keep every original xmlns:* on the root.

    Word's mc:Ignorable lists prefixes like w15/w16/wp14. ElementTree drops
    declarations it thinks are unused, and Word then reports unreadable content.
    """
    orig_text = original.decode("utf-8")
    new_text = serialized.decode("utf-8")
    orig_tag = _opening_tag(orig_text)
    new_tag = _opening_tag(new_text)
    orig_name = re.match(r"<([A-Za-z0-9:]+)", orig_tag)
    new_name = re.match(r"<([A-Za-z0-9:]+)", new_tag)
    if not orig_name or not new_name or orig_name.group(1) != new_name.group(1):
        return serialized

    xmlns_decls = re.findall(r'\s(xmlns(?::[A-Za-z0-9]+)?="[^"]+")', orig_tag)
    seen = {decl.split("=", 1)[0] for decl in xmlns_decls}
    for decl in re.findall(r'\s(xmlns(?::[A-Za-z0-9]+)?="[^"]+")', new_tag):
        key = decl.split("=", 1)[0]
        if key not in seen:
            xmlns_decls.append(decl)
            seen.add(key)
    other_attrs = [
        attr
        for attr in re.findall(r'\s((?!xmlns)[\w:.-]+="[^"]+")', new_tag)
        if not attr.startswith("mc:Ignorable=")
    ]
    # Keep the original list and add any prefix the edit newly relies on (for example w14 on
    # comment paragraphs added to a comments part that had no mc:Ignorable of its own).
    tokens: list[str] = []
    for tag in (orig_tag, new_tag):
        found = re.search(r'\smc:Ignorable="([^"]+)"', tag)
        for token in (found.group(1).split() if found else []):
            if token not in tokens:
                tokens.append(token)
    ignorable = f'mc:Ignorable="{" ".join(tokens)}"' if tokens else None
    rebuilt = f"<{new_name.group(1)}"
    for decl in xmlns_decls:
        rebuilt += f" {decl}"
    if ignorable:
        rebuilt += f" {ignorable}"
    for attr in other_attrs:
        rebuilt += f" {attr}"
    rebuilt += "/>" if new_tag.rstrip().endswith("/>") else ">"
    return new_text.replace(new_tag, rebuilt, 1).encode("utf-8")


def _register_namespaces(original: bytes | None) -> None:
    for prefix, uri in _WORD_NS_PREFIXES.items():
        ET.register_namespace(prefix, uri)
    if not original:
        return
    head = original.decode("utf-8", errors="replace")[:12000]
    for prefix, uri in _XMLNS_PREFIX.findall(head):
        if re.fullmatch(r"ns\d+", prefix):
            # ElementTree generates these names but rejects their registration.
            continue
        ET.register_namespace(prefix, uri)


def parse_xml(data: bytes) -> ET.Element:
    # Counterparty files are untrusted. A DOCTYPE or entity declaration is
    # enough to expand into a billion laughs; refuse before the parser runs.
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Untrusted XML: DOCTYPE and entity declarations are not allowed")
    return ET.fromstring(data)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_stories(files: dict[str, bytes]) -> list[Story]:
    stories: list[Story] = []
    if "word/document.xml" in files:
        stories.append(_story_from_part("body", "word/document.xml", files["word/document.xml"]))
    for name in sorted(files):
        if name.startswith("word/header") and name.endswith(".xml"):
            stories.append(_story_from_part(f"header {name}", name, files[name]))
        elif name.startswith("word/footer") and name.endswith(".xml"):
            stories.append(_story_from_part(f"footer {name}", name, files[name]))
    for extra, label in (
        ("word/footnotes.xml", "footnotes"),
        ("word/endnotes.xml", "endnotes"),
    ):
        if extra in files:
            stories.append(_story_from_part(label, extra, files[extra]))
    return stories


NOTE_SEPARATOR_TYPES = {"separator", "continuationSeparator", "continuationNotice"}


def separator_note_paragraphs(root: ET.Element) -> set[ET.Element]:
    """Paragraphs of Word's separator footnotes and endnotes: not document text."""
    skip: set[ET.Element] = set()
    for tag in (q("footnote"), q("endnote")):
        for note in root.iter(tag):
            if note.get(w_attr("type")) in NOTE_SEPARATOR_TYPES:
                skip.update(note.iter(q("p")))
    return skip


def _story_from_part(name: str, part_name: str, data: bytes) -> Story:
    root = parse_xml(data)
    paragraphs: list[ParagraphView] = []
    skip = separator_note_paragraphs(root) if name in {"footnotes", "endnotes"} else set()
    parents = parent_map_from(root)
    for i, el in enumerate((p for p in _iter_paragraphs(root) if p not in skip), start=1):
        reject_text, accept_text, revisions = paragraph_texts(el)
        # The label keeps the row's wording, so `revisions` and `list` still
        # name a struck row by what it says.
        label = paragraph_label(el, accept_text)
        marks = row_revision_marks(el, parents)
        if marks:
            reject_text, accept_text, revisions = _apply_row_marks(marks, reject_text, accept_text, revisions)
        paragraphs.append(
            ParagraphView(
                story=name,
                index=i,
                element=el,
                part_name=part_name,
                reject_text=reject_text,
                accept_text=accept_text,
                revisions=revisions,
                label=label,
            )
        )
    return Story(name=name, part_name=part_name, root=root, paragraphs=paragraphs)


def row_revision_marks(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> list[ET.Element]:
    """Row insertions and deletions (``w:ins``/``w:del`` in ``w:trPr``) of every
    table row holding this paragraph, outermost row first.

    A row of a nested table inside a deleted outer row carries no marker of its
    own; the outer row's deletion covers it (Word removes it with the row).
    """
    marks: list[ET.Element] = []
    current = parents.get(paragraph)
    while current is not None:
        if current.tag == q("tr"):
            pr = current.find(q("trPr"))
            if pr is not None:
                marks[:0] = [node for node in pr if node.tag in INS_TAGS | DEL_TAGS]
        current = parents.get(current)
    return marks


def _apply_row_marks(
    marks: list[ET.Element], reject_text: str, accept_text: str, revisions: list[Revision]
) -> tuple[str, str, list[Revision]]:
    """Read a paragraph inside a tracked row the way text inside ``w:del`` reads.

    A deleted row is absent from the accept view (Word removes it on Accept),
    whatever its cell runs say: the tool's and the fixtures' rows keep plain
    ``w:t``, Word also strikes the runs as ``w:delText``; either way the text is
    in the reject view only and nothing is counted twice. An inserted row's
    reject view is left to its runs: Word writes them as ``w:ins``, so it is
    already empty; a marker-only inserted row (the fixtures' shape) keeps its
    text there, since blanking it only makes verify's paragraph alignment
    misfire and fixes nothing. The row revisions are listed on
    the paragraph with the row's id, so ``list`` shows ``[has revisions]`` and
    ``verify`` compares them like any other. They carry no text, like a
    paragraph-mark revision: the cell text belongs to the runs, which may carry
    their own revisions (ours inside their inserted row), and ``revisions``
    reports the row's wording from the row itself.
    """
    row_revisions: list[Revision] = []
    for mark in marks:
        row_revisions.append(
            Revision(
                kind="del" if mark.tag in DEL_TAGS else "ins",
                rev_id=mark.get(w_attr("id"), ""),
                author=mark.get(w_attr("author"), ""),
                date=mark.get(w_attr("date"), ""),
                text="",
            )
        )
    if any(mark.tag in DEL_TAGS for mark in marks):
        accept_text = ""
    return reject_text, accept_text, row_revisions + revisions


def paragraph_mark_revision(paragraph: ET.Element) -> tuple[str, str] | None:
    rpr = paragraph.find(f"{q('pPr')}/{q('rPr')}")
    if rpr is None:
        return None
    for child in rpr:
        if child.tag in DEL_TAGS:
            return ("del", child.get(w_attr("id"), ""))
        if child.tag in INS_TAGS:
            return ("ins", child.get(w_attr("id"), ""))
    return None


def paragraph_mark_kind(paragraph: ET.Element) -> str | None:
    found = paragraph_mark_revision(paragraph)
    return found[0] if found else None


def is_last_paragraph_in_cell(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    parent = parents.get(paragraph)
    if parent is None or parent.tag != q("tc"):
        return False
    paras = [child for child in parent if child.tag == q("p")]
    return bool(paras) and paras[-1] is paragraph


def is_only_paragraph_in_cell(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    parent = parents.get(paragraph)
    if parent is None or parent.tag != q("tc"):
        return False
    paras = [child for child in parent if child.tag == q("p")]
    return len(paras) == 1 and paras[0] is paragraph


def is_only_paragraph_in_body(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    """The document body, like a cell or a header, must keep one paragraph."""
    parent = parents.get(paragraph)
    if parent is None or parent.tag != q("body"):
        return False
    paras = [child for child in parent if child.tag == q("p")]
    return len(paras) == 1 and paras[0] is paragraph


def is_last_paragraph_in_header_or_footer(
    paragraph: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    """Headers and footers, like table cells, must keep one paragraph."""
    parent = parents.get(paragraph)
    if parent is None or parent.tag not in {q("hdr"), q("ftr")}:
        return False
    paras = [child for child in parent if child.tag == q("p")]
    return bool(paras) and paras[-1] is paragraph


def is_only_paragraph_in_header_or_footer(
    paragraph: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    parent = parents.get(paragraph)
    if parent is None or parent.tag not in {q("hdr"), q("ftr")}:
        return False
    paras = [child for child in parent if child.tag == q("p")]
    return len(paras) == 1 and paras[0] is paragraph


def paragraph_label(el: ET.Element, accept_text: str) -> str:
    ppr = el.find(q("pPr"))
    if ppr is not None:
        style = ppr.find(q("pStyle"))
        if style is not None:
            val = style.get(w_attr("val"), "")
            if val.lower().startswith("heading") or val in {"Title", "Subtitle"}:
                title = accept_text.strip().split("\n")[0][:80]
                return title or val
    for child in el:
        if child.tag != q("r"):
            continue
        rpr = child.find(q("rPr"))
        bold = rpr is not None and rpr.find(q("b")) is not None
        text = "".join((node.text or "") for node in child if node.tag == q("t")).strip()
        if bold and text:
            return text[:80]
        break
    numbered = re.match(r"^(\d+(?:\.\d+)*[.)]\s+\S[^\n]{0,80})", accept_text.strip())
    if numbered:
        return numbered.group(1).strip()[:80]
    first = accept_text.strip().split(".")[0].strip()
    if first and 2 < len(first) < 70 and first[:1].isupper():
        return first + "."
    return ""


MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
MC_FALLBACK = f"{{{MC_NS}}}Fallback"


def _iter_paragraphs(root: ET.Element) -> Iterator[ET.Element]:
    """Every paragraph in document order, text boxes counted once.

    A text box is stored twice, as ``mc:Choice`` (the DrawingML shape) and
    ``mc:Fallback`` (the VML copy Word keeps for older readers). Only the
    Choice copy is a paragraph of the document; ``apply`` mirrors edits into
    the Fallback copy, keyed off the Choice paragraph.
    """
    if root.tag == q("p"):
        yield root
    for child in root:
        if child.tag == MC_FALLBACK:
            continue
        yield from _iter_paragraphs(child)


MC_ALTERNATE = f"{{{MC_NS}}}AlternateContent"
MC_CHOICE = f"{{{MC_NS}}}Choice"


def iter_outside_fallback(root: ET.Element) -> Iterator[ET.Element]:
    """Every element in document order, the ``mc:Fallback`` mirrors excluded."""
    yield root
    for child in root:
        if child.tag == MC_FALLBACK:
            continue
        yield from iter_outside_fallback(child)


def iter_own_content(paragraph: ET.Element) -> Iterator[ET.Element]:
    """The paragraph's descendants without descending into nested paragraphs.

    A text box's paragraphs are listed on their own; the host paragraph that
    holds the drawing does not own their revisions or comment markers (and the
    ``mc:Fallback`` mirror is inside nested paragraphs too).
    """
    for child in paragraph:
        if child.tag == q("p"):
            continue
        yield child
        yield from iter_own_content(child)


def text_boxes(root: ET.Element) -> list[ET.Element]:
    """Every ``mc:AlternateContent`` that holds a Choice and a Fallback branch."""
    return [
        alternate
        for alternate in root.iter(MC_ALTERNATE)
        if alternate.find(MC_CHOICE) is not None and alternate.find(MC_FALLBACK) is not None
    ]


def text_box_snapshots(package: "DocxPackage") -> dict[str, list[bytes]]:
    """The serialised ``mc:Choice`` branch of every text box, per story part, before an edit."""
    return {
        story.part_name: [ET.tostring(alternate.find(MC_CHOICE)) for alternate in text_boxes(story.root)]
        for story in package.stories
    }


def mirror_changed_text_boxes(
    package: "DocxPackage", snapshots: dict[str, list[bytes]], allocate: "Callable[[], str]"
) -> set[str]:
    """Copy every edited ``mc:Choice`` text box over its ``mc:Fallback`` twin.

    Word keeps both branches identical: a tracked change, a comment's range
    markers and reference run, or a resolved revision written into the listed
    Choice copy is mirrored into the Fallback, so a reader that uses the VML
    fallback sees the same document. Revision ids in the copy get fresh
    values so every id stays unique; comment ids are the same in both copies,
    as Word writes them. Returns the story parts that changed.
    """
    changed: set[str] = set()
    for story in package.stories:
        before = snapshots.get(story.part_name, [])
        boxes = text_boxes(story.root)
        for index, alternate in enumerate(boxes):
            choice = alternate.find(MC_CHOICE)
            if index < len(before) and ET.tostring(choice) == before[index]:
                continue
            mirror_text_box(alternate, allocate)
            changed.add(story.part_name)
    return changed


def mirror_text_box(alternate: ET.Element, allocate: "Callable[[], str]") -> None:
    """Replace the Fallback's ``txbxContent`` with a copy of the Choice's, fresh revision ids."""
    from copy import deepcopy

    choice = alternate.find(MC_CHOICE)
    fallback = alternate.find(MC_FALLBACK)
    if choice is None or fallback is None:
        return
    sources = list(choice.iter(q("txbxContent")))
    targets = list(fallback.iter(q("txbxContent")))
    if len(sources) != len(targets):
        return
    renumber = INS_TAGS | DEL_TAGS | FORMAT_CHANGE_TAGS
    for source, target in zip(sources, targets):
        for child in list(target):
            target.remove(child)
        for child in source:
            clone = deepcopy(child)
            for el in clone.iter():
                if el.tag in renumber and el.get(w_attr("id")):
                    el.set(w_attr("id"), allocate())
            target.append(clone)


# Run content that reads as one character: Word shows a non-breaking hyphen as
# U+2011, a soft hyphen as U+00AD, and a ``w:sym`` glyph at the private-use
# code point it stores for Symbol and Wingdings fonts (U+F000 + the low byte of
# ``w:char``). They are addressable through ``list`` and ``find`` and can be
# struck or commented on like any character; a span boundary falls before or
# after the run, never inside it.
NO_BREAK_HYPHEN = "\u2011"
SOFT_HYPHEN = "\u00ad"
PRIVATE_USE = range(0xE000, 0xF900)


def sym_char(node: ET.Element) -> str:
    """The character Word shows for a ``w:sym`` element."""
    raw = (node.get(w_attr("char")) or "").strip()
    try:
        code = int(raw, 16)
    except ValueError:
        return "\ufffd"
    if code in PRIVATE_USE:
        return chr(code)
    return chr(0xF000 + (code & 0xFF))


def inline_char(node: ET.Element, take_deleted: bool | None = None) -> str | None:
    """The character a run child contributes to the text, or None for none.

    ``take_deleted`` None takes both ``w:t`` and ``w:delText``; True takes
    ``w:delText`` only, False ``w:t`` only. Tabs, breaks, the two special
    hyphens and ``w:sym`` count whichever way.
    """
    tag = node.tag
    if tag == q("t"):
        return None if take_deleted is True else (node.text or "")
    if tag == q("delText"):
        return None if take_deleted is False else (node.text or "")
    if tag == q("tab"):
        return "\t"
    if tag in {q("br"), q("cr")}:
        return "\n"
    if tag == q("noBreakHyphen"):
        return NO_BREAK_HYPHEN
    if tag == q("softHyphen"):
        return SOFT_HYPHEN
    if tag == q("sym"):
        return sym_char(node)
    return None


def run_text(run: ET.Element, take_deleted: bool | None = None) -> str:
    """Text of one run as Word shows it (see ``inline_char``)."""
    return "".join(part for part in (inline_char(child, take_deleted) for child in run) if part)


def paragraph_texts(p: ET.Element) -> tuple[str, str, list[Revision]]:
    reject: list[str] = []
    accept: list[str] = []
    revisions: list[Revision] = []

    def take_run_text(run: ET.Element, deleted: bool) -> str:
        return run_text(run)

    def walk(el: ET.Element, in_ins: ET.Element | None, in_del: ET.Element | None) -> None:
        for child in el:
            tag = child.tag
            if tag in SKIP_TAGS:
                continue
            if tag in INS_TAGS:
                text = _collect_revision_text(child, deleted=False)
                revisions.append(
                    Revision(
                        kind="ins",
                        rev_id=child.get(w_attr("id"), ""),
                        author=child.get(w_attr("author"), ""),
                        date=child.get(w_attr("date"), ""),
                        text=text,
                    )
                )
                walk(child, child, in_del)
                continue
            if tag in DEL_TAGS:
                text = _collect_revision_text(child, deleted=True)
                revisions.append(
                    Revision(
                        kind="del",
                        rev_id=child.get(w_attr("id"), ""),
                        author=child.get(w_attr("author"), ""),
                        date=child.get(w_attr("date"), ""),
                        text=text,
                    )
                )
                walk(child, in_ins, child)
                continue
            if tag == q("r"):
                deleted = in_del is not None
                inserted = in_ins is not None
                text = take_run_text(child, deleted)
                if deleted and not inserted:
                    reject.append(text)
                elif inserted and not deleted:
                    accept.append(text)
                elif not deleted and not inserted:
                    reject.append(text)
                    accept.append(text)
                continue
            if tag in WRAPPER_TAGS:
                walk(child, in_ins, in_del)
                continue
            walk(child, in_ins, in_del)

    walk(p, None, None)
    return "".join(reject), "".join(accept), revisions


def _collect_revision_text(el: ET.Element, deleted: bool) -> str:
    """Text of one revision. An insertion includes nested deletions by another author.

    Word writes our strike inside their insertion as a nested ``w:del``. The
    wrapper piece has no ``w:t``; the struck words still belong to their proposal.
    """
    owner = el.get(w_attr("author"), "")
    parts: list[str] = []

    def walk(node: ET.Element, take_deleted: bool) -> None:
        for child in node:
            if child.tag in INS_TAGS:
                if not deleted and child.get(w_attr("author"), "") != owner:
                    continue
                walk(child, take_deleted)
                continue
            if child.tag in DEL_TAGS:
                child_author = child.get(w_attr("author"), "")
                if not deleted and child_author != owner:
                    walk(child, True)
                    continue
                if deleted:
                    walk(child, True)
                continue
            if child.tag == q("r"):
                parts.append(run_text(child, take_deleted))
                continue
            walk(child, take_deleted)

    walk(el, deleted)
    return "".join(parts)


def revision_reject_offsets(paragraph: ET.Element) -> dict[str, int]:
    """Reject-all offset of each revision id: where it sits in the baseline."""
    offsets: dict[str, int] = {}
    reject_len = 0

    def take_run_text(run: ET.Element) -> str:
        return run_text(run)

    def walk(el: ET.Element, in_ins: ET.Element | None, in_del: ET.Element | None) -> None:
        nonlocal reject_len
        for child in el:
            tag = child.tag
            if tag in SKIP_TAGS:
                continue
            if tag in INS_TAGS:
                rid = child.get(w_attr("id"), "")
                if rid and rid not in offsets:
                    offsets[rid] = reject_len
                walk(child, child, in_del)
                continue
            if tag in DEL_TAGS:
                rid = child.get(w_attr("id"), "")
                if rid and rid not in offsets:
                    offsets[rid] = reject_len
                walk(child, in_ins, child)
                continue
            if tag == q("r"):
                deleted = in_del is not None
                inserted = in_ins is not None
                text = take_run_text(child)
                if (deleted and not inserted) or (not deleted and not inserted):
                    reject_len += len(text)
                continue
            if tag in WRAPPER_TAGS:
                walk(child, in_ins, in_del)
                continue
            walk(child, in_ins, in_del)

    walk(paragraph, None, None)
    return offsets


def final_char_map(p: ET.Element) -> list[CharRef]:
    refs: list[CharRef] = []

    def walk(el: ET.Element, in_ins: ET.Element | None, in_del: ET.Element | None) -> None:
        for child in el:
            tag = child.tag
            if tag in SKIP_TAGS:
                continue
            if tag in INS_TAGS:
                walk(child, child, in_del)
                continue
            if tag in DEL_TAGS:
                walk(child, in_ins, child)
                continue
            if tag == q("r"):
                if in_del is not None:
                    continue
                for node in child:
                    if node.tag in {q("t"), q("delText")}:
                        text = node.text or ""
                        for i, ch in enumerate(text):
                            refs.append(
                                CharRef(
                                    char=ch,
                                    text_node=node,
                                    offset=i,
                                    run=child,
                                    in_ins=in_ins is not None,
                                    in_del=False,
                                    ins_el=in_ins,
                                    del_el=in_del,
                                )
                            )
                        continue
                    # One character that is the whole node (tab, break,
                    # special hyphen, symbol): offset 0, never split inside.
                    ch = inline_char(node)
                    if ch is not None:
                        refs.append(CharRef(ch, node, 0, child, in_ins is not None, False, in_ins, in_del))
                continue
            if tag in WRAPPER_TAGS:
                walk(child, in_ins, in_del)
                continue
            walk(child, in_ins, in_del)

    walk(p, None, None)
    return refs


def set_text_node(node: ET.Element, text: str) -> None:
    node.text = text
    if text.startswith(" ") or text.endswith(" ") or "\t" in text:
        node.set(XML_SPACE, "preserve")
    elif XML_SPACE in node.attrib and not text:
        node.attrib.pop(XML_SPACE, None)


def clone_run_shell(run: ET.Element) -> ET.Element:
    new_run = ET.Element(q("r"))
    rpr = run.find(q("rPr"))
    if rpr is not None:
        new_run.append(sanitize_copied_properties(rpr))
    return new_run


def sanitize_copied_properties(el: ET.Element) -> ET.Element:
    """Clone pPr/rPr without section breaks or revision history."""
    cloned = _clone(el)
    _strip_copied_revision_props(cloned)
    return cloned


def _strip_copied_revision_props(el: ET.Element) -> None:
    drop = FORMAT_CHANGE_TAGS | INS_TAGS | DEL_TAGS | {q("sectPr")}
    for child in list(el):
        if child.tag in drop:
            el.remove(child)
        else:
            _strip_copied_revision_props(child)


def _clone(el: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(el, encoding="utf-8"))


def make_tracked_insert(text: str, author: str, date: str, rev_id: str, sample_run: ET.Element | None = None) -> ET.Element:
    ins = ET.Element(
        q("ins"),
        {
            w_attr("id"): rev_id,
            w_attr("author"): author,
            w_attr("date"): date,
        },
    )
    run = clone_run_shell(sample_run) if sample_run is not None else ET.Element(q("r"))
    _fill_run_with_text(run, q("t"), text)
    ins.append(run)
    return ins


def make_tracked_delete(text: str, author: str, date: str, rev_id: str, sample_run: ET.Element | None = None) -> ET.Element:
    dele = ET.Element(
        q("del"),
        {
            w_attr("id"): rev_id,
            w_attr("author"): author,
            w_attr("date"): date,
        },
    )
    run = clone_run_shell(sample_run) if sample_run is not None else ET.Element(q("r"))
    _fill_run_with_text(run, q("delText"), text)
    dele.append(run)
    return dele


def _fill_run_with_text(run: ET.Element, text_tag: str, text: str) -> None:
    """Put text into a run, turning newlines into breaks and tabs into w:tab."""
    buffer = ""
    for char in text:
        if char in {"\n", "\t"}:
            if buffer:
                node = ET.SubElement(run, text_tag)
                set_text_node(node, buffer)
                buffer = ""
            ET.SubElement(run, q("br" if char == "\n" else "tab"))
        else:
            buffer += char
    if buffer:
        node = ET.SubElement(run, text_tag)
        set_text_node(node, buffer)


def parent_map_from(root: ET.Element) -> dict[ET.Element, ET.Element]:
    mapping: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            mapping[child] = parent
    return mapping


def style_ids(package: "DocxPackage | dict[str, bytes]", kind: str | None = None) -> set[str]:
    """Style ids declared in ``word/styles.xml``.

    ``kind`` narrows to one ``w:type``: ``paragraph``, ``character``, ``table``
    or ``numbering`` (a style without a type is a paragraph style). Empty when
    the part is missing or unreadable, so callers refuse rather than write an
    id Word would ignore. Accepts a package or its ``files`` dict.
    """
    files = package.files if isinstance(package, DocxPackage) else package
    data = files.get("word/styles.xml")
    if not data:
        return set()
    try:
        root = parse_xml(data)
    except (ET.ParseError, ValueError):
        return set()
    ids: set[str] = set()
    for style in root.iter(q("style")):
        if kind is not None and style.get(w_attr("type"), "paragraph") != kind:
            continue
        style_id = style.get(w_attr("styleId"))
        if style_id:
            ids.add(style_id)
    return ids


def max_revision_id(files: dict[str, bytes]) -> int:
    highest = 0
    for name, data in files.items():
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        try:
            root = parse_xml(data)
        except ET.ParseError:
            continue
        for el in root.iter():
            value = el.get(w_attr("id"))
            if value and value.isdigit():
                highest = max(highest, int(value))
    return highest


# CT_Settings children that precede w:revisionView / w:trackRevisions (ECMA-376).
_SETTINGS_BEFORE_TRACKING = (
    "writeProtection",
    "view",
    "zoom",
    "removePersonalInformation",
    "removeDateAndTime",
    "doNotDisplayPageBoundaries",
    "displayBackgroundShape",
    "printPostScriptOverText",
    "printFractionalCharacterWidth",
    "printFormsData",
    "embedTrueTypeFonts",
    "embedSystemFonts",
    "saveSubsetFonts",
    "saveFormsData",
    "mirrorMargins",
    "alignBordersAndEdges",
    "bordersDoNotSurroundHeader",
    "bordersDoNotSurroundFooter",
    "gutterAtTop",
    "hideSpellingErrors",
    "hideGrammaticalErrors",
    "activeWritingStyle",
    "proofState",
    "formsDesign",
    "attachedTemplate",
    "linkStyles",
    "stylePaneFormatFilter",
    "stylePaneSortMethod",
    "documentType",
    "mailMerge",
)
_REVISION_VIEW_XML = (
    '<w:revisionView w:markup="true" w:comments="true" w:insDel="true" w:formatting="true"/>'
)


def _settings_child_span(text: str, name: str) -> re.Pattern[str]:
    return re.compile(rf"<w:{name}\b[^>]*/>|<w:{name}\b[^>]*>.*?</w:{name}>", re.DOTALL)


def _insert_settings_child(text: str, fragment: str, after_names: tuple[str, ...]) -> str:
    """Insert ``fragment`` after the last existing settings child in ``after_names``.

    When none of those children exist, insert immediately after ``<w:settings>``.
    That is first-child only when the part has nothing ahead of the tracking
    slot; a Word-like part with ``w:zoom`` keeps zoom first.
    """
    end: int | None = None
    for name in after_names:
        for match in _settings_child_span(text, name).finditer(text):
            if end is None or match.end() > end:
                end = match.end()
    if end is None:
        open_tag = re.search(r"<w:settings\b[^>]*>", text)
        if open_tag is None:
            return text
        end = open_tag.end()
    return text[:end] + fragment + text[end:]


_SETTINGS_CT = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"
)


def enable_track_revisions(files: dict[str, bytes]) -> None:
    if "word/settings.xml" not in files:
        settings = ET.Element(q("settings"))
        ET.SubElement(
            settings,
            q("revisionView"),
            {
                w_attr("markup"): "true",
                w_attr("comments"): "true",
                w_attr("insDel"): "true",
                w_attr("formatting"): "true",
            },
        )
        ET.SubElement(settings, q("trackRevisions"))
        files["word/settings.xml"] = write_tree(settings)
        _ensure_settings_part(files)
        return

    # String-edit settings.xml so Word's namespace declarations stay intact.
    # Rewriting this part with ElementTree is what produced "unreadable content".
    text = files["word/settings.xml"].decode("utf-8")
    if re.search(r"<w:trackRevisions\b[^>]*w:val=\"(?:0|false|off|False)\"", text):
        text = re.sub(r"<w:trackRevisions\b[^/]*/>", "<w:trackRevisions/>", text)
        text = re.sub(
            r"<w:trackRevisions\b[^>]*>\s*</w:trackRevisions>",
            "<w:trackRevisions/>",
            text,
        )
    if "<w:revisionView" not in text:
        text = _insert_settings_child(text, _REVISION_VIEW_XML, _SETTINGS_BEFORE_TRACKING)
    if "<w:trackRevisions" not in text:
        text = _insert_settings_child(
            text, "<w:trackRevisions/>", _SETTINGS_BEFORE_TRACKING + ("revisionView",)
        )
    files["word/settings.xml"] = text.encode("utf-8")


def track_revisions_enabled(files: dict[str, bytes]) -> bool:
    data = files.get("word/settings.xml")
    if not data:
        return False
    root = parse_xml(data)
    return on_off(root.find(q("trackRevisions")))


def revision_view_shows_markup(files: dict[str, bytes]) -> bool | None:
    data = files.get("word/settings.xml")
    if not data:
        return None
    root = parse_xml(data)
    view = root.find(q("revisionView"))
    if view is None:
        return None
    markup = view.get(w_attr("markup"))
    ins_del = view.get(w_attr("insDel"))
    if markup is None and ins_del is None:
        return None
    def _flag(raw: str | None) -> bool:
        if raw is None:
            return True
        return raw not in {"0", "false", "off", "False"}

    return _flag(markup) and _flag(ins_del)


def _ensure_settings_part(files: dict[str, bytes]) -> None:
    _ensure_settings_content_type(files)
    _ensure_settings_rel(files)


def _ensure_settings_content_type(files: dict[str, bytes]) -> None:
    # A WordprocessingML part needs its own Override; the xml Default is not
    # enough for Word, and the structure check rejects a package without one.
    ct_name = "[Content_Types].xml"
    if ct_name not in files:
        return
    original = files[ct_name]
    types = parse_xml(original)
    for node in types:
        if node.get("PartName") == "/word/settings.xml":
            return
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    ET.SubElement(
        types,
        f"{{{ct_ns}}}Override",
        {"PartName": "/word/settings.xml", "ContentType": _SETTINGS_CT},
    )
    # This part declares its namespace as the default, which _register_namespaces
    # does not pick up; without this ElementTree would rewrite it under an ns0
    # prefix.
    ET.register_namespace("", ct_ns)
    files[ct_name] = write_tree(types, original)


def _ensure_settings_rel(files: dict[str, bytes]) -> None:
    rels_name = "word/_rels/document.xml.rels"
    if rels_name not in files:
        return
    rels = parse_xml(files[rels_name])
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    for rel in rels:
        if rel.get("Target") == "settings.xml":
            return
    used = {rel.get("Id", "") for rel in rels}
    rid = 1
    while f"rId{rid}" in used:
        rid += 1
    ET.SubElement(
        rels,
        f"{{{rel_ns}}}Relationship",
        {
            "Id": f"rId{rid}",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings",
            "Target": "settings.xml",
        },
    )
    files[rels_name] = write_tree(rels, files.get(rels_name))


def persist_story(package: DocxPackage, story: Story) -> None:
    original = package.files[story.part_name]
    package.files[story.part_name] = write_tree(story.root, original)
