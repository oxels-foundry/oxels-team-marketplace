"""Apply agent edits as Word tracked changes (w:ins / w:del)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree as ET

from redline_guard.ooxml import (
    CharRef,
    DEL_TAGS,
    DocxPackage,
    FORMAT_CHANGE_TAGS,
    INS_TAGS,
    ParagraphView,
    Story,
    _fill_run_with_text,
    clone_run_shell,
    enable_track_revisions,
    final_char_map,
    is_last_paragraph_in_cell,
    load_docx,
    make_tracked_delete,
    make_tracked_insert,
    max_revision_id,
    paragraph_mark_kind,
    paragraph_texts,
    parent_map_from,
    parse_xml,
    persist_story,
    q,
    refuse_overwrite,
    sanitize_copied_properties,
    save_docx,
    set_text_node,
    text_box_snapshots,
    mirror_changed_text_boxes,
    utc_now,
    w_attr,
)
from redline_guard.resolution_log import DEFAULT_AUTHOR, require_author

MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
MC_ALTERNATE = f"{{{MC_NS}}}AlternateContent"

# Run content that has no character in the text map but is still part of what
# the paragraph says: Word strikes it together with a selection that covers it.
# Symbols and the special hyphens are characters of the text map (ooxml
# ``inline_char``) and are struck by the span itself.
ATOM_TAGS = {
    q("footnoteReference"),
    q("endnoteReference"),
    q("drawing"),
    q("pict"),
    q("object"),
    q("ptab"),
    q("dayShort"),
    q("dayLong"),
    q("monthShort"),
    q("monthLong"),
    q("yearShort"),
    q("yearLong"),
    MC_ALTERNATE,
}
HIDDEN_TAGS = {q("vanish"), q("webHidden"), q("specVanish")}


class ApplyError(ValueError):
    """An edit could not be applied as a tracked change."""


@dataclass
class Edit:
    type: str
    paragraph: int = 0
    find: str = ""
    replace: str = ""
    text: str = ""
    after: str = ""
    before: str = ""
    story: str = "body"
    occurrence: int = 1
    numbering: bool | None = None
    style: str = ""
    properties: dict = field(default_factory=dict)
    table: int = 0
    row: int = 0
    cells: list[str] | None = None
    position: str = "after"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edit":
        if not isinstance(data, dict):
            raise ApplyError("Each edit must be a JSON object.")
        edit_type = data.get("type")
        if edit_type not in {"replace", "insert", "delete", "insert_paragraph", "delete_paragraph", "format_run", "format_paragraph", "insert_row", "delete_row"}:
            raise ApplyError(f"Unsupported edit type: {edit_type!r}")
        is_row = edit_type in {"insert_row", "delete_row"}
        if is_row and ("table" not in data or "row" not in data):
            raise ApplyError("Row edits need 1-based table and row indexes from `tables`.")
        if not is_row and "paragraph" not in data:
            raise ApplyError("Each edit needs a 1-based 'paragraph' index from `redline_guard list`.")
        known = {
            "type",
            "paragraph",
            "find",
            "replace",
            "text",
            "after",
            "before",
            "story",
            "occurrence",
            "numbering",
            "style",
            "properties", "table", "row", "cells", "position",
        }
        unknown = set(data) - known
        if unknown:
            name = sorted(unknown)[0]
            raise ApplyError(f"Unsupported field {name!r} in edit spec.")
        for name in ("paragraph", "table", "row", "occurrence"):
            if name not in data:
                continue
            value = data[name]
            if type(value) is not int or value < 1:
                raise ApplyError(f"{name} must be a positive integer.")
        for name in ("find", "replace", "text", "after", "before", "story", "style", "position"):
            if name in data and not isinstance(data[name], str):
                raise ApplyError(f"{name} must be a string.")
        format_edit = edit_type in {"format_run", "format_paragraph"}
        if format_edit and "properties" not in data:
            raise ApplyError("Formatting edits need a properties object.")
        if not format_edit and "properties" in data:
            raise ApplyError("properties is only valid for formatting edits.")
        if is_row and "paragraph" in data:
            raise ApplyError("Row edits use table and row indexes, not paragraph.")
        if not is_row and any(name in data for name in ("table", "row", "cells")):
            raise ApplyError("table, row and cells are only valid for row edits.")
        if "position" in data and not is_row and edit_type != "insert_paragraph":
            raise ApplyError("position is only valid for insert_row and insert_paragraph edits.")
        if edit_type == "insert_paragraph" and data.get("position", "after") not in {"after", "before"}:
            raise ApplyError("insert_paragraph position must be 'before' or 'after'.")
        if edit_type == "delete_row" and any(name in data for name in ("cells", "position")):
            raise ApplyError("delete_row does not accept cells or position.")
        return cls(
            type=edit_type,
            paragraph=int(data.get("paragraph", 0)),
            find=data.get("find", ""),
            replace=data.get("replace", data.get("text", "")),
            text=data.get("text", data.get("replace", "")),
            after=data.get("after", ""),
            before=data.get("before", ""),
            story=data.get("story", "body"),
            occurrence=int(data.get("occurrence", 1)),
            numbering=data.get("numbering"),
            style=str(data.get("style") or ""),
            properties=data.get("properties", {}),
            table=int(data.get("table", 0)), row=int(data.get("row", 0)),
            cells=data.get("cells"), position=data.get("position", "after"),
        )


@dataclass
class IdAllocator:
    next_id: int

    def allocate(self) -> str:
        value = str(self.next_id)
        self.next_id += 1
        return value


def list_paragraphs(path: str | Path, story: str | None = None) -> list[ParagraphView]:
    package = load_docx(path)
    if story:
        return package.story(story).paragraphs
    return package.all_paragraphs()


def format_paragraph_list(paragraphs: list[ParagraphView]) -> str:
    lines = []
    for para in paragraphs:
        preview = " ".join(para.accept_text.split())
        if len(preview) > 100:
            preview = preview[:99] + "…"
        mark = " [has revisions]" if para.revisions else ""
        label = f"  {para.label}" if para.label else ""
        lines.append(f"{para.location}{label}\t{preview}{mark}")
    return "\n".join(lines)


def apply_edits(
    input_path: str | Path,
    output_path: str | Path,
    edits: list[Edit | dict[str, Any]],
    author: str = DEFAULT_AUTHOR,
    date: str | None = None,
) -> DocxPackage:
    require_author(author)
    from redline_guard.resolution_log import copy_resolution_log, warn_if_author_exists

    refuse_overwrite(input_path, output_path, ApplyError)
    warn_if_author_exists(input_path, author)
    package = load_docx(input_path)
    parsed = [edit if isinstance(edit, Edit) else Edit.from_dict(edit) for edit in edits]
    allocator = IdAllocator(max_revision_id(package.files) + 1)
    when = date or utc_now()
    style_ids = _paragraph_style_ids(package.files)

    # Batch edits address the paragraph numbers from `list` at load time.
    # Mid-batch insert/delete must not renumber later targets.
    frozen: dict[tuple[str, int], ParagraphView] = {}
    frozen_rows = {}
    for story in package.stories:
        for ti, table in enumerate(story.root.iter(q("tbl")), 1):
            for ri, row in enumerate(table.findall(q("tr")), 1):
                for name in (story.name, story.part_name):
                    frozen_rows[(name, ti, ri)] = (table, row)
        for para in story.paragraphs:
            frozen[(story.name, para.index)] = para
            frozen[(story.part_name, para.index)] = para
    snapshots = text_box_snapshots(package)

    dirty: set[str] = set()
    inserted_rows = set()
    for edit in parsed:
        if edit.type in {"insert_row", "delete_row"}:
            from redline_guard.tables import apply_row

            target = frozen_rows.get((edit.story, edit.table, edit.row))
            if target is None:
                raise ApplyError("No such table/row in the document as loaded; use `tables` to inspect indexes.")
            edit._inserted_rows = inserted_rows
            try:
                new = apply_row(*target, edit, author, when, allocator)
            except ValueError as exc:
                raise ApplyError(str(exc)) from exc
            if new is not None:
                inserted_rows.add(new)
            dirty.add(package.story(edit.story).part_name)
            continue
        key = (edit.story, edit.paragraph)
        para = frozen.get(key)
        if para is None:
            raise ApplyError(
                f"{edit.story} has no paragraph {edit.paragraph} in the document as loaded. "
                "Batch edits use the paragraph numbers from `redline_guard list` before this apply."
            )
        story = package.story(edit.story)
        _apply_one(story, para, edit, author, when, allocator, style_ids)
        _refresh_paragraph(para)
        dirty.add(story.part_name)

    # A text box is stored twice (mc:Choice and mc:Fallback); only the Choice
    # copy is listed, and an edit to it is mirrored into the Fallback.
    dirty |= mirror_changed_text_boxes(package, snapshots, allocator.allocate)
    enable_track_revisions(package.files)
    dirty |= getattr(package, "_touched_parts", set())  # notes struck with their reference
    for story in package.stories:
        if story.part_name in dirty:
            persist_story(package, story)
    save_docx(package, output_path)
    copy_resolution_log(input_path, output_path)
    return package


def _refresh_paragraph(para: ParagraphView) -> None:
    reject_text, accept_text, revisions = paragraph_texts(para.element)
    para.reject_text = reject_text
    para.accept_text = accept_text
    para.revisions = revisions


def _paragraph_style_ids(files: dict[str, bytes]) -> set[str] | None:
    """Paragraph style ids from word/styles.xml; None when the part is absent."""
    data = files.get("word/styles.xml")
    if not data:
        return None
    try:
        root = parse_xml(data)
    except (ET.ParseError, ValueError):
        return None
    ids: set[str] = set()
    for style in root.iter(q("style")):
        if style.get(w_attr("type"), "paragraph") != "paragraph":
            continue
        style_id = style.get(w_attr("styleId"))
        if style_id:
            ids.add(style_id)
    return ids


def _apply_one(
    story: Story,
    para: ParagraphView,
    edit: Edit,
    author: str,
    date: str,
    allocator: IdAllocator,
    style_ids: set[str] | None = None,
) -> None:
    final_text = para.accept_text
    # Deleting a row keeps its XML until accepted; do not accidentally edit its
    # hidden cell text later in the same batch (or in a subsequent apply).
    parents = parent_map_from(story.root)
    ancestor = parents.get(para.element)
    while ancestor is not None:
        if ancestor.tag == q("tr") and ancestor.find(f"{q('trPr')}/{q('del')}") is not None:
            raise ApplyError("Reject or accept the row deletion before editing its contents.")
        ancestor = parents.get(ancestor)
    if edit.type in {"format_run", "format_paragraph"}:
        from redline_guard.tracked_format import apply_format

        try:
            apply_format(para, edit, author, date, allocator)
        except ValueError as exc:
            raise ApplyError(str(exc)) from exc
        return
    if edit.type == "replace":
        if not edit.find:
            raise ApplyError(f"{para.location}: replace edits need 'find'.")
        start = _nth_index(final_text, edit.find, edit.occurrence, para)
        cut = _delete_range(story, para, start, start + len(edit.find), author, date, allocator)
        if edit.replace:
            if cut.last_del is not None:
                _insert_after_element(story, cut.last_del, edit.replace, author, date, allocator, sample_from=cut.first_del)
            elif cut.own_gap is not None:
                _insert_plain_in_own_insertion(cut.own_gap, edit.replace, cut.own_sample)
            else:
                _insert_at(story, para, start, edit.replace, author, date, allocator)
        _prune_empty_insertions(para.element, author, parent_map_from(story.root))
        return
    if edit.type == "delete":
        target = edit.find or edit.text
        if not target:
            raise ApplyError(f"{para.location}: delete edits need 'find'.")
        start = _nth_index(final_text, target, edit.occurrence, para)
        _delete_range(story, para, start, start + len(target), author, date, allocator)
        _prune_empty_insertions(para.element, author, parent_map_from(story.root))
        return
    if edit.type == "insert":
        text = edit.text or edit.replace
        if not text:
            raise ApplyError(f"{para.location}: insert edits need 'text'.")
        anchors = [name for name in ("after", "before", "find") if getattr(edit, name)]
        if len(anchors) > 1:
            raise ApplyError(f"{para.location}: insert takes one of after, before or find, not {' and '.join(anchors)}.")
        start = _insert_position(final_text, edit, para)
        _insert_at(story, para, start, text, author, date, allocator)
        return
    if edit.type == "insert_paragraph":
        text = edit.text or edit.replace
        _insert_paragraph(
            story, para, text, author, date, allocator,
            numbering=edit.numbering, style=edit.style, before=edit.position == "before", style_ids=style_ids,
        )
        return
    if edit.type == "delete_paragraph":
        if paragraph_mark_kind(para.element) == "del":
            raise ApplyError(
                f"{para.location}: this paragraph is already a tracked deletion; accept or reject that revision instead."
            )
        if _wholly_own_inserted_paragraph(para, author) and _withdraw_paragraph(story, para):
            return
        _assert_no_field(para, None)
        if final_text:
            _delete_range(story, para, 0, len(final_text), author, date, allocator, whole=True)
        else:
            _strike_atom_runs(_atom_runs(para, None), para, author, date, allocator, parent_map_from(story.root))
        _prune_empty_insertions(para.element, author, parent_map_from(story.root))
        parents = parent_map_from(story.root)
        if not is_last_paragraph_in_cell(para.element, parents):
            _set_paragraph_mark_revision(para.element, "del", author, date, allocator)
        return
    raise ApplyError(f"Unsupported edit type: {edit.type}")


def _wholly_counterparty_inserted_paragraph(para: ParagraphView, author: str) -> bool:
    """True when both the paragraph boundary and all text are their insertions."""
    if paragraph_mark_kind(para.element) != "ins":
        return False
    refs = final_char_map(para.element)
    return bool(refs) and all(
        ref.in_ins
        and ref.ins_el is not None
        and ref.ins_el.get(w_attr("author"), "") != author
        for ref in refs
    )


def _wholly_own_inserted_paragraph(para: ParagraphView, author: str) -> bool:
    """True when the paragraph is one we inserted: our mark and only our text."""
    rpr = para.element.find(f"{q('pPr')}/{q('rPr')}")
    if rpr is None:
        return False
    mark = next((child for child in rpr if child.tag in INS_TAGS), None)
    if mark is None or mark.get(w_attr("author"), "") != author:
        return False
    if any(el.tag in INS_TAGS | DEL_TAGS and el.get(w_attr("author"), "") != author for el in para.element.iter()):
        return False
    return all(_own_insertion(ref, author) for ref in final_char_map(para.element))


def _withdraw_paragraph(story: Story, para: ParagraphView) -> bool:
    """Remove a paragraph we inserted ourselves; False when its container needs it."""
    parents = parent_map_from(story.root)
    parent = parents.get(para.element)
    if parent is None:
        return False
    if any(el.tag in {q("commentRangeStart"), q("commentRangeEnd"), q("commentReference"), q("bookmarkStart")} for el in para.element.iter()):
        return False
    if len([child for child in parent if child.tag == q("p")]) < 2:
        return False
    parent.remove(para.element)
    return True


def _nth_index(text: str, needle: str, occurrence: int, para: ParagraphView) -> int:
    if occurrence < 1:
        raise ApplyError(f"{para.location}: occurrence must be >= 1.")
    start = 0
    found = -1
    for _ in range(occurrence):
        found = text.find(needle, start)
        if found < 0:
            raise ApplyError(
                f"{para.location}: could not find {needle!r} (occurrence {occurrence}) in the current text."
            )
        start = found + 1
    return found


def _insert_position(text: str, edit: Edit, para: ParagraphView) -> int:
    if edit.after:
        start = _nth_index(text, edit.after, edit.occurrence, para)
        return start + len(edit.after)
    if edit.before:
        return _nth_index(text, edit.before, edit.occurrence, para)
    if edit.find:
        return _nth_index(text, edit.find, edit.occurrence, para) + len(edit.find)
    return len(text)


def _own_insertion(ref: CharRef, author: str) -> bool:
    return ref.in_ins and ref.ins_el is not None and ref.ins_el.get(w_attr("author"), "") == author


def _assert_not_tracked_reversal(ins_el: ET.Element, para: ParagraphView, author: str, parents: dict[ET.Element, ET.Element]) -> None:
    """Our insertion that restores text they deleted is the visible record of a tracked
    rejection; verify expects it to spell the rejected text, so it is not edited in place."""
    parent = parents.get(ins_el)
    if parent is None:
        return
    siblings = list(parent)
    index = siblings.index(ins_el)
    markers = {q("bookmarkStart"), q("bookmarkEnd"), q("commentRangeStart"), q("commentRangeEnd"), q("proofErr")}
    previous = next((s for s in reversed(siblings[:index]) if s.tag not in markers), None)
    if previous is None or previous.tag not in DEL_TAGS or previous.get(w_attr("author"), "") == author:
        return
    restored = "".join(node.text or "" for node in ins_el.iter(q("t")))
    struck = "".join(node.text or "" for node in previous.iter(q("delText")))
    if restored and restored in struck:
        raise ApplyError(
            f"{para.location}: target text lies in your tracked reversal of del [{previous.get(w_attr('id'), '')}] "
            f"({restored[:40]!r}); reject --id {ins_el.get(w_attr('id'), '')} to withdraw the reversal, or narrow the find string."
        )


def _assert_editable_span(refs: list[CharRef], para: ParagraphView, author: str) -> None:
    marked = [ref for ref in refs if ref.in_del]
    if marked:
        sample = "".join(ref.char for ref in marked[:40])
        raise ApplyError(
            f"{para.location}: target text overlaps existing tracked changes ({sample!r}). "
            "Choose unmarked text, or a more specific find string."
        )


def _assert_no_own_deletion_between(para: ParagraphView, target: list[CharRef], author: str) -> None:
    """A span that passes over text we struck earlier is refused: withdraw that deletion first."""
    order = list(para.element.iter())
    first = order.index(target[0].run)
    last = order.index(target[-1].run)
    for el in order[first:last]:
        if el.tag in DEL_TAGS and el.get(w_attr("author"), "") == author:
            rev_id = el.get(w_attr("id"), "")
            struck = "".join(node.text or "" for node in el.iter(q("delText")))[:40]
            raise ApplyError(
                f"{para.location}: target text spans text you already struck (del [{rev_id}], {struck!r}); "
                f"reject --id {rev_id} to withdraw that deletion first, or narrow the find string."
            )


def _field_runs(para: ParagraphView, parents: dict[ET.Element, ET.Element]) -> dict[ET.Element, str]:
    """Runs that belong to a field (simple or complex), mapped to the field instruction."""
    fields: dict[ET.Element, str] = {}
    depth = 0
    stack: list[list[str]] = []
    for run in para.element.iter(q("r")):
        ancestor = parents.get(run)
        simple = None
        while ancestor is not None and ancestor is not para.element:
            if ancestor.tag == q("fldSimple"):
                simple = ancestor
            ancestor = parents.get(ancestor)
        if simple is not None:
            fields[run] = " ".join((simple.get(w_attr("instr")) or "").split())
            continue
        fld_char = run.find(q("fldChar"))
        kind = fld_char.get(w_attr("fldCharType")) if fld_char is not None else None
        if kind == "begin":
            depth += 1
            stack.append([])
        if depth > 0:
            instr = run.find(q("instrText"))
            if instr is not None and stack:
                stack[-1].append(instr.text or "")
            fields[run] = " ".join("".join(stack[-1]).split()) if stack else ""
        if kind == "end" and depth > 0:
            depth -= 1
            stack.pop()
    return fields


def _assert_no_field(para: ParagraphView, target: list[CharRef] | None) -> None:
    """Refuse a span over a field result: Word regenerates it, so the edit would not survive."""
    parents = parent_map_from(para.element)
    fields = _field_runs(para, parents)
    if not fields:
        return
    if target is None:
        instr = next(iter(fields.values())) or "field"
        raise ApplyError(
            f"{para.location}: the paragraph holds a {instr} field, which Word regenerates; "
            "delete the field in Word, or delete the text around it with 'delete'."
        )
    for ref in target:
        if ref.run in fields:
            instr = fields[ref.run] or "field"
            covered = "".join(r.char for r in target if r.run in fields)[:40]
            raise ApplyError(
                f"{para.location}: target text covers the result of the {instr} field ({covered!r}), which Word regenerates; "
                "narrow the find string to the text around the field, or edit the field in Word."
            )


@dataclass
class _Cut:
    last_del: ET.Element | None = None
    first_del: ET.Element | None = None
    own_gap: tuple[ET.Element, ET.Element | None] | None = None
    own_sample: ET.Element | None = None


def _delete_range(
    story: Story,
    para: ParagraphView,
    start: int,
    end: int,
    author: str,
    date: str,
    allocator: IdAllocator,
    whole: bool = False,
) -> _Cut:
    cut = _Cut()
    if start == end:
        return cut
    parents = parent_map_from(story.root)
    refs = final_char_map(para.element)
    if end > len(refs):
        raise ApplyError(f"{para.location}: delete range is out of bounds.")
    target = refs[start:end]
    _assert_editable_span(target, para, author)
    _assert_no_field(para, None if whole else target)
    _assert_no_own_deletion_between(para, target, author)
    for ref in target:
        if _own_insertion(ref, author):
            _assert_not_tracked_reversal(ref.ins_el, para, author, parents)
    _explode_runs({ref.run for ref in target}, parents, author, allocator)
    parents = parent_map_from(story.root)
    refs = final_char_map(para.element)
    target = refs[start:end]
    # Objects the span covers are struck after the text: their runs are not
    # touched by the splicing below, so collect them now.
    atoms = _atom_runs(para, None if whole else (target[0].run, target[-1].run))

    groups: list[list[CharRef]] = []
    for ref in target:
        if not groups:
            groups.append([ref])
            continue
        prev = groups[-1][-1]
        if ref.text_node is prev.text_node and ref.offset == prev.offset + 1:
            groups[-1].append(ref)
        else:
            groups.append([ref])

    parents = parent_map_from(story.root)
    for group in reversed(groups):
        if _own_insertion(group[0], author):
            # Text we inserted earlier is edited in place: Word never nests a
            # deletion inside the same author's insertion.
            cut.own_gap = _cut_own_insertion(group, author, allocator, parents)
            cut.own_sample = clone_run_shell(group[0].run)
            continue
        created = _splice_node_slice(group, author, date, allocator, parents, kind="del")
        if cut.last_del is None:
            cut.last_del = created
        if created is not None:
            cut.first_del = created
    _strike_atom_runs(atoms, para, author, date, allocator, parent_map_from(story.root))
    return cut


def _cut_own_insertion(
    group: list[CharRef],
    author: str,
    allocator: IdAllocator,
    parents: dict[ET.Element, ET.Element],
) -> tuple[ET.Element, ET.Element | None]:
    """Remove the group's characters from our own insertion; return where they were."""
    first = group[0]
    run = first.run
    node = first.text_node
    parent = parents[run]
    siblings = list(parent)
    idx = siblings.index(run)
    following = siblings[idx + 1] if idx + 1 < len(siblings) else None
    if node.tag not in {q("t"), q("delText")}:
        # A tab, break, special hyphen or symbol is the whole run after
        # _explode_runs: the run goes.
        parent.remove(run)
        return parent, following
    text = node.text or ""
    before = text[: first.offset]
    after = text[group[-1].offset + 1 :]
    change = _format_change_of(run)
    pieces: list[ET.Element] = []
    if before:
        pieces.append(_copy_run_with_text(run, node.tag, before))
    gap_next = None
    if after:
        gap_next = _copy_run_with_text(run, node.tag, after)
        pieces.append(gap_next)
    else:
        gap_next = following
    parent.remove(run)
    for offset, piece in enumerate(pieces):
        parent.insert(idx + offset, piece)
        parents[piece] = parent
    if change is not None and pieces:
        _spread_format_change(pieces, change, author, allocator)
    return parent, gap_next


def _insert_plain_in_own_insertion(gap: tuple[ET.Element, ET.Element | None], text: str, sample: ET.Element | None) -> None:
    """Put replacement text inside our own insertion, as ordinary runs of that insertion."""
    parent, following = gap
    run = clone_run_shell(sample) if sample is not None else ET.Element(q("r"))
    _fill_run_with_text(run, q("t"), text)
    _unhide(run)
    children = list(parent)
    index = children.index(following) if following is not None and following in children else len(children)
    parent.insert(index, run)


def _prune_empty_insertions(paragraph: ET.Element, author: str, parents: dict[ET.Element, ET.Element]) -> None:
    """Drop runs of ours emptied by an in-place edit, and our insertions left with nothing."""
    for ins in list(paragraph.iter()):
        if ins.tag not in INS_TAGS or ins.get(w_attr("author"), "") != author:
            continue
        for run in list(ins):
            if run.tag == q("r") and all(child.tag == q("rPr") for child in run):
                ins.remove(run)
        if len(ins) == 0:
            parent = parents.get(ins)
            if parent is not None:
                parent.remove(ins)


def _atom_runs(para: ParagraphView, bounds: tuple[ET.Element, ET.Element] | None) -> list[ET.Element]:
    """Runs holding footnote references, pictures or other objects without a character.

    They have no character in the text map, so a span's text groups pass over
    them; Word strikes them with the selection. ``bounds`` limits the sweep to
    runs strictly between the first and last run of the span; None sweeps the
    whole paragraph.
    """
    runs = list(para.element.iter(q("r")))
    if bounds is not None:
        first, last = bounds
        candidates = runs[runs.index(first) + 1 : runs.index(last)]
    else:
        candidates = runs
    return [run for run in candidates if any(child.tag in ATOM_TAGS for child in run)]


def _strike_atom_runs(
    runs: list[ET.Element],
    para: ParagraphView,
    author: str,
    date: str,
    allocator: IdAllocator,
    parents: dict[ET.Element, ET.Element],
) -> None:
    """Delete object runs inside our w:del (nested in their insertion when they inserted the object)."""
    for run in runs:
        ancestor = parents.get(run)
        deleted = False
        own_ins: ET.Element | None = None
        while ancestor is not None and ancestor is not para.element:
            if ancestor.tag in DEL_TAGS:
                deleted = True
                break
            if ancestor.tag in INS_TAGS and ancestor.get(w_attr("author"), "") == author:
                own_ins = ancestor
            ancestor = parents.get(ancestor)
        if deleted or ancestor is None:
            continue
        if own_ins is not None:
            parents[run].remove(run)
            continue
        _wrap_run(run, author, date, allocator, parents, "del")
        _strike_note_text(para, run, author, date, allocator)


NOTE_REF_PARTS = {
    q("footnoteReference"): ("word/footnotes.xml", "footnote"),
    q("endnoteReference"): ("word/endnotes.xml", "endnote"),
}


def _strike_note_text(para: ParagraphView, run: ET.Element, author: str, date: str, allocator: IdAllocator) -> None:
    """Word strikes a note's text together with its reference.

    Every run of the referenced footnote or endnote that is not already inside
    a deletion is wrapped in our ``w:del`` with the same date as the reference
    deletion, so a withdrawal (``reject`` of our revision) can find and undo it.
    """
    package = getattr(para, "package", None)
    if package is None:
        return
    for child in list(run):
        spec = NOTE_REF_PARTS.get(child.tag)
        if spec is None:
            continue
        part, note_tag = spec
        nid = child.get(w_attr("id"), "")
        story = next((s for s in package.stories if s.part_name == part), None)
        if story is None:
            continue
        for note in story.root.iter(q(note_tag)):
            if note.get(w_attr("id"), "") != nid:
                continue
            parents = parent_map_from(story.root)
            for r in list(note.iter(q("r"))):
                ancestor = parents.get(r)
                struck = False
                while ancestor is not None and ancestor is not note:
                    if ancestor.tag in DEL_TAGS:
                        struck = True
                        break
                    ancestor = parents.get(ancestor)
                if struck:
                    continue
                for t in r.iter(q("t")):
                    t.tag = q("delText")
                _wrap_run(r, author, date, allocator, parents, "del")
            touched = getattr(package, "_touched_parts", None)
            if touched is None:
                touched = set()
                package._touched_parts = touched
            touched.add(part)


def _explode_runs(
    runs: set[ET.Element],
    parents: dict[ET.Element, ET.Element],
    author: str | None = None,
    allocator: IdAllocator | None = None,
) -> None:
    ignorable = {q("rPr"), q("lastRenderedPageBreak"), q("proofErr")}
    for run in list(runs):
        pieces = [child for child in list(run) if child.tag not in ignorable]
        if len(pieces) <= 1:
            continue
        parent = parents.get(run)
        if parent is None:
            continue
        change = _format_change_of(run)
        idx = list(parent).index(run)
        parent.remove(run)
        clones: list[ET.Element] = []
        for offset, piece in enumerate(pieces):
            clone = clone_run_shell(run)
            clone.append(piece)
            parent.insert(idx + offset, clone)
            parents[clone] = parent
            clones.append(clone)
        if change is not None and clones:
            _spread_format_change(clones, change, author, allocator)


def _splice_node_slice(
    group: list[CharRef],
    author: str,
    date: str,
    allocator: IdAllocator,
    parents: dict[ET.Element, ET.Element],
    kind: Literal["ins", "del"],
) -> ET.Element | None:
    first = group[0]
    node = first.text_node
    if node.tag not in {q("t"), q("delText")}:
        # One-character node (tab, break, special hyphen, symbol): the run is
        # struck whole, as Word does; a span never splits inside it.
        return _wrap_run(first.run, author, date, allocator, parents, kind)

    text = node.text or ""
    local_start = first.offset
    local_end = group[-1].offset + 1
    before = text[:local_start]
    mid = text[local_start:local_end]
    after = text[local_end:]
    if not mid:
        return None

    run = first.run
    parent = parents[run]
    change = _format_change_of(run)
    nodes: list[ET.Element] = []
    if before:
        nodes.append(_copy_run_with_text(run, node.tag, before))
    maker = make_tracked_insert if kind == "ins" else make_tracked_delete
    tracked = maker(mid, author, date, allocator.allocate(), run)
    nodes.append(tracked)
    if after:
        nodes.append(_copy_run_with_text(run, node.tag, after))
    idx = list(parent).index(run)
    parent.remove(run)
    if change is not None:
        # Every fragment of the original text keeps the pending formatting
        # change, including the piece we strike: Word keeps the revision on
        # each piece, and the formatting check compares deleted characters too.
        carriers = [item for item in nodes if item.tag == q("r")]
        if kind == "del":
            carriers.append(next(tracked.iter(q("r"))))
        _spread_format_change(carriers, change, author, allocator)
    for offset, item in enumerate(nodes):
        parent.insert(idx + offset, item)
        parents[item] = parent
    return tracked


def _wrap_run(
    run: ET.Element,
    author: str,
    date: str,
    allocator: IdAllocator,
    parents: dict[ET.Element, ET.Element],
    kind: Literal["ins", "del"],
) -> ET.Element:
    parent = parents[run]
    wrapper = ET.Element(
        q(kind),
        {
            w_attr("id"): allocator.allocate(),
            w_attr("author"): author,
            w_attr("date"): date,
        },
    )
    idx = list(parent).index(run)
    parent.remove(run)
    wrapper.append(run)
    parent.insert(idx, wrapper)
    parents[wrapper] = parent
    parents[run] = wrapper
    return wrapper


def _insert_paragraph(
    story: Story,
    para: ParagraphView,
    text: str,
    author: str,
    date: str,
    allocator: IdAllocator,
    numbering: bool | None = None,
    style: str = "",
    before: bool = False,
    style_ids: set[str] | None = None,
) -> None:
    parents = parent_map_from(story.root)
    parent = parents.get(para.element)
    if parent is None:
        raise ApplyError(f"{para.location}: could not find the paragraph parent.")
    if style and style_ids is not None and style not in style_ids:
        raise ApplyError(
            f"{para.location}: unknown paragraph style {style!r}; word/styles.xml defines no paragraph style with that id."
        )
    new_p = ET.Element(q("p"))
    ppr = para.element.find(q("pPr"))
    cloned = sanitize_copied_properties(ppr) if ppr is not None else None
    if cloned is not None and numbering is False:
        num_pr = cloned.find(q("numPr"))
        if num_pr is not None:
            cloned.remove(num_pr)
    if style:
        if cloned is None:
            cloned = ET.Element(q("pPr"))
        p_style = cloned.find(q("pStyle"))
        if p_style is None:
            p_style = ET.Element(q("pStyle"))
            cloned.insert(0, p_style)
        p_style.set(w_attr("val"), style)
    if cloned is not None:
        new_p.append(cloned)
    _set_paragraph_mark_revision(new_p, "ins", author, date, allocator)
    if text:
        new_p.append(_make_insert(text, author, date, allocator))
    siblings = list(parent)
    if before:
        idx = siblings.index(para.element)
    else:
        idx = siblings.index(para.element) + 1
        while idx < len(siblings) and siblings[idx].tag == q("p") and paragraph_mark_kind(siblings[idx]) == "ins":
            idx += 1
    parent.insert(idx, new_p)


# Kept for callers that import the old name.
_insert_paragraph_after = _insert_paragraph


def _set_paragraph_mark_revision(
    paragraph: ET.Element,
    kind: Literal["ins", "del"],
    author: str,
    date: str,
    allocator: IdAllocator,
) -> None:
    ppr = paragraph.find(q("pPr"))
    if ppr is None:
        ppr = ET.Element(q("pPr"))
        paragraph.insert(0, ppr)
    rpr = ppr.find(q("rPr"))
    if rpr is None:
        # CT_PPr: rPr precedes sectPr and pPrChange.
        rpr = ET.Element(q("rPr"))
        slot = next(
            (index for index, child in enumerate(ppr) if child.tag in {q("sectPr"), q("pPrChange")}),
            len(ppr),
        )
        ppr.insert(slot, rpr)
    for child in rpr:
        if child.tag in INS_TAGS | DEL_TAGS and child.get(w_attr("author"), "") == author:
            if (child.tag in INS_TAGS and kind == "ins") or (child.tag in DEL_TAGS and kind == "del"):
                return
    marker = ET.Element(
        q(kind),
        {
            w_attr("id"): allocator.allocate(),
            w_attr("author"): author,
            w_attr("date"): date,
        },
    )
    marker_order = {
        q("ins"): 0,
        q("del"): 1,
        q("moveFrom"): 2,
        q("moveTo"): 3,
    }
    rank = marker_order[marker.tag]
    insert_at = next(
        (
            index
            for index, child in enumerate(rpr)
            if marker_order.get(child.tag, len(marker_order)) > rank
        ),
        len(rpr),
    )
    rpr.insert(insert_at, marker)


def _make_insert(text: str, author: str, date: str, allocator: IdAllocator, sample: ET.Element | None = None) -> ET.Element:
    """Our tracked insertion of ``text``, never hidden even when the sample run is."""
    ins = make_tracked_insert(text, author, date, allocator.allocate(), sample)
    _unhide(ins)
    return ins


def _unhide(element: ET.Element) -> None:
    """Text we insert must be visible: a hidden sample run must not hide our words."""
    for rpr in element.iter(q("rPr")):
        for child in list(rpr):
            if child.tag in HIDDEN_TAGS:
                rpr.remove(child)


def _insert_after_element(
    story: Story,
    element: ET.Element,
    text: str,
    author: str,
    date: str,
    allocator: IdAllocator,
    sample_from: ET.Element | None = None,
) -> None:
    if not text:
        return
    parents = parent_map_from(story.root)
    parent = parents.get(element)
    if parent is None:
        raise ApplyError("Could not find the parent of a tracked deletion.")
    source = sample_from if sample_from is not None else element
    sample = next((child for child in source.iter(q("r"))), None)
    ins = _make_insert(text, author, date, allocator, sample)
    _insert_beside(parent, list(parent).index(element) + 1, ins, author, allocator, parents)


def _insert_beside(
    parent: ET.Element,
    index: int,
    ins: ET.Element,
    author: str,
    allocator: IdAllocator,
    parents: dict[ET.Element, ET.Element],
) -> None:
    """Place our insertion at ``index`` in ``parent``, the way Word does.

    Word never nests one author's insertion inside another's. When the
    position lies inside the counterparty's ``w:ins``, their insertion is
    split around ours: the pieces keep their author and date (a fresh id on
    the second piece) and still spell out their text, so both Word and other
    validators read their proposal unchanged with our words added beside it.
    Our own deletion of their text stays nested inside their piece.
    """
    if parent.tag in INS_TAGS and parent.get(w_attr("author"), "") != author:
        grand = parents.get(parent)
        if grand is not None:
            position = list(grand).index(parent)
            tail_children = list(parent)[index:]
            if tail_children:
                tail = ET.Element(parent.tag, dict(parent.attrib))
                tail.set(w_attr("id"), allocator.allocate())
                for child in tail_children:
                    parent.remove(child)
                    tail.append(child)
                grand.insert(position + 1, tail)
                parents[tail] = grand
            if len(parent) == 0:
                grand.remove(parent)
                position -= 1
            grand.insert(position + 1, ins)
            parents[ins] = grand
            return
    parent.insert(index, ins)
    parents[ins] = parent


def _copy_run_with_text(sample_run: ET.Element, tag: str, text: str) -> ET.Element:
    run = clone_run_shell(sample_run)
    node = ET.SubElement(run, tag)
    set_text_node(node, text)
    return run


def _insert_at(
    story: Story,
    para: ParagraphView,
    index: int,
    text: str,
    author: str,
    date: str,
    allocator: IdAllocator,
) -> None:
    if not text:
        return
    parents = parent_map_from(story.root)
    refs = final_char_map(para.element)
    if refs:
        target_run = refs[index].run if index < len(refs) else refs[-1].run
        _explode_runs({target_run}, parents, author, allocator)
        parents = parent_map_from(story.root)
        refs = final_char_map(para.element)
    if refs and index < len(refs):
        _assert_editable_span(refs[index : index + 1], para, author)
    sample_run = _sample_run_for_insert(para, refs, index)

    if not refs:
        ins = _make_insert(text, author, date, allocator, sample_run)
        ppr = para.element.find(q("pPr"))
        insert_at = 1 if ppr is not None else 0
        para.element.insert(insert_at, ins)
        return

    if index >= len(refs):
        ins = _make_insert(text, author, date, allocator, sample_run)
        anchor = _end_of_paragraph_anchor(para, refs[-1].run, parents)
        parent = parents[anchor]
        parent.insert(list(parent).index(anchor) + 1, ins)
        return

    ref = refs[index]
    if _own_insertion(ref, author):
        # Typing inside our own insertion extends it: a plain run of that
        # insertion, never a second w:ins nested in the first.
        _assert_not_tracked_reversal(ref.ins_el, para, author, parents)
        run = clone_run_shell(sample_run) if sample_run is not None else ET.Element(q("r"))
        _fill_run_with_text(run, q("t"), text)
        _unhide(run)
        parent = parents[ref.run]
        run_idx = list(parent).index(ref.run)
        if ref.offset == 0:
            parent.insert(run_idx, run)
            return
        _split_text_run(ref, parent, run_idx, author, allocator)
        parent.insert(run_idx + 1, run)
        return

    ins = _make_insert(text, author, date, allocator, sample_run)
    if ref.offset == 0:
        parent = parents[ref.run]
        _insert_beside(parent, list(parent).index(ref.run), ins, author, allocator, parents)
        return

    # Split the run's text node at offset and insert between the pieces.
    parent = parents[ref.run]
    run_idx = list(parent).index(ref.run)
    _split_text_run(ref, parent, run_idx, author, allocator)
    _insert_beside(parent, run_idx + 1, ins, author, allocator, parents)


def _split_text_run(ref: CharRef, parent: ET.Element, run_idx: int, author: str, allocator: IdAllocator) -> None:
    """Split ``ref.run`` at ``ref.offset``; the right piece follows it in ``parent``."""
    node = ref.text_node
    raw = node.text or ""
    left_text, right_text = raw[: ref.offset], raw[ref.offset :]
    set_text_node(node, left_text)
    if right_text:
        right = _copy_run_with_text(ref.run, node.tag, right_text)
        parent.insert(run_idx + 1, right)
        change = _format_change_of(ref.run)
        if change is not None:
            _spread_format_change([ref.run, right], change, author, allocator)


def _end_of_paragraph_anchor(para: ParagraphView, last_run: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element:
    """The element after which end-of-paragraph text goes: past any field the last run belongs to."""
    fields = _field_runs(para, parents)
    run = last_run
    if run in fields:
        runs = list(para.element.iter(q("r")))
        depth = 0
        for candidate in runs[runs.index(run):]:
            fld_char = candidate.find(q("fldChar"))
            kind = fld_char.get(w_attr("fldCharType")) if fld_char is not None else None
            if kind == "begin":
                depth += 1
            elif kind == "end":
                if depth == 0:
                    run = candidate
                    break
                depth -= 1
    anchor = _outer_revision_anchor(run, parents)
    parent = parents.get(anchor)
    while parent is not None and parent.tag == q("fldSimple"):
        anchor = parent
        parent = parents.get(anchor)
    return anchor


def _sample_run_for_insert(para: ParagraphView, refs: list[CharRef], index: int) -> ET.Element | None:
    if refs and index > 0:
        return refs[index - 1].run
    if refs:
        return refs[0].run
    for run in para.element.iter(q("r")):
        if run.find(q("rPr")) is not None:
            return run
    ppr = para.element.find(q("pPr"))
    if ppr is None:
        return None
    rpr = ppr.find(q("rPr"))
    if rpr is None:
        return None
    dummy = ET.Element(q("r"))
    dummy.append(sanitize_copied_properties(rpr))
    return dummy


def _format_change_of(run: ET.Element) -> ET.Element | None:
    rpr = run.find(q("rPr"))
    if rpr is None:
        return None
    return rpr.find(q("rPrChange"))


def _spread_format_change(
    runs: list[ET.Element],
    change: ET.Element,
    author: str | None,
    allocator: IdAllocator | None,
) -> None:
    """Carry a pending rPrChange onto every fragment of a split run.

    Word keeps the change on each piece, whoever made it: the first fragment
    keeps the id, the others get copies (same author, date and old
    properties) under fresh ids so ids stay unique. Without an allocator only
    the first fragment can keep it.
    """
    if not runs:
        return
    _attach_format_change(runs[0], change)
    if allocator is None:
        return
    for run in runs[1:]:
        copy = ET.fromstring(ET.tostring(change, encoding="utf-8"))
        copy.set(w_attr("id"), allocator.allocate())
        _attach_format_change(run, copy)


def _attach_format_change(run: ET.Element, change: ET.Element) -> None:
    rpr = run.find(q("rPr"))
    if rpr is None:
        rpr = ET.Element(q("rPr"))
        run.insert(0, rpr)
    if rpr.find(q("rPrChange")) is None:
        rpr.append(ET.fromstring(ET.tostring(change, encoding="utf-8")))


def _outer_revision_anchor(run: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element:
    """Sibling-level node to insert after so we do not nest inside an existing ins/del."""
    anchor = run
    parent = parents.get(anchor)
    while parent is not None and parent.tag in INS_TAGS | DEL_TAGS:
        anchor = parent
        parent = parents.get(anchor)
    return anchor
