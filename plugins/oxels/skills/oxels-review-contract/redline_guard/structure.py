"""OPC, revision, comment, and optional ECMA-376 checks (plan §17.1)."""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from redline_guard.ooxml import (
    DEL_TAGS,
    FORMAT_CHANGE_TAGS,
    INS_TAGS,
    NOTE_SEPARATOR_TYPES,
    W_NS,
    paragraph_mark_kind,
    parse_xml,
    q,
    revision_view_shows_markup,
    track_revisions_enabled,
    w_attr,
)

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
W16CID = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
W16CEX = "http://schemas.microsoft.com/office/word/2018/wordml/cex"
STORY_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
WML_PARTS = re.compile(
    r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments|settings|styles|numbering|fontTable|webSettings)\.xml$"
)
REVISION_TAGS = INS_TAGS | DEL_TAGS | FORMAT_CHANGE_TAGS | {
    q("cellIns"),
    q("cellDel"),
    q("cellMerge"),
    q("numberingChange"),
}
ECMA_NAMESPACES = {
    W_NS,
    R_NS,
    XML_NS,
    "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "http://schemas.openxmlformats.org/schemaLibrary/2006/main",
    "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "urn:schemas-microsoft-com:vml",
    "urn:schemas-microsoft-com:office:office",
    "urn:schemas-microsoft-com:office:word",
}
LINE_DIGITS = re.compile(r"\d+")
_SCHEMAS: dict[str, object] = {}


@dataclass
class Defect:
    part: str
    check: str
    message: str
    location: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def key(self) -> tuple[str, str, str]:
        # IDs, target names, and numeric property values identify the defect.
        # Erasing their digits lets a different defect masquerade as preexisting.
        return (self.part, self.check, self.message)


@dataclass
class StructureReport:
    ok: bool
    path: str
    defects: list[Defect] = field(default_factory=list)
    preexisting: list[Defect] = field(default_factory=list)
    schema_checked: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "path": self.path,
            "defects": [d.to_dict() for d in self.defects],
            "preexisting": [d.to_dict() for d in self.preexisting],
            "schema_checked": self.schema_checked,
            "warnings": self.warnings,
        }


class StructureError(ValueError):
    """Structure validation could not run in the requested mode."""


def schema_available() -> bool:
    try:
        import lxml.etree  # noqa: F401
    except ImportError:
        return False
    return (SCHEMA_DIR / "wml-driver.xsd").exists()


def validate_structure(
    path: str | Path,
    original: str | Path | None = None,
    schema: str = "auto",
) -> StructureReport:
    if schema not in {"auto", "required", "off"}:
        raise StructureError(f"Unknown schema mode {schema!r}.")
    need_schema = schema == "required" or (schema == "auto" and schema_available())
    if schema == "required" and not schema_available():
        raise StructureError(
            "lxml is required for schema validation. Install it with: pip install lxml"
        )
    found = _collect_defects(path, run_schema=need_schema)
    warnings = list(found.warnings)
    if schema == "off":
        warnings.append("Schema validation was not run (schema=off).")
    elif not need_schema:
        warnings.append("lxml is not installed; schema layer skipped. Install it with: pip install lxml")
    report = StructureReport(
        ok=not found.defects,
        path=str(path),
        defects=found.defects,
        schema_checked=found.schema_checked,
        warnings=warnings,
    )
    if original is None:
        return report
    baseline = _collect_defects(original, run_schema=need_schema)
    report.warnings.extend(baseline.warnings)
    report.schema_checked = found.schema_checked
    counts: dict[tuple[str, str, str], int] = {}
    for item in baseline.defects:
        counts[item.key()] = counts.get(item.key(), 0) + 1
    fresh: list[Defect] = []
    preexisting: list[Defect] = []
    for item in found.defects:
        key = item.key()
        if counts.get(key, 0) > 0:
            counts[key] -= 1
            preexisting.append(item)
        else:
            fresh.append(item)
    report.defects = fresh
    report.preexisting = preexisting
    report.ok = not fresh
    return report


def _collect_defects(path: str | Path, run_schema: bool) -> StructureReport:
    report = StructureReport(ok=True, path=str(path), schema_checked=False)
    try:
        parts = _package_parts(path)
        with zipfile.ZipFile(path) as archive:
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(names) != len(set(names)):
            report.defects.append(Defect("package", "zip", "Duplicate ZIP member names."))
        for name in names:
            if "\\" in name or name.startswith("/") or posixpath.normpath(name) != name or name.startswith("../"):
                report.defects.append(Defect(name, "zip", "Non-canonical package member name."))
    except (OSError, zipfile.BadZipFile) as exc:
        report.defects.append(Defect("package", "xml", f"Could not open package: {exc}"))
        return report
    roots: dict[str, ET.Element] = {}
    for name, data in parts.items():
        if not name.endswith((".xml", ".rels")):
            continue
        try:
            roots[name] = parse_xml(data)
        except (ET.ParseError, ValueError) as exc:
            report.defects.append(Defect(name, "xml", f"{name} does not parse: {exc}"))
    _check_content_types(parts, roots, report)
    _check_relationships(parts, roots, report)
    _check_references(parts, roots, report)
    _check_revision_ids(roots, report)
    _check_text_nodes(roots, report)
    _check_comment_anchors(roots, report)
    _check_comment_parts(roots, report)
    _check_paragraph_ids(roots, report)
    _check_notes(roots, report)
    _check_settings(parts, report)
    if run_schema:
        _check_schema(parts, report)
    return report


def _package_parts(path: str | Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {info.filename: zf.read(info) for info in zf.infolist() if not info.is_dir()}


def _check_content_types(parts: dict[str, bytes], roots: dict[str, ET.Element], report: StructureReport) -> None:
    root = roots.get("[Content_Types].xml")
    if root is None:
        if "[Content_Types].xml" not in parts:
            report.defects.append(Defect("[Content_Types].xml", "content_types", "Content types part is missing."))
        return
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "Default":
            defaults[el.get("Extension", "").lower()] = el.get("ContentType", "")
        elif tag == "Override":
            key = unquote(el.get("PartName", "")).lstrip("/")
            overrides[key] = el.get("ContentType", "")
            if key not in parts:
                report.defects.append(
                    Defect("[Content_Types].xml", "content_types", f"Override names missing part {key}.")
                )
    for name in parts:
        if name == "[Content_Types].xml":
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        covered = name in overrides or ext in defaults
        if WML_PARTS.match(name) and name not in overrides:
            report.defects.append(
                Defect("[Content_Types].xml", "content_types", f"{name} has no Override.")
            )
        elif not covered:
            report.defects.append(Defect(name, "content_types", f"{name} has no content type."))


def _owner_of_rels(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    directory, base = posixpath.split(rels_name)
    return posixpath.join(posixpath.dirname(directory), base[: -len(".rels")])


def _check_relationships(parts: dict[str, bytes], roots: dict[str, ET.Element], report: StructureReport) -> None:
    for name, root in roots.items():
        if not name.endswith(".rels"):
            continue
        owner = _owner_of_rels(name)
        for rel in root:
            if rel.tag.split("}")[-1] != "Relationship":
                continue
            if rel.get("TargetMode") == "External":
                continue
            target = unquote((rel.get("Target") or "").split("#", 1)[0])
            if not target:
                continue
            if target.startswith("/"):
                resolved = target.lstrip("/")
            else:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))
            if resolved not in parts:
                report.defects.append(
                    Defect(name, "relationship", f"{name} relationship targets missing part {target}.")
                )


def _rels_for_part(part: str) -> str:
    directory, base = posixpath.split(part)
    return posixpath.join(directory, "_rels", base + ".rels") if directory else "_rels/.rels"


def _relationship_ids(roots: dict[str, ET.Element], rels_name: str) -> set[str]:
    root = roots.get(rels_name)
    if root is None:
        return set()
    return {el.get("Id", "") for el in root if el.tag.split("}")[-1] == "Relationship"}


def _check_references(parts: dict[str, bytes], roots: dict[str, ET.Element], report: StructureReport) -> None:
    for name, root in roots.items():
        if name.endswith(".rels") or name == "[Content_Types].xml":
            continue
        rels = _relationship_ids(roots, _rels_for_part(name))
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            for attr, value in el.attrib.items():
                if not attr.startswith(f"{{{R_NS}}}"):
                    continue
                local = attr.split("}")[-1]
                if local not in {"id", "embed", "link"}:
                    continue
                if value not in rels:
                    report.defects.append(
                        Defect(
                            name,
                            "reference",
                            f"{name} attribute r:{local}={value} names no relationship.",
                            location=value,
                        )
                    )


def _check_revision_ids(roots: dict[str, ET.Element], report: StructureReport) -> None:
    seen: dict[str, str] = {}
    for name, root in sorted(roots.items()):
        if not STORY_PARTS.match(name):
            continue
        for el in root.iter():
            if el.tag not in REVISION_TAGS:
                continue
            rid = el.get(w_attr("id"), "")
            if not rid:
                continue
            if rid in seen:
                report.defects.append(
                    Defect(
                        name,
                        "revision_id",
                        f"Revision id {rid} is used in both {seen[rid]} and {name}.",
                        location=rid,
                    )
                )
            else:
                seen[rid] = name
            if not el.get(w_attr("author")) or not el.get(w_attr("date")):
                report.defects.append(
                    Defect(name, "revision_id", f"Revision {rid} is missing author or date.", location=rid)
                )


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    mapping: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            mapping[child] = parent
    return mapping


def _nearest_revision(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> str | None:
    current = parents.get(el)
    while current is not None:
        if current.tag in INS_TAGS | DEL_TAGS:
            return current.tag
        current = parents.get(current)
    return None


def _check_text_nodes(roots: dict[str, ET.Element], report: StructureReport) -> None:
    for name, root in roots.items():
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        parents = _parent_map(root)
        for el in root.iter():
            if el.tag not in {q("t"), q("delText"), q("instrText")}:
                continue
            nearest = _nearest_revision(el, parents)
            text = el.text or ""
            if el.tag == q("t") and nearest in DEL_TAGS:
                report.defects.append(Defect(name, "text_node", f"{name}: w:t inside a deletion ({text[:40]!r})."))
            elif el.tag == q("delText") and nearest not in DEL_TAGS:
                report.defects.append(Defect(name, "text_node", f"{name}: w:delText outside a deletion ({text[:40]!r})."))
            elif el.tag == q("instrText") and nearest in DEL_TAGS:
                report.defects.append(Defect(name, "text_node", f"{name}: w:instrText inside a deletion."))
            if text == "":
                report.defects.append(Defect(name, "text_node", f"{name}: empty <w:{el.tag.split('}')[-1]}>."))
            elif text[:1] == " " or text[-1:] == " " or "\t" in text:
                if el.get(f"{{{XML_NS}}}space") != "preserve":
                    report.defects.append(
                        Defect(name, "text_node", f"{name}: missing xml:space on {text[:30]!r}.")
                    )


ANCHOR_ORDER = ["commentRangeStart", "commentRangeEnd", "commentReference"]


def _check_comment_anchors(roots: dict[str, ET.Element], report: StructureReport) -> None:
    """Every comment body, replies included, needs its three markers in some story.

    Word shows nothing for a comment without a reference run, and a reply
    without its own range is not listed under its parent, so a body that
    lacks any of the three is reported with the markers it lacks.
    """
    bodies: list[str] = []
    if "word/comments.xml" in roots:
        bodies = [cid for cid in (el.get(w_attr("id"), "") for el in roots["word/comments.xml"].iter(q("comment"))) if cid]
    from redline_guard.ooxml import iter_outside_fallback

    used: dict[str, list[tuple[str, str]]] = {}
    for name, root in roots.items():
        if not STORY_PARTS.match(name):
            continue
        # A text box's mc:Fallback carries the same markers as its listed
        # mc:Choice copy, as Word writes them; only the Choice copy is counted.
        for el in iter_outside_fallback(root):
            local = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
            if local not in ANCHOR_ORDER:
                continue
            used.setdefault(el.get(w_attr("id"), ""), []).append((name, local))
    for cid, seq in used.items():
        locals_only = [local for _part, local in seq]
        part = seq[0][0]
        if locals_only != ANCHOR_ORDER and set(locals_only) == set(ANCHOR_ORDER):
            report.defects.append(
                Defect(
                    part,
                    "comment_anchor",
                    f"comment {cid} anchors are duplicated or out of order: {locals_only}.",
                    location=cid,
                )
            )
        if cid not in bodies:
            report.defects.append(
                Defect("word/comments.xml", "comment_anchor", f"commentReference {cid} has no comment body.", location=cid)
            )
    for cid in bodies:
        present = {local for _part, local in used.get(cid, [])}
        missing = [local for local in ANCHOR_ORDER if local not in present]
        if missing:
            report.defects.append(
                Defect(
                    "word/comments.xml",
                    "comment_anchor",
                    f"comment body {cid} has no {', '.join(missing)} in any story; Word shows nothing for it.",
                    location=cid,
                )
            )


def _check_notes(roots: dict[str, ET.Element], report: StructureReport) -> None:
    """Footnotes and endnotes stay openable and consistent with their references.

    Word never writes a note without a paragraph, cannot delete a note's last
    paragraph mark, and strikes a note's text together with its reference.
    """
    for part, note_tag, ref_tag, label in (
        ("word/footnotes.xml", "footnote", "footnoteReference", "footnote"),
        ("word/endnotes.xml", "endnote", "endnoteReference", "endnote"),
    ):
        root = roots.get(part)
        if root is None:
            continue
        live: set[str] = set()
        struck: set[str] = set()
        where: dict[str, str] = {}
        for name, story_root in roots.items():
            if not STORY_PARTS.match(name) or name == part:
                continue
            parents = _parent_map(story_root)
            for el in story_root.iter(q(ref_tag)):
                nid = el.get(w_attr("id"), "")
                (struck if _nearest_revision(el, parents) in DEL_TAGS else live).add(nid)
                where.setdefault(nid, name)
        for note in root.iter(q(note_tag)):
            if note.get(w_attr("type")) in NOTE_SEPARATOR_TYPES:
                continue
            nid = note.get(w_attr("id"), "")
            paragraphs = [child for child in note if child.tag == q("p")] or list(note.iter(q("p")))
            if not paragraphs:
                report.defects.append(
                    Defect(part, label, f"{label} {nid} has no paragraph; Word cannot open a {label} without one.", location=nid)
                )
                continue
            if paragraph_mark_kind(paragraphs[-1]) == "del":
                report.defects.append(
                    Defect(
                        part,
                        label,
                        f"{label} {nid}: its last paragraph mark is a tracked deletion, so accepting it leaves the {label} "
                        f"without a paragraph; delete the {ref_tag} in the text instead, or keep the mark and strike only the text.",
                        location=nid,
                    )
                )
            if nid in struck and nid not in live and _has_live_text(note):
                report.defects.append(
                    Defect(
                        part,
                        label,
                        f"{label} {nid}: its reference in {where.get(nid, 'the text')} is a tracked deletion but the {label} text is not; "
                        f"Word strikes the {label} text together with its reference.",
                        location=nid,
                    )
                )


def _has_live_text(note: ET.Element) -> bool:
    parents = _parent_map(note)
    return any((el.text or "").strip() and _nearest_revision(el, parents) not in DEL_TAGS for el in note.iter(q("t")))


def _check_comment_parts(roots: dict[str, ET.Element], report: StructureReport) -> None:
    comments = roots.get("word/comments.xml")
    if comments is None:
        return
    para_ids: list[str] = []
    for el in comments.iter(q("p")):
        pid = el.get(f"{{{W14}}}paraId")
        if pid:
            para_ids.append(pid)
    if len(para_ids) != len(set(para_ids)):
        report.defects.append(Defect("word/comments.xml", "comment_part", "duplicate comment paraIds."))
    for pid in para_ids:
        try:
            value = int(pid, 16)
        except ValueError:
            report.defects.append(Defect("word/comments.xml", "comment_part", f"comment paraId {pid} is not hex."))
            continue
        if not 0 < value < 0x80000000:
            report.defects.append(
                Defect("word/comments.xml", "comment_part", f"comment paraId {pid} is at or above 80000000.")
            )
    want = set(para_ids)
    for part, attr, label in (
        ("word/commentsExtended.xml", f"{{{W15}}}paraId", "commentsExtended"),
        ("word/commentsIds.xml", f"{{{W16CID}}}paraId", "commentsIds"),
    ):
        root = roots.get(part)
        if root is None:
            continue
        got = {el.get(attr) for el in root if el.get(attr)}
        if got != want:
            report.defects.append(
                Defect(part, "comment_part", f"{label} paraIds do not match comments.xml.")
            )
    ids_root = roots.get("word/commentsIds.xml")
    cex = roots.get("word/commentsExtensible.xml")
    if ids_root is not None and cex is not None:
        durable = {el.get(f"{{{W16CID}}}durableId") for el in ids_root if el.get(f"{{{W16CID}}}durableId")}
        extra = {el.get(f"{{{W16CEX}}}durableId") for el in cex if el.get(f"{{{W16CEX}}}durableId")} - durable
        if extra:
            report.defects.append(
                Defect(
                    "word/commentsExtensible.xml",
                    "comment_part",
                    "commentsExtensible durableIds are not a subset of commentsIds.",
                )
            )


def _check_paragraph_ids(roots: dict[str, ET.Element], report: StructureReport) -> None:
    for name, root in roots.items():
        if not STORY_PARTS.match(name):
            continue
        seen: set[str] = set()
        for el in root.iter(q("p")):
            pid = el.get(f"{{{W14}}}paraId")
            if not pid:
                continue
            try:
                value = int(pid, 16)
            except ValueError:
                report.defects.append(Defect(name, "paragraph_id", f"{name} paraId {pid} is not hex."))
                continue
            if not 0 < value < 0x80000000:
                report.defects.append(Defect(name, "paragraph_id", f"{name} paraId {pid} is at or above 80000000."))
            if pid in seen:
                report.defects.append(Defect(name, "paragraph_id", f"{name} duplicate paraId {pid}."))
            seen.add(pid)


def _check_settings(parts: dict[str, bytes], report: StructureReport) -> None:
    # Advisory on validate: counterparty originals often have tracking off.
    # finalize enforces both on the send file.
    if not track_revisions_enabled(parts):
        report.warnings.append("w:trackRevisions is missing or off.")
    if revision_view_shows_markup(parts) is False:
        report.warnings.append("w:revisionView hides markup.")


def _strip_extensions(root, warnings: list[str] | None = None) -> object:
    """Project declared ignorable content; preserve unknown mandatory XML.

    This operates on the validation copy only. Unknown mandatory extensions
    must fail instead of disappearing before the schema sees them.
    """
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"

    def ns(tag):
        return tag[1:].split("}", 1)[0] if isinstance(tag, str) and tag.startswith("{") else ""

    def visit(el, inherited, inherited_process):
        ignorable = set(inherited)
        process = set(inherited_process)
        for prefix in el.get(f"{{{mc}}}Ignorable", "").split():
            if prefix not in el.nsmap:
                raise ValueError(f"Undeclared mc:Ignorable prefix {prefix!r}.")
            ignorable.add(el.nsmap[prefix])
        for prefix in el.get(f"{{{mc}}}MustUnderstand", "").split():
            if el.nsmap.get(prefix) not in ECMA_NAMESPACES:
                raise ValueError(f"Unsupported mc:MustUnderstand namespace {prefix!r}.")
        for name in el.get(f"{{{mc}}}ProcessContent", "").split():
            prefix, local = name.split(":", 1) if ":" in name else (None, name)
            if el.nsmap.get(prefix) is None:
                raise ValueError(f"Undeclared mc:ProcessContent name {name!r}.")
            process.add(f"{{{el.nsmap[prefix]}}}{local}")
        for attr in list(el.attrib):
            if ns(attr) == mc or (ns(attr) in ignorable and ns(attr) not in ECMA_NAMESPACES):
                del el.attrib[attr]
        for child in list(el):
            if not isinstance(child.tag, str):
                el.remove(child)
            elif child.tag == f"{{{mc}}}AlternateContent":
                chosen = None
                for branch in child:
                    if branch.tag == f"{{{mc}}}Choice" and all(branch.nsmap.get(p) in ECMA_NAMESPACES for p in branch.get("Requires", "").split()):
                        chosen = branch
                        break
                    if branch.tag == f"{{{mc}}}Fallback":
                        chosen = branch
                if chosen is None:
                    raise ValueError("AlternateContent has no supported choice or fallback.")
                visit(chosen, ignorable, process)
                index = el.index(child)
                el.remove(child)
                for offset, item in enumerate(list(chosen)):
                    el.insert(index + offset, item)
                if warnings is not None:
                    warnings.append("Schema validation checks the supported AlternateContent branch, not every extension branch.")
            elif ns(child.tag) in ignorable and ns(child.tag) not in ECMA_NAMESPACES:
                if child.tag in process:
                    visit(child, ignorable, process)
                    index = el.index(child)
                    for offset, item in enumerate(list(child)):
                        el.insert(index + offset, item)
                el.remove(child)
                if warnings is not None:
                    warnings.append("Declared ignorable extension payloads are outside ECMA schema coverage.")
            else:
                visit(child, ignorable, process)

    visit(root, set(), set())
    return root


def _schema(kind: str):
    import lxml.etree as LX

    if kind not in _SCHEMAS:
        paths = {
            "wml": SCHEMA_DIR / "wml-driver.xsd",
            "content-types": SCHEMA_DIR / "opc" / "opc-contentTypes.xsd",
            "relationships": SCHEMA_DIR / "opc" / "opc-relationships.xsd",
        }
        _SCHEMAS[kind] = LX.XMLSchema(LX.parse(str(paths[kind])))
    return _SCHEMAS[kind]


def _check_schema(parts: dict[str, bytes], report: StructureReport) -> None:
    import lxml.etree as LX

    report.schema_checked = True
    for name, data in sorted(parts.items()):
        if WML_PARTS.match(name):
            kind, strip = "wml", True
        elif name == "[Content_Types].xml":
            kind, strip = "content-types", False
        elif name.endswith(".rels"):
            kind, strip = "relationships", False
        else:
            continue
        try:
            root = LX.fromstring(data, LX.XMLParser(resolve_entities=False, no_network=True))
            if root.getroottree().docinfo.doctype:
                raise ValueError("DTD declarations are not supported in DOCX parts.")
            if strip:
                root = _strip_extensions(root, report.warnings)
        except (LX.XMLSyntaxError, ValueError) as exc:
            report.defects.append(Defect(name, "schema", f"{name} is not well-formed: {exc}"))
            continue
        schema = _schema(kind)
        if schema.validate(root):
            continue
        err = next(iter(schema.error_log), None)
        message = err.message if err is not None else "schema validation failed"
        report.defects.append(Defect(name, "schema", f"{name}: {message}".strip()))
    report.warnings = sorted(set(report.warnings))
