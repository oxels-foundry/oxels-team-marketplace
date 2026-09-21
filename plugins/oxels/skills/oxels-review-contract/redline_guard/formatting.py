"""Formatting integrity of original content (plan §17.2)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from redline_guard.ooxml import (
    DEL_TAGS,
    FORMAT_CHANGE_TAGS,
    INS_TAGS,
    SKIP_TAGS,
    WRAPPER_TAGS,
    inline_char,
    load_docx,
    parse_xml,
    parent_map_from,
    persist_story,
    save_docx,
    q,
    w_attr,
)
from redline_guard.resolution_log import DEFAULT_AUTHOR, log_path_for, read_resolution_log, resolution_entry_key

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CHANGE_LOCAL = {tag.split("}")[-1] for tag in FORMAT_CHANGE_TAGS}
UNORDERED = {"rPr", "pPr", "sectPr", "tblPr", "trPr", "tcPr"}
DROP_ELS = {"proofErr", "lastRenderedPageBreak"}
PROP_MARKERS = {"ins", "del", "moveFrom", "moveTo"}
IGNORE_SETTINGS = {"rsids", "trackRevisions", "revisionView", "proofState"}
BOOLEAN_TAGS = {
    "b", "i", "strike", "dstrike", "vanish", "specVanish", "smallCaps", "caps",
    "emboss", "imprint", "outline", "shadow", "rtl", "cs", "noProof", "snapToGrid",
    "keepNext", "keepLines", "pageBreakBefore", "widowControl", "autoSpaceDE",
    "autoSpaceDN", "adjustRightInd", "bidi", "contextualSpacing", "mirrorIndents",
    "suppressAutoHyphens", "suppressOverlap", "cantSplit", "tblHeader", "hidden",
}
ON_VALUES = {None, "", "1", "true", "on", "True"}
OFF_VALUES = {"0", "false", "off", "False"}


@dataclass
class FormattingFailure:
    kind: str
    location: str
    story: str
    paragraph: int
    property: str
    original: str
    edited: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FormattingReport:
    ok: bool
    original: str
    edited: str
    failures: list[FormattingFailure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "original": self.original,
            "edited": self.edited,
            "failures": [f.to_dict() for f in self.failures],
            "notes": self.notes,
        }


def compare_formatting(
    original: str | Path,
    edited: str | Path,
    author: str = DEFAULT_AUTHOR,
    resolved: list[str | Path] | None = None,
) -> FormattingReport:
    report = FormattingReport(ok=True, original=str(original), edited=str(edited))
    from redline_guard.verify import (
        VerifyReport, _load_resolution_entries, _resolved_baseline,
        _recognized_edit_keys, _revision_key,
    )
    from redline_guard.resolve import _index_revisions, _resolve_element, list_revisions

    trace = VerifyReport(ok=True, original=str(original), edited=str(edited))
    logged, _ = _load_resolution_entries(original, edited, resolved or [], trace)
    # Resolve the exact logged spans, including repeated partial decisions. Then
    # undo only newly added text revisions in an internal copy. This aligns the
    # original characters without skipping paragraphs or excluding old revisions
    # merely because their author happens to be the current agent.
    with _resolved_baseline(original, logged, trace) as baseline:
        orig = load_docx(baseline)
        edit = load_docx(edited)
        before = list_revisions(baseline)
        after = list_revisions(edited)
        existing = {r.rev_id for r in before}
        recognized = _recognized_edit_keys(before, after, baseline, edited)
        for rev in after:
            if rev.kind not in {"ins", "del"} or rev.rev_id in existing or _revision_key(rev) in recognized:
                continue
            if rev.author != author:
                continue
            current = _index_revisions(edit).get(rev.rev_id)
            if current is None:
                continue
            kind, element, story = current
            _resolve_element(element, parent_map_from(story.root), kind, "reject")
        for story in edit.stories:
            persist_story(edit, story)
        with tempfile.TemporaryDirectory(prefix="redline-formatting-") as folder:
            projected = Path(folder) / "projected.docx"
            save_docx(edit, projected)
            edit = load_docx(projected)
            _attach_files(orig)
            _attach_files(edit)
            orig_stories = {s.name: s for s in orig.stories}
            edit_stories = {s.name: s for s in edit.stories}
            for name in sorted(set(orig_stories) | set(edit_stories)):
                if name not in orig_stories or name not in edit_stories:
                    report.failures.append(FormattingFailure("alignment", name, name, 0, "story", "present" if name in orig_stories else "missing", "present" if name in edit_stories else "missing", "Story structure could not be aligned after replaying decisions."))
                    continue
                _compare_story(orig_stories[name], edit_stories[name], author, set(), report)
            _compare_document_level(orig, edit, author, set(), report)
    for failure in trace.failures:
        report.failures.append(FormattingFailure("resolution_log", failure.location, failure.story, failure.paragraph, "log", "", "", failure.message))
    report.ok = not report.failures
    return report


def _resolved_drop_ids(original: str | Path, edited: str | Path, extra: list[str | Path]) -> set[str]:
    paths: list[str | Path] = []
    auto = log_path_for(edited)
    if auto.exists():
        paths.append(auto)
    paths.extend(extra)
    drop: set[str] = set()
    seen: set[str] = set()
    for path in paths:
        try:
            data = read_resolution_log(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for item in data.get("resolved") or []:
            rev_id = str(item.get("id", ""))
            key = resolution_entry_key(item)
            if not rev_id or key in seen:
                continue
            seen.add(key)
            action = str(item.get("action", "")).lower()
            kind = str(item.get("kind", "")).lower()
            if action == "accept" and kind in {"", "del", "delete"}:
                drop.add(rev_id)
            elif action == "reject" and kind in {"", "ins", "insert"}:
                drop.add(rev_id)
            elif action == "accept" and "del" in kind:
                drop.add(rev_id)
            elif action == "reject" and "ins" in kind:
                drop.add(rev_id)
            elif action == "accept":
                # Accepting a deletion removes those characters from the domain.
                if kind != "ins":
                    drop.add(rev_id)
            elif action == "reject":
                if kind != "del":
                    drop.add(rev_id)
    return drop


def _compare_story(orig_story, edit_story, author: str, drop_ids: set[str], report: FormattingReport) -> None:
    if len(orig_story.paragraphs) != len(edit_story.paragraphs):
        report.failures.append(FormattingFailure("alignment", orig_story.name, orig_story.name, 0, "paragraph count", str(len(orig_story.paragraphs)), str(len(edit_story.paragraphs)), "Paragraphs could not be aligned after undoing new text revisions."))
    for orig_p, edit_p in zip(orig_story.paragraphs, edit_story.paragraphs):
        orig_chars = _domain_chars(orig_p.element, author=author, skip_agent_ins=False, drop_ids=drop_ids)
        edit_chars = _domain_chars(edit_p.element, author=author, skip_agent_ins=False, drop_ids=drop_ids)
        if "".join(c[0] for c in orig_chars) != "".join(c[0] for c in edit_chars):
            report.failures.append(FormattingFailure("alignment", edit_p.location, edit_p.story, edit_p.index, "text", "".join(c[0] for c in orig_chars)[:160], "".join(c[0] for c in edit_chars)[:160], "Original characters could not be aligned for a formatting check."))
            continue
        _compare_runs(orig_p, edit_p, orig_chars, edit_chars, author, report)
        _compare_paragraph_props(orig_p, edit_p, author, report)
        _compare_numbering(orig_p, edit_p, orig_story, edit_story, report)
    _compare_sections(orig_story, edit_story, author, report)
    _compare_tables(orig_story, edit_story, author, drop_ids, report)


def _align_paragraphs(original, edited, author: str, drop_ids: set[str]):
    pairs = []
    i = j = 0
    while i < len(original) and j < len(edited):
        if _agent_inserted_paragraph(edited[j], author):
            j += 1
            continue
        if original[i].reject_text == edited[j].reject_text:
            pairs.append((original[i], edited[j]))
            i += 1
            j += 1
            continue
        orig_dom = "".join(c[0] for c in _domain_chars(original[i].element, author, False, drop_ids))
        edit_dom = "".join(c[0] for c in _domain_chars(edited[j].element, author, True, drop_ids))
        if orig_dom == edit_dom:
            pairs.append((original[i], edited[j]))
            i += 1
            j += 1
            continue
        if i + 1 < len(original) and original[i + 1].reject_text == edited[j].reject_text:
            i += 1
            continue
        if not edited[j].reject_text.strip() and j + 1 < len(edited):
            j += 1
            continue
        if j + 1 < len(edited) and original[i].reject_text == edited[j + 1].reject_text:
            j += 1
            continue
        i += 1
        j += 1
    return pairs


def _agent_inserted_paragraph(para, author: str) -> bool:
    if para.reject_text.strip():
        return False
    for rev in para.revisions:
        if rev.kind == "ins" and rev.author == author:
            return True
    mark = para.element.find(f"{q('pPr')}/{q('rPr')}")
    if mark is not None:
        for child in mark:
            if child.tag in INS_TAGS and child.get(w_attr("author"), "") == author:
                return True
    return not para.accept_text.strip() and not para.reject_text.strip()


def _domain_chars(paragraph: ET.Element, author: str, skip_agent_ins: bool, drop_ids: set[str]) -> list[tuple[str, ET.Element]]:
    refs: list[tuple[str, ET.Element]] = []

    def take(run: ET.Element) -> None:
        for node in run:
            text = inline_char(node)
            for ch in text or "":
                refs.append((ch, run))

    def walk(el: ET.Element, in_ins: ET.Element | None, in_del: ET.Element | None) -> None:
        for child in el:
            tag = child.tag
            if tag in SKIP_TAGS:
                continue
            if tag in INS_TAGS:
                rid = child.get(w_attr("id"), "")
                if rid in drop_ids:
                    continue
                if skip_agent_ins and child.get(w_attr("author"), "") == author:
                    continue
                walk(child, child, in_del)
                continue
            if tag in DEL_TAGS:
                rid = child.get(w_attr("id"), "")
                if rid in drop_ids:
                    continue
                walk(child, in_ins, child)
                continue
            if tag == q("r"):
                take(child)
                continue
            if tag in WRAPPER_TAGS:
                walk(child, in_ins, in_del)
                continue
            walk(child, in_ins, in_del)

    walk(paragraph, None, None)
    return refs


def _compare_runs(orig_p, edit_p, orig_chars, edit_chars, author: str, report: FormattingReport) -> None:
    for (och, orun), (ech, erun) in zip(orig_chars, edit_chars):
        if och != ech:
            return
        orig_pr = _normalize(orun.find(q("rPr")))
        edit_pr = _normalize(erun.find(q("rPr")))
        if orig_pr == edit_pr:
            continue
        if _explained(erun.find(q("rPr")), orig_pr, author, q("rPrChange")):
            continue
        prop, orig_val, edit_val = _first_diff(orig_pr, edit_pr)
        change = _find_change(erun.find(q("rPr")), q("rPrChange"))
        message = f"run property {prop} differs"
        if change is not None:
            message = f"recorded old properties differ from the original ({prop})"
        report.failures.append(
            FormattingFailure(
                kind="run",
                location=edit_p.location,
                story=edit_p.story,
                paragraph=edit_p.index,
                property=prop,
                original=orig_val,
                edited=edit_val,
                message=message,
            )
        )
        return


def _compare_paragraph_props(orig_p, edit_p, author: str, report: FormattingReport) -> None:
    orig_pr = orig_p.element.find(q("pPr"))
    edit_pr = edit_p.element.find(q("pPr"))
    orig_n = _normalize(orig_pr)
    edit_n = _normalize(edit_pr)
    if orig_n == edit_n:
        return
    if _explained(edit_pr, orig_n, author, q("pPrChange")):
        return
    prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
    report.failures.append(
        FormattingFailure(
            kind="paragraph",
            location=edit_p.location,
            story=edit_p.story,
            paragraph=edit_p.index,
            property=prop,
            original=orig_val,
            edited=edit_val,
            message=f"paragraph property {prop} differs",
        )
    )


def _compare_numbering(orig_p, edit_p, orig_story, edit_story, report: FormattingReport) -> None:
    orig_num = _num_pr(orig_p.element)
    if orig_num is None:
        return
    orig_lvl = _resolved_level(orig_story, orig_num)
    edit_num = _num_pr(edit_p.element)
    edit_lvl = _resolved_level(edit_story, edit_num if edit_num is not None else orig_num)
    orig_n = _normalize(orig_lvl)
    edit_n = _normalize(edit_lvl)
    if orig_n == edit_n:
        return
    prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
    report.failures.append(
        FormattingFailure(
            kind="numbering",
            location=edit_p.location,
            story=edit_p.story,
            paragraph=edit_p.index,
            property=prop or "lvl",
            original=orig_val,
            edited=edit_val,
            message=f"numbering level {prop} differs",
        )
    )


def _num_pr(paragraph: ET.Element) -> ET.Element | None:
    ppr = paragraph.find(q("pPr"))
    return None if ppr is None else ppr.find(q("numPr"))


def _resolved_level(story, num_pr: ET.Element | None) -> ET.Element | None:
    if num_pr is None:
        return None
    return _resolved_level_from_files(getattr(story, "files", {}) or {}, num_pr)


def _resolved_level_from_files(files: dict[str, bytes], num_pr: ET.Element) -> ET.Element | None:
    data = files.get("word/numbering.xml")
    if not data:
        return num_pr
    root = parse_xml(data)
    num_id = _val(num_pr.find(q("numId")))
    ilvl = _val(num_pr.find(q("ilvl"))) or "0"
    abstract = None
    override = None
    for num in root.iter(q("num")):
        if num.get(w_attr("numId")) == num_id:
            aid = num.find(q("abstractNumId"))
            abstract = None if aid is None else aid.get(w_attr("val"))
            for item in num.iter(q("lvlOverride")):
                if item.get(w_attr("ilvl")) == ilvl:
                    override = item.find(q("lvl"))
            break
    if override is not None:
        return override
    for absn in root.iter(q("abstractNum")):
        if absn.get(w_attr("abstractNumId")) == abstract:
            for lvl in absn.iter(q("lvl")):
                if lvl.get(w_attr("ilvl")) == ilvl:
                    return lvl
    return num_pr


def _attach_files(package) -> None:
    for story in package.stories:
        story.files = package.files  # type: ignore[attr-defined]


def _compare_sections(orig_story, edit_story, author: str, report: FormattingReport) -> None:
    orig_sects = _sect_list(orig_story, orig_story.files)
    edit_sects = _sect_list(edit_story, edit_story.files)
    if len(orig_sects) != len(edit_sects):
        report.failures.append(
            FormattingFailure(
                kind="section",
                location=f"{edit_story.name} sections",
                story=edit_story.name,
                paragraph=0,
                property="count",
                original=str(len(orig_sects)),
                edited=str(len(edit_sects)),
                message="section count differs",
            )
        )
        return
    for orig_el, edit_el in zip(orig_sects, edit_sects):
        orig_n = _normalize(_rewrite_header_refs(orig_el, orig_story.files, orig_story.part_name))
        edit_n = _normalize(_rewrite_header_refs(edit_el, edit_story.files, edit_story.part_name))
        if orig_n == edit_n:
            continue
        if _explained(edit_el, orig_n, author, q("sectPrChange")):
            continue
        prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
        report.failures.append(
            FormattingFailure(
                kind="section",
                location=f"{edit_story.name} section",
                story=edit_story.name,
                paragraph=0,
                property=prop,
                original=orig_val,
                edited=edit_val,
                message=f"section property {prop} differs",
            )
        )
        return


def _sect_list(story, files: dict[str, bytes]) -> list[ET.Element]:
    root = story.root
    found = [el for el in root.iter(q("sectPr"))]
    return found


def _rewrite_header_refs(sect: ET.Element, files: dict[str, bytes], part_name: str) -> ET.Element:
    cloned = ET.fromstring(ET.tostring(sect, encoding="utf-8"))
    rels = _rels_map(files, part_name)
    for el in cloned.iter():
        local = _local(el.tag)
        if local not in {"headerReference", "footerReference"}:
            continue
        rid = None
        for attr, value in list(el.attrib.items()):
            if attr.endswith("}id") or attr == "id" or attr.split("}")[-1] == "id":
                if attr.startswith(f"{{{R_NS}}}") or attr.endswith("}id"):
                    rid = value
                    del el.attrib[attr]
        if rid and rid in rels:
            el.set("target", rels[rid])
    return cloned


def _rels_map(files: dict[str, bytes], part_name: str) -> dict[str, str]:
    directory, base = part_name.rsplit("/", 1) if "/" in part_name else ("", part_name)
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    data = files.get(rels_name)
    if not data:
        return {}
    root = parse_xml(data)
    return {el.get("Id", ""): el.get("Target", "") for el in root if el.tag.split("}")[-1] == "Relationship"}


def _compare_tables(orig_story, edit_story, author: str, drop_ids: set[str], report: FormattingReport) -> None:
    orig_tbls = list(orig_story.root.iter(q("tbl")))
    edit_tbls = list(edit_story.root.iter(q("tbl")))
    for orig_tbl, edit_tbl in zip(orig_tbls, edit_tbls):
        for tag, kind_prop in ((q("tblPr"), "tblPr"), (q("tblGrid"), "tblGrid")):
            orig_n = _normalize(orig_tbl.find(tag))
            edit_n = _normalize(edit_tbl.find(tag))
            if orig_n == edit_n:
                continue
            change_tag = q("tblPrChange") if tag == q("tblPr") else q("tblGridChange")
            if tag == q("tblPr") and _explained(edit_tbl.find(tag), orig_n, author, change_tag):
                continue
            prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
            report.failures.append(
                FormattingFailure(
                    kind="table",
                    location=f"{edit_story.name} table",
                    story=edit_story.name,
                    paragraph=0,
                    property=prop or kind_prop,
                    original=orig_val,
                    edited=edit_val,
                    message=f"table property {prop} differs",
                )
            )
            return
        orig_rows = [row for row in orig_tbl.findall(q("tr")) if not _row_dropped(row, drop_ids)]
        edit_rows = [row for row in edit_tbl.findall(q("tr")) if not _row_dropped(row, drop_ids)]
        for orig_row, edit_row in zip(orig_rows, edit_rows):
            orig_n = _normalize(orig_row.find(q("trPr")))
            edit_n = _normalize(edit_row.find(q("trPr")))
            if orig_n != edit_n and not _explained(edit_row.find(q("trPr")), orig_n, author, q("trPrChange")):
                prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
                report.failures.append(
                    FormattingFailure(
                        kind="table",
                        location=f"{edit_story.name} table row",
                        story=edit_story.name,
                        paragraph=0,
                        property=prop or "trPr",
                        original=orig_val,
                        edited=edit_val,
                        message=f"table row property {prop} differs",
                    )
                )
                return
            orig_cells = orig_row.findall(q("tc"))
            edit_cells = edit_row.findall(q("tc"))
            for orig_cell, edit_cell in zip(orig_cells, edit_cells):
                orig_n = _normalize(orig_cell.find(q("tcPr")))
                edit_n = _normalize(edit_cell.find(q("tcPr")))
                if orig_n == edit_n or _explained(edit_cell.find(q("tcPr")), orig_n, author, q("tcPrChange")):
                    continue
                prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
                report.failures.append(
                    FormattingFailure(
                        kind="table",
                        location=f"{edit_story.name} table cell",
                        story=edit_story.name,
                        paragraph=0,
                        property=prop or "tcPr",
                        original=orig_val,
                        edited=edit_val,
                        message=f"table cell property {prop} differs",
                    )
                )
                return


def _row_dropped(row: ET.Element, drop_ids: set[str]) -> bool:
    trpr = row.find(q("trPr"))
    if trpr is None:
        return False
    for child in trpr:
        if child.tag in INS_TAGS | DEL_TAGS and child.get(w_attr("id"), "") in drop_ids:
            return True
    return False


def _compare_document_level(orig, edit, author: str, drop_ids: set[str], report: FormattingReport) -> None:
    _attach_files(orig)
    _attach_files(edit)
    _compare_styles(orig.files, edit.files, report)
    _compare_settings(orig.files, edit.files, report)
    _compare_fonts(orig.files, edit.files, report)
    _compare_equal_part(orig.files, edit.files, "word/webSettings.xml", report)
    for name in sorted(set(orig.files) | set(edit.files)):
        if name.startswith("word/theme/") and name.endswith(".xml"):
            _compare_equal_part(orig.files, edit.files, name, report)


def _compare_styles(orig_files: dict[str, bytes], edit_files: dict[str, bytes], report: FormattingReport) -> None:
    orig_root = _optional_root(orig_files, "word/styles.xml")
    edit_root = _optional_root(edit_files, "word/styles.xml")
    if orig_root is None or edit_root is None:
        return
    orig_defaults = _normalize(orig_root.find(q("docDefaults")))
    edit_defaults = _normalize(edit_root.find(q("docDefaults")))
    if orig_defaults != edit_defaults:
        prop, orig_val, edit_val = _first_diff(orig_defaults, edit_defaults)
        report.failures.append(
            FormattingFailure("style", "word/styles.xml", "styles", 0, prop or "docDefaults", orig_val, edit_val, "docDefaults differ")
        )
        return
    orig_styles = {_style_id(el): el for el in orig_root.iter(q("style"))}
    edit_styles = {_style_id(el): el for el in edit_root.iter(q("style"))}
    for sid, orig_el in orig_styles.items():
        if sid not in edit_styles:
            report.failures.append(
                FormattingFailure("style", "word/styles.xml", "styles", 0, sid, sid, "", f"style {sid} was removed")
            )
            return
        orig_n = _normalize(orig_el)
        edit_n = _normalize(edit_styles[sid])
        if orig_n != edit_n:
            prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
            report.failures.append(
                FormattingFailure(
                    "style",
                    "word/styles.xml",
                    "styles",
                    0,
                    sid,
                    orig_val,
                    edit_val,
                    f"style {sid} property {prop} differs",
                )
            )
            return
    for sid in edit_styles:
        if sid not in orig_styles:
            report.notes.append(f"style {sid} was added")


def _style_id(el: ET.Element) -> str:
    return el.get(w_attr("styleId"), "")


def _compare_settings(orig_files: dict[str, bytes], edit_files: dict[str, bytes], report: FormattingReport) -> None:
    orig_root = _optional_root(orig_files, "word/settings.xml")
    edit_root = _optional_root(edit_files, "word/settings.xml")
    if orig_root is None or edit_root is None:
        return
    orig_n = _normalize_settings(orig_root)
    edit_n = _normalize_settings(edit_root)
    if orig_n == edit_n:
        return
    prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
    report.failures.append(
        FormattingFailure(
            kind="settings",
            location="word/settings.xml",
            story="settings",
            paragraph=0,
            property=prop,
            original=orig_val,
            edited=edit_val,
            message=f"settings {prop} differs",
        )
    )


def _normalize_settings(root: ET.Element):
    cloned = ET.fromstring(ET.tostring(root, encoding="utf-8"))
    for child in list(cloned):
        if _local(child.tag) in IGNORE_SETTINGS:
            cloned.remove(child)
    return _normalize(cloned)


def _compare_fonts(orig_files: dict[str, bytes], edit_files: dict[str, bytes], report: FormattingReport) -> None:
    orig_root = _optional_root(orig_files, "word/fontTable.xml")
    edit_root = _optional_root(edit_files, "word/fontTable.xml")
    if orig_root is None:
        return
    orig_names = {_font_name(el) for el in orig_root.iter(q("font"))}
    edit_names = {_font_name(el) for el in edit_root.iter(q("font"))} if edit_root is not None else set()
    missing = orig_names - edit_names
    if missing:
        name = sorted(missing)[0]
        report.failures.append(
            FormattingFailure("part", "word/fontTable.xml", "fonts", 0, name, name, "", f"font {name} was removed")
        )


def _font_name(el: ET.Element) -> str:
    return el.get(w_attr("name"), "")


def _compare_equal_part(orig_files: dict[str, bytes], edit_files: dict[str, bytes], name: str, report: FormattingReport) -> None:
    if name not in orig_files or name not in edit_files:
        return
    orig_n = _normalize(parse_xml(orig_files[name]))
    edit_n = _normalize(parse_xml(edit_files[name]))
    if orig_n == edit_n:
        return
    prop, orig_val, edit_val = _first_diff(orig_n, edit_n)
    report.failures.append(
        FormattingFailure("part", name, name, 0, prop, orig_val, edit_val, f"{name} differs")
    )


def _optional_root(files: dict[str, bytes], name: str) -> ET.Element | None:
    data = files.get(name)
    return None if data is None else parse_xml(data)


def _local(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.split("}")[-1]


def _val(el: ET.Element | None) -> str:
    return "" if el is None else (el.get(w_attr("val")) or "")


def _find_change(container: ET.Element | None, tag: str) -> ET.Element | None:
    if container is None:
        return None
    return container.find(tag)


def _explained(container: ET.Element | None, orig_norm, author: str, change_tag: str) -> bool:
    if container is None:
        return False
    change = container.find(change_tag)
    if change is None or change.get(w_attr("author"), "") != author:
        return False
    inner = None
    for child in change:
        inner = child
        break
    if change_tag == q("pPrChange") and inner is not None:
        from copy import deepcopy

        inner = deepcopy(inner)
        for child in container:
            if child.tag in {q("rPr"), q("sectPr")}:
                inner.append(deepcopy(child))
    return _normalize(inner) == orig_norm


def _normalize(el: ET.Element | None):
    if el is None:
        return None
    return _normalize_el(el)


def _normalize_el(el: ET.Element, in_ppr: bool = False, drop_markers: bool = False):
    if not isinstance(el.tag, str):
        return None
    local = _local(el.tag)
    if local in DROP_ELS:
        return None
    if drop_markers and local in PROP_MARKERS:
        return None
    if local in {"bookmarkStart", "bookmarkEnd"} and el.get(w_attr("name")) == "_GoBack":
        return None
    if local in CHANGE_LOCAL:
        return None
    attrs = []
    for key, value in el.attrib.items():
        kl = _local(key)
        if kl.startswith("rsid") or kl in {"paraId", "textId"}:
            continue
        if kl == "id" and local in {"ins", "del"}:
            continue
        if local == "numId" and kl == "val":
            continue
        attrs.append((key, value))
    next_ppr = in_ppr or local == "pPr"
    next_drop = drop_markers or local == "trPr" or (in_ppr and local == "rPr")
    children = []
    for child in el:
        item = _normalize_el(child, in_ppr=next_ppr, drop_markers=next_drop)
        if item is not None:
            children.append(item)
    if local in UNORDERED:
        children.sort()
    val = el.get(w_attr("val"))
    if local in BOOLEAN_TAGS and not children:
        attrs = [(w_attr("val"), "off" if val in OFF_VALUES else "on")]
    if local in UNORDERED and not children and not attrs:
        return None
    return (el.tag, tuple(sorted(attrs)), tuple(children))


def _first_diff(orig, edit) -> tuple[str, str, str]:
    if orig == edit:
        return ("", "", "")
    if orig is None:
        if isinstance(edit, tuple) and edit[2]:
            return (_local(edit[2][0][0]), "", _brief(edit[2][0]))
        return (_local(edit[0]) if isinstance(edit, tuple) else "missing", "", _brief(edit))
    if edit is None:
        if isinstance(orig, tuple) and orig[2]:
            return (_local(orig[2][0][0]), _brief(orig[2][0]), "")
        return (_local(orig[0]) if isinstance(orig, tuple) else "missing", _brief(orig), "")
    if not isinstance(orig, tuple) or not isinstance(edit, tuple):
        return ("value", _brief(orig), _brief(edit))
    otag, oattrs, ochildren = orig
    etag, eattrs, echildren = edit
    if otag != etag:
        return (_local(etag) or _local(otag), _local(otag), _local(etag))
    if oattrs != eattrs:
        return (_local(otag), _brief(oattrs), _brief(eattrs))
    omap = {_local(child[0]): child for child in ochildren if isinstance(child, tuple)}
    emap = {_local(child[0]): child for child in echildren if isinstance(child, tuple)}
    for key in list(omap) + [k for k in emap if k not in omap]:
        if omap.get(key) != emap.get(key):
            if key in omap and key in emap:
                nested = _first_diff(omap[key], emap[key])
                return (nested[0] or key, nested[1], nested[2])
            return (key, _brief(omap.get(key)), _brief(emap.get(key)))
    return (_local(otag), _brief(orig), _brief(edit))


def _brief(value) -> str:
    text = repr(value)
    return text if len(text) < 160 else text[:157] + "..."
