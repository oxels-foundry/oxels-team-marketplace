"""Read and write Word comments on a .docx."""

from __future__ import annotations

import random
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from redline_guard.ooxml import (
    DEL_TAGS,
    INS_TAGS,
    SKIP_TAGS,
    CharRef,
    _fill_run_with_text,
    load_docx,
    max_revision_id,
    parse_xml,
    parent_map_from,
    persist_story,
    q,
    refuse_overwrite,
    save_docx,
    inline_char,
    iter_outside_fallback,
    mirror_changed_text_boxes,
    set_text_node,
    text_box_snapshots,
    utc_now,
    w_attr,
    write_tree,
)
from redline_guard.resolution_log import DEFAULT_AUTHOR, require_author

REVISION_WRAPPERS = INS_TAGS | DEL_TAGS
ANCHOR_MARKERS = ("commentRangeStart", "commentRangeEnd", "commentReference")

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
W16CID = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
W16CEX = "http://schemas.microsoft.com/office/word/2018/wordml/cex"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENT_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

INTERNAL_AUTHOR_MARK = "[INTERNAL — do not send]"
INTERNAL_BANNER = "[INTERNAL — do not send to counterparty or include in the signature copy]"


@dataclass
class Comment:
    id: str
    author: str
    date: str
    text: str
    location: str | None = None
    story: str | None = None
    paragraph: int | None = None
    parent_id: str | None = None
    internal: bool = False
    resolved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def list_comments(path: str) -> list[Comment]:
    package = load_docx(path)
    data = package.files.get("word/comments.xml")
    if not data:
        return []

    anchors = _comment_anchors(package)
    parent_by_para, para_by_comment = _comment_thread_maps(package, data)
    comments: list[Comment] = []
    root = parse_xml(data)
    by_id: dict[str, Comment] = {}
    done = _done_by_para(package)
    for el in root.iter(q("comment")):
        cid = el.get(w_attr("id"), "")
        loc = anchors.get(cid)
        para_id = _comment_para_id(el)
        parent_para = parent_by_para.get(para_id or "")
        parent_id = para_by_comment.get(parent_para or "") if parent_para else None
        author = el.get(w_attr("author"), "")
        body = comment_text(el).strip()
        comments.append(
            Comment(
                id=cid,
                author=author,
                date=el.get(w_attr("date"), ""),
                text=body,
                location=None if loc is None else loc.location,
                story=None if loc is None else loc.story,
                paragraph=None if loc is None else loc.index,
                parent_id=parent_id,
                internal=is_internal_comment(author, body),
                resolved=done.get(para_id, False),
            )
        )
        by_id[cid] = comments[-1]
    for comment in comments:
        if comment.parent_id and comment.location is None:
            parent = by_id.get(comment.parent_id)
            if parent is not None:
                comment.location = parent.location
                comment.story = parent.story
                comment.paragraph = parent.paragraph
        # Replies share their root thread's state, even if Word only sets done
        # on the root commentEx record.
        ancestor = comment
        visited = set()
        while ancestor.parent_id in by_id and ancestor.id not in visited:
            visited.add(ancestor.id)
            ancestor = by_id[ancestor.parent_id]
        comment.resolved = ancestor.resolved
    return comments


def format_comments(comments: list[Comment]) -> str:
    if not comments:
        return "No comments."
    lines = []
    for comment in comments:
        where = comment.location or "unanchored"
        reply = f"  reply to [{comment.parent_id}]" if comment.parent_id else ""
        flag = ("  INTERNAL" if comment.internal else "") + ("  RESOLVED" if comment.resolved else "")
        lines.append(f"[{comment.id}] {comment.author}  {where}{reply}{flag}")
        if comment.date:
            lines.append(f"    {comment.date}")
        lines.append(f"    {comment.text}")
    return "\n".join(lines)


def comment_text(comment_el: ET.Element) -> str:
    """A comment body as it reads: line breaks and tabs kept, paragraphs joined by newlines."""
    paragraphs: list[str] = []
    for p in comment_el.iter(q("p")):
        pieces: list[str] = []
        for node in p.iter():
            if node.tag == q("t"):
                pieces.append(node.text or "")
            elif node.tag in {q("br"), q("cr")}:
                pieces.append("\n")
            elif node.tag == q("tab"):
                pieces.append("\t")
        paragraphs.append("".join(pieces))
    return "\n".join(paragraphs)


def _comment_anchors(package) -> dict[str, object]:
    """The listed paragraph each comment is anchored in.

    A marker inside a text box belongs to the box's own paragraph, not to the
    host paragraph the drawing sits in, so the walk stops at nested paragraphs.
    """
    mapping: dict[str, object] = {}
    for para in package.all_paragraphs():
        for el in _own_markers(para.element):
            cid = el.get(w_attr("id"))
            if cid and cid not in mapping:
                mapping[cid] = para
    return mapping


def _own_markers(paragraph: ET.Element):
    """Comment range starts and references of this paragraph, nested paragraphs excluded."""
    for child in paragraph:
        if child.tag == q("p"):
            continue
        if child.tag in {q("commentRangeStart"), q("commentReference")}:
            yield child
        else:
            yield from _own_markers(child)


def is_internal_comment(author: str, text: str) -> bool:
    blob = f"{author}\n{text}"
    return "[INTERNAL" in blob


def mark_internal_comment(author: str, text: str) -> tuple[str, str]:
    who = author if INTERNAL_AUTHOR_MARK in author else f"{author} {INTERNAL_AUTHOR_MARK}"
    body = text if text.startswith(INTERNAL_BANNER) else f"{INTERNAL_BANNER}\n{text}"
    return who, body


class CommentError(ValueError):
    """A comment could not be added."""


def add_comments(
    input_path: str | Path,
    output_path: str | Path,
    comments: list[dict[str, Any]],
    author: str = DEFAULT_AUTHOR,
    date: str | None = None,
    internal: bool = False,
) -> list[str]:
    """Add Word comments anchored to paragraphs. Returns the new comment ids."""
    require_author(author)
    if not comments:
        raise CommentError("No comments to add.")
    for spec in comments:
        if not isinstance(spec, dict):
            raise CommentError("Each comment must be a JSON object.")
        unknown = set(spec) - {"paragraph", "text", "comment", "find", "after", "story", "author", "reply_to", "parent", "internal", "occurrence"}
        if unknown:
            raise CommentError(f"Unsupported comment fields: {', '.join(sorted(unknown))}.")
        for name in ("paragraph", "occurrence"):
            if name in spec and (type(spec[name]) is not int or spec[name] < 1):
                raise CommentError(f"{name} must be a positive integer.")
        for name in ("text", "comment", "find", "after", "story", "author"):
            if name in spec and not isinstance(spec[name], str):
                raise CommentError(f"{name} must be a string.")
        if "internal" in spec and spec["internal"] is not None and type(spec["internal"]) is not bool:
            raise CommentError("internal must be true or false.")
    refuse_overwrite(input_path, output_path, CommentError)
    from redline_guard.resolution_log import copy_resolution_log, warn_if_author_exists

    warned: set[str] = set()
    for who in [author, *(str(spec.get("author") or "") for spec in comments)]:
        key = who.lower()
        if not who or key in warned:
            continue
        warned.add(key)
        warn_if_author_exists(input_path, who)
    from redline_guard.apply import IdAllocator

    package = load_docx(input_path)
    when = date or utc_now()
    # Comment ids share the revision id space; splitting a run that carries
    # our own formatting change also needs fresh ids.
    allocator = IdAllocator(max_revision_id(package.files) + 1)
    _ensure_comments_part(package)
    added: list[str] = []
    dirty: set[str] = set()
    snapshots = text_box_snapshots(package)

    for spec in comments:
        text = (spec.get("text") or spec.get("comment") or "").strip()
        if not text:
            raise CommentError("Each comment needs 'text'.")
        reply_to = str(spec.get("reply_to") or spec.get("parent") or "")
        parent_para_id = None
        if reply_to:
            clashing = [name for name in ("paragraph", "find", "after", "story", "occurrence") if name in spec]
            if clashing:
                raise CommentError(
                    f"reply_to cannot be combined with {', '.join(clashing)}; a reply shares the anchor of the comment it answers."
                )
            parent_para_id = _ensure_comment_para_id(package, reply_to)
            if not parent_para_id:
                raise CommentError(f"No comment with id {reply_to} to reply to.")
        elif "paragraph" not in spec:
            raise CommentError("Each comment needs a 1-based 'paragraph' index, or reply_to an existing comment.")
        cid = allocator.allocate()
        who = spec.get("author") or author
        flagged = spec.get("internal")
        if flagged is None:
            flagged = internal
        if flagged:
            who, text = mark_internal_comment(who, text)
        if not reply_to:
            story = package.story(spec.get("story", "body"))
            index = int(spec["paragraph"])
            if index < 1 or index > len(story.paragraphs):
                raise CommentError(f"{story.name} has {len(story.paragraphs)} paragraphs; there is no paragraph {index}.")
            para = story.paragraphs[index - 1]
            find = spec.get("find") or spec.get("after") or ""
            _anchor_comment(para.element, cid, find, spec.get("occurrence", 1), author, allocator, location=para.location)
            dirty.add(story.part_name)
        _append_comment_body(package, cid, who, when, text, parent_para_id=parent_para_id)
        if reply_to:
            dirty.update(_anchor_reply(package, reply_to, cid))
        added.append(cid)

    # A comment placed in a text box is mirrored into the mc:Fallback copy,
    # markers and reference run under the same id, as Word writes it.
    dirty |= mirror_changed_text_boxes(package, snapshots, allocator.allocate)
    for story in package.stories:
        if story.part_name in dirty:
            persist_story(package, story)
    save_docx(package, output_path)
    copy_resolution_log(input_path, output_path)
    return added


def _anchor_reply(package, parent_cid: str, cid: str) -> set[str]:
    """Give a reply the document range of its thread, the way Word writes it.

    Word anchors a reply on the same text as the comment it answers: the reply's
    range start follows the parent's range start, and its range end and reference
    run follow the parent's reference run.  A comment with no reference run in the
    document is not shown at all, so a reply without this is invisible in Word.
    Returns the story part names that changed.
    """
    source = _reply_anchor_source(package, parent_cid)
    if source is None:
        raise CommentError(f"Comment {parent_cid} has no anchor in the document to attach a reply to.")
    changed: set[str] = set()
    for story in package.stories:
        root = story.root
        start = end = ref_run = None
        parents = parent_map_from(root)
        # The listed copy of a text box comes first; its mc:Fallback mirror
        # carries the same markers and is rewritten from the Choice afterwards.
        for el in iter_outside_fallback(root):
            if el.tag == q("commentRangeStart") and el.get(w_attr("id")) == source and start is None:
                start = el
            elif el.tag == q("commentRangeEnd") and el.get(w_attr("id")) == source and end is None:
                end = el
            elif el.tag == q("commentReference") and el.get(w_attr("id")) == source and ref_run is None:
                ref_run = parents.get(el)
        if start is None or end is None:
            continue
        # Earlier replies to the same comment sit right after its markers; a new
        # reply goes after them so siblings read in the order they were written.
        start_parent = parents[start]
        siblings = list(start_parent)
        idx = siblings.index(start)
        while idx + 1 < len(siblings) and siblings[idx + 1].tag == q("commentRangeStart"):
            idx += 1
        start_parent.insert(idx + 1, ET.Element(q("commentRangeStart"), {w_attr("id"): cid}))
        after = ref_run if ref_run is not None and ref_run in parents else end
        after_parent = parents[after]
        siblings = list(after_parent)
        idx = siblings.index(after)
        while (
            idx + 2 < len(siblings)
            and siblings[idx + 1].tag == q("commentRangeEnd")
            and siblings[idx + 2].find(q("commentReference")) is not None
        ):
            idx += 2
        after_parent.insert(idx + 1, ET.Element(q("commentRangeEnd"), {w_attr("id"): cid}))
        after_parent.insert(idx + 2, _comment_reference_run(cid))
        changed.add(story.part_name)
    return changed


def _reply_anchor_source(package, parent_cid: str) -> str | None:
    """The comment whose range a reply shares: the parent, or the nearest ancestor with one."""
    comments_xml = package.files.get("word/comments.xml")
    if not comments_xml:
        return None
    parent_by_para, para_by_comment = _comment_thread_maps(package, comments_xml)
    para_by_cid = {cid: para for para, cid in para_by_comment.items()}
    cid = str(parent_cid)
    seen: set[str] = set()
    while cid and cid not in seen:
        seen.add(cid)
        if _has_range_start(package, cid):
            return cid
        parent_para = parent_by_para.get(para_by_cid.get(cid, ""))
        cid = para_by_comment.get(parent_para, "") if parent_para else ""
    return None


def _has_range_start(package, cid: str) -> bool:
    return any(
        el.tag == q("commentRangeStart") and el.get(w_attr("id")) == cid
        for story in package.stories
        for el in story.root.iter()
    )


def _anchor_comment(
    paragraph: ET.Element,
    cid: str,
    find: str,
    occurrence: int = 1,
    author: str | None = None,
    allocator=None,
    location: str = "paragraph",
) -> None:
    """Place the range markers and the reference run for one comment.

    With ``find`` the range wraps exactly the words named, as the paragraph reads
    with markup shown: a span inside a deletion, theirs or our tracked
    rejection, gets its markers inside that ``w:del``.  The reference run is
    never nested in a revision wrapper: it follows the outermost ``w:ins``
    or ``w:del`` that holds the end of the range, so the comment survives when
    the counterparty accepts or rejects that revision.
    """
    start = ET.Element(q("commentRangeStart"), {w_attr("id"): cid})
    end = ET.Element(q("commentRangeEnd"), {w_attr("id"): cid})
    ref = _comment_reference_run(cid)

    ppr = paragraph.find(q("pPr"))
    insert_at = 1 if ppr is not None else 0
    if find:
        span_start, span_end, skip_deleted = _find_comment_span(paragraph, find, occurrence, location)
        try:
            runs = _isolate_comment_span(paragraph, span_start, span_end, skip_deleted, author, allocator)
        except ValueError as exc:
            raise CommentError(str(exc)) from exc
        parents = parent_map_from(paragraph)
        first_run, last_run = runs[0], runs[-1]
        first_parent, last_parent = parents[first_run], parents[last_run]
        first_parent.insert(list(first_parent).index(first_run), start)
        last_parent.insert(list(last_parent).index(last_run) + 1, end)
        _insert_reference_after(end, parent_map_from(paragraph), ref)
        return

    paragraph.insert(insert_at, start)
    paragraph.append(end)
    paragraph.append(ref)


def _insert_reference_after(marker: ET.Element, parents: dict[ET.Element, ET.Element], ref: ET.Element) -> None:
    """Insert the reference run after ``marker``, outside any revision wrapper around it."""
    anchor = marker
    while parents.get(anchor) is not None and parents[anchor].tag in REVISION_WRAPPERS:
        anchor = parents[anchor]
    holder = parents[anchor]
    holder.insert(list(holder).index(anchor) + 1, ref)


def _shown_char_map(paragraph: ET.Element) -> list[CharRef]:
    """Every character of the paragraph as Word shows it with All Markup: deleted text included."""
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
                deleted = in_del is not None
                for node in child:
                    if node.tag in {q("t"), q("delText")}:
                        for i, ch in enumerate(node.text or ""):
                            refs.append(CharRef(ch, node, i, child, in_ins is not None, deleted, in_ins, in_del))
                        continue
                    # Tab, break, special hyphen or symbol: one character, one node.
                    ch = inline_char(node)
                    if ch is not None:
                        refs.append(CharRef(ch, node, 0, child, in_ins is not None, deleted, in_ins, in_del))
                continue
            walk(child, in_ins, in_del)

    walk(paragraph, None, None)
    return refs


def _find_comment_span(paragraph: ET.Element, find: str, occurrence: int, location: str) -> tuple[int, int, bool]:
    """Locate ``find`` in the paragraph as shown with markup.

    Matches are collected in document order from two readings: the text as
    shown (accepted and deleted words in place), and the text as it reads with
    changes accepted, so a find copied from ``list`` that reads across a
    deletion still matches.  Returns (start, end) in the shown character map
    and whether the deleted characters inside the range are skipped.
    """
    if type(occurrence) is not int or occurrence < 1:
        raise CommentError("occurrence must be a positive integer.")
    shown = _shown_char_map(paragraph)
    index_of = {id(ref): i for i, ref in enumerate(shown)}
    matches: list[tuple[int, int, int, bool]] = []
    text = "".join(ref.char for ref in shown)
    pos = text.find(find)
    while pos >= 0:
        matches.append((pos, 1, pos + len(find), False))
        pos = text.find(find, pos + 1)
    live = [ref for ref in shown if not ref.in_del]
    live_text = "".join(ref.char for ref in live)
    pos = live_text.find(find)
    while pos >= 0:
        first, last = index_of[id(live[pos])], index_of[id(live[pos + len(find) - 1])]
        if last - first + 1 != len(find):
            matches.append((first, 0, last + 1, True))
        pos = live_text.find(find, pos + 1)
    matches.sort(key=lambda m: (m[0], m[1]))
    if occurrence > len(matches):
        which = f" (occurrence {occurrence})" if occurrence > 1 or matches else ""
        raise CommentError(
            f"{location}: could not find {find!r}{which} to anchor the comment "
            "(copy it from list, or from revisions for deleted words)."
        )
    start, _priority, end, skip_deleted = matches[occurrence - 1]
    return start, end, skip_deleted


def _isolate_comment_span(paragraph: ET.Element, start: int, end: int, skip_deleted: bool, author, allocator) -> list[ET.Element]:
    """Split runs at both ends of the span and return the runs it covers, in document order."""
    _split_shown_at(paragraph, end, author, allocator)
    _split_shown_at(paragraph, start, author, allocator)
    shown = _shown_char_map(paragraph)
    selected = [ref for ref in shown[start:end] if not (skip_deleted and ref.in_del)]
    return list(dict.fromkeys(ref.run for ref in selected))


def _split_shown_at(paragraph: ET.Element, index: int, author, allocator) -> None:
    refs = _shown_char_map(paragraph)
    if index <= 0 or index >= len(refs) or refs[index - 1].run is not refs[index].run:
        return
    if not refs[index].in_del:
        # Live text: the same split apply uses, so one policy governs a run that
        # carries a pending formatting revision.
        from redline_guard.spans import _split_at

        _split_at(paragraph, sum(1 for ref in refs[:index] if not ref.in_del), author, allocator)
        return
    ref = refs[index]
    run = ref.run
    left, right = ET.Element(run.tag, run.attrib), ET.Element(run.tag, run.attrib)
    pr = run.find(q("rPr"))
    if pr is not None:
        left.append(deepcopy(pr))
        right.append(deepcopy(pr))
        change = right.find(f"{q('rPr')}/{q('rPrChange')}")
        if change is not None and allocator is not None:
            # Word keeps the formatting revision on both pieces; ids stay unique.
            change.set(w_attr("id"), allocator.allocate())
    passed = False
    for child in run:
        if child.tag == q("rPr"):
            continue
        if child is ref.text_node:
            passed = True
            if child.tag in {q("t"), q("delText")}:
                for dest, text in ((left, (child.text or "")[: ref.offset]), (right, (child.text or "")[ref.offset :])):
                    if text:
                        node = deepcopy(child)
                        set_text_node(node, text)
                        dest.append(node)
                continue
        (right if passed else left).append(deepcopy(child))
    parent = parent_map_from(paragraph)[run]
    pos = list(parent).index(run)
    parent.remove(run)
    parent.insert(pos, left)
    parent.insert(pos + 1, right)


def _append_comment_body(
    package,
    cid: str,
    author: str,
    date: str,
    text: str,
    parent_para_id: str | None = None,
) -> None:
    used = {value for part, data in package.files.items() if part.startswith("word/comments") and part.endswith(".xml") for node in parse_xml(data).iter() for key, value in node.attrib.items() if key.rsplit("}", 1)[-1] in {"paraId", "durableId"}}
    para_id = _new_word_para_id()
    while para_id in used:
        para_id = _new_word_para_id()
    durable = _new_word_para_id()
    while durable in used or durable == para_id:
        durable = _new_word_para_id()
    initials = "".join(word[:1] for word in author.split())[:2].upper() or "AG"

    comments = parse_xml(package.files["word/comments.xml"])
    comment = ET.SubElement(
        comments,
        q("comment"),
        {
            w_attr("id"): cid,
            w_attr("author"): author,
            w_attr("date"): date,
            w_attr("initials"): initials,
        },
    )
    p = ET.SubElement(
        comment,
        q("p"),
        {
            f"{{{W14}}}paraId": para_id,
            f"{{{W14}}}textId": "77777777",
        },
    )
    mark = ET.SubElement(p, q("r"))
    mark_rpr = ET.SubElement(mark, q("rPr"))
    ET.SubElement(mark_rpr, q("rStyle"), {w_attr("val"): "CommentReference"})
    ET.SubElement(mark, q("annotationRef"))
    run = ET.SubElement(p, q("r"))
    # A newline is a line break and a tab a tab, as apply writes them.
    _fill_run_with_text(run, q("t"), text)
    package.files["word/comments.xml"] = write_tree(comments, package.files["word/comments.xml"])

    ex_attrs = {f"{{{W15}}}paraId": para_id, f"{{{W15}}}done": "0"}
    if parent_para_id:
        ex_attrs[f"{{{W15}}}paraIdParent"] = parent_para_id
    _append_satellite(
        package,
        "word/commentsExtended.xml",
        f"{{{W15}}}commentEx",
        ex_attrs,
    )
    _append_satellite(
        package,
        "word/commentsIds.xml",
        f"{{{W16CID}}}commentId",
        {f"{{{W16CID}}}paraId": para_id, f"{{{W16CID}}}durableId": durable},
    )
    _append_satellite(
        package,
        "word/commentsExtensible.xml",
        f"{{{W16CEX}}}commentExtensible",
        {f"{{{W16CEX}}}durableId": durable, f"{{{W16CEX}}}dateUtc": date},
    )


def _new_word_para_id() -> str:
    # ECMA-376 w14:paraId is a 32-bit hex value at most 0x7FFFFFFF.
    return f"{random.randint(1, 0x7FFFFFFF):08X}"


def _comment_para_id(comment_el: ET.Element) -> str | None:
    paragraphs = list(comment_el.iter(q("p")))
    if not paragraphs:
        return None
    return paragraphs[-1].get(f"{{{W14}}}paraId")


def _ensure_comment_para_id(package, comment_id):
    """Upgrade a legacy comment only when a reply/status needs its paragraph ID."""
    data = package.files.get("word/comments.xml")
    if data is None:
        return None
    root = parse_xml(data)
    for comment in root.iter(q("comment")):
        if comment.get(w_attr("id")) != str(comment_id):
            continue
        paragraphs = list(comment.iter(q("p")))
        if not paragraphs:
            raise CommentError("The comment has no paragraph to attach thread metadata to.")
        pid = _comment_para_id(comment)
        if not pid:
            used = {n.get(f"{{{W14}}}paraId") for n in root.iter()}
            pid = _new_word_para_id()
            while pid in used:
                pid = _new_word_para_id()
            paragraphs[-1].set(f"{{{W14}}}paraId", pid)
            package.files["word/comments.xml"] = write_tree(root, data)
        return pid
    return None


def _done_by_para(package):
    data = package.files.get("word/commentsExtended.xml")
    if not data:
        return {}
    return {n.get(f"{{{W15}}}paraId"): n.get(f"{{{W15}}}done", "0") in {"1", "true", "on"} for n in parse_xml(data)}


def _set_comment_status(package, cid, resolved):
    pid = _ensure_comment_para_id(package, cid)
    if pid is None:
        raise CommentError(f"No comment with id {cid}.")
    part = "word/commentsExtended.xml"
    data = package.files.get(part)
    root = parse_xml(data) if data else _satellite_root(part)
    by_pid = {n.get(f"{{{W15}}}paraId"): n for n in root}
    # Resolve the thread root even when the caller selects a reply.
    seen = set()
    while pid in by_pid and by_pid[pid].get(f"{{{W15}}}paraIdParent"):
        if pid in seen:
            raise CommentError("The comment thread has a parent cycle.")
        seen.add(pid)
        pid = by_pid[pid].get(f"{{{W15}}}paraIdParent")
    comment_root = parse_xml(package.files["word/comments.xml"])
    ids = {_comment_para_id(n): n.get(w_attr("id")) for n in comment_root.iter(q("comment"))}
    if pid not in ids:
        raise CommentError("The comment thread points to a missing parent.")
    if pid not in by_pid:
        by_pid[pid] = ET.SubElement(root, f"{{{W15}}}commentEx", {f"{{{W15}}}paraId": pid})
    before = by_pid[pid].get(f"{{{W15}}}done", "0") in {"1", "true", "on"}
    affected = {pid}
    while True:
        more = {p for p, n in by_pid.items() if n.get(f"{{{W15}}}paraIdParent") in affected}
        if more <= affected:
            break
        affected |= more
    for p in affected:
        by_pid[p].set(f"{{{W15}}}done", "1" if resolved else "0")
    package.files[part] = write_tree(root, data)
    _ensure_part_binding(package, part)
    return ids[pid], before


def set_comment_status(input_path, output_path, comment_id, resolved=True, author=DEFAULT_AUTHOR, date=None):
    """Resolve/reopen a whole thread; retain text, author, date, replies and anchors."""
    require_author(author)
    if type(resolved) is not bool:
        raise CommentError("resolved must be a boolean.")
    refuse_overwrite(input_path, output_path, CommentError)
    package = load_docx(input_path)
    root_id, before = _set_comment_status(package, str(comment_id), resolved)
    save_docx(package, output_path)
    from redline_guard.resolution_log import write_resolve_log

    write_resolve_log(input_path, output_path, [{"id": root_id, "kind": "comment_status", "action": "resolve" if resolved else "reopen", "before": before, "after": resolved, "author": author, "date": date or utc_now()}])
    return root_id


def _existing_comment_para_id(package, comment_id: str) -> str | None:
    data = package.files.get("word/comments.xml")
    if not data:
        return None
    root = parse_xml(data)
    for el in root.iter(q("comment")):
        if el.get(w_attr("id")) == comment_id:
            return _comment_para_id(el)
    return None


def _comment_thread_maps(package, comments_xml: bytes) -> tuple[dict[str, str], dict[str, str]]:
    """Return paraId -> parent paraId, and comment-paraId -> comment id."""
    parent_by_para: dict[str, str] = {}
    para_by_comment: dict[str, str] = {}
    root = parse_xml(comments_xml)
    for el in root.iter(q("comment")):
        para_id = _comment_para_id(el)
        if para_id:
            para_by_comment[para_id] = el.get(w_attr("id"), "")
    ext = package.files.get("word/commentsExtended.xml")
    if ext:
        ex_root = parse_xml(ext)
        for el in ex_root:
            para_id = el.get(f"{{{W15}}}paraId")
            parent = el.get(f"{{{W15}}}paraIdParent")
            if para_id and parent:
                parent_by_para[para_id] = parent
    return parent_by_para, para_by_comment


def _append_satellite(package, part: str, tag: str, attrs: dict[str, str]) -> None:
    data = package.files.get(part)
    if not data:
        root = _satellite_root(part)
        data = write_tree(root)
        package.files[part] = data
    root = parse_xml(data)
    ET.SubElement(root, tag, attrs)
    package.files[part] = write_tree(root, data)
    _ensure_part_binding(package, part)


def _satellite_root(part: str) -> ET.Element:
    if part.endswith("commentsExtended.xml"):
        root = ET.Element(f"{{{W15}}}commentsEx")
        root.set(f"{{{MC}}}Ignorable", "w15")
        return root
    if part.endswith("commentsIds.xml"):
        root = ET.Element(f"{{{W16CID}}}commentsIds")
        root.set(f"{{{MC}}}Ignorable", "w16cid")
        return root
    if part.endswith("commentsExtensible.xml"):
        root = ET.Element(f"{{{W16CEX}}}commentsExtensible")
        root.set(f"{{{MC}}}Ignorable", "w16cex")
        return root
    raise ValueError(f"Unknown comments satellite part: {part}")


def _ensure_comments_part(package) -> None:
    if "word/comments.xml" in package.files:
        # A comments part written by another tool (pandoc, for one) may not list w14 as
        # ignorable; the comment paragraphs we add carry w14:paraId, so declare it.
        data = package.files["word/comments.xml"]
        root = parse_xml(data)
        listed = root.get(f"{{{MC}}}Ignorable", "").split()
        if "w14" not in listed:
            root.set(f"{{{MC}}}Ignorable", " ".join([*listed, "w14"]))
            package.files["word/comments.xml"] = write_tree(root, data)
        return
    comments = ET.Element(q("comments"))
    comments.set(f"{{{MC}}}Ignorable", "w14")
    package.files["word/comments.xml"] = write_tree(comments)
    _ensure_part_binding(package, "word/comments.xml")


def _ensure_part_binding(package, part):
    suffix = Path(part).stem
    rel_types = {"comments": COMMENT_REL, "commentsExtended": "http://schemas.microsoft.com/office/2011/relationships/commentsExtended", "commentsIds": "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds", "commentsExtensible": "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible"}
    ct_name = "[Content_Types].xml"
    data = package.files[ct_name]
    root = parse_xml(data)
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    content_type = f"application/vnd.openxmlformats-officedocument.wordprocessingml.{suffix}+xml"
    if not any(n.get("PartName") == "/" + part for n in root):
        ET.SubElement(root, f"{{{ct_ns}}}Override", {"PartName": "/" + part, "ContentType": content_type})
        ET.register_namespace("", ct_ns)
        package.files[ct_name] = write_tree(root, data)
    rel_name = "word/_rels/document.xml.rels"
    data = package.files.get(rel_name)
    root = parse_xml(data) if data else ET.Element(f"{{{REL_NS}}}Relationships")
    if not any(n.get("Type") == rel_types[suffix] and n.get("Target") in {Path(part).name, "/" + part} for n in root):
        used = {n.get("Id") for n in root}
        rid = 1
        while f"rId{rid}" in used:
            rid += 1
        ET.SubElement(root, f"{{{REL_NS}}}Relationship", {"Id": f"rId{rid}", "Type": rel_types[suffix], "Target": Path(part).name})
        ET.register_namespace("", REL_NS)
        package.files[rel_name] = write_tree(root, data)


def _ensure_content_type(package) -> None:
    name = "[Content_Types].xml"
    text = package.files[name].decode("utf-8")
    if 'PartName="/word/comments.xml"' in text:
        return
    text = text.replace(
        "</Types>",
        f'<Override PartName="/word/comments.xml" ContentType="{COMMENT_CT}"/></Types>',
    )
    package.files[name] = text.encode("utf-8")


def _ensure_comment_rel(package) -> None:
    name = "word/_rels/document.xml.rels"
    text = package.files[name].decode("utf-8")
    if 'Target="comments.xml"' in text:
        return
    used = {int(m) for m in re.findall(r'Id="rId(\d+)"', text)}
    rid = 1
    while rid in used:
        rid += 1
    rel = f'<Relationship Id="rId{rid}" Type="{COMMENT_REL}" Target="comments.xml"/>'
    text = text.replace("</Relationships>", f"{rel}</Relationships>")
    package.files[name] = text.encode("utf-8")


def internal_comment_ids(path: str | Path) -> set[str]:
    return {c.id for c in list_comments(str(path)) if c.internal}


def scrub_internal_notes(input_path: str | Path, output_path: str | Path) -> int:
    """Remove internal agent notes. Keep redlines and customer-facing comments."""
    refuse_overwrite(input_path, output_path, CommentError)
    package = load_docx(input_path)
    ids = {
        el.get(w_attr("id"), "")
        for el in parse_xml(package.files["word/comments.xml"]).iter(q("comment"))
        if is_internal_comment(el.get(w_attr("author"), ""), comment_text(el))
    } if "word/comments.xml" in package.files else set()
    ids.discard("")
    removed = strip_comment_ids(package, ids)
    save_docx(package, output_path)
    from redline_guard.resolution_log import copy_resolution_log

    copy_resolution_log(input_path, output_path)
    return removed


def _reanchor_public_replies(package, note_ids: set[str]) -> None:
    """Keep a public reply when its internal parent is removed.

    Copy the note's document range onto the reply, then clear the thread
    parent so the reply is a standalone comment at the same place.
    """
    comments_xml = package.files.get("word/comments.xml")
    if not comments_xml or not note_ids:
        return
    parent_by_para, para_by_comment = _comment_thread_maps(package, comments_xml)
    note_para_ids = {para_id for para_id, cid in para_by_comment.items() if cid in note_ids}
    replies: list[tuple[str, str, str]] = []
    for para_id, parent in parent_by_para.items():
        if parent not in note_para_ids:
            continue
        reply_cid = para_by_comment.get(para_id)
        note_cid = para_by_comment.get(parent)
        if reply_cid and note_cid:
            replies.append((reply_cid, note_cid, para_id))
    for reply_cid, note_cid, reply_para in replies:
        for story in package.stories:
            _copy_comment_range_anchors(package, story, note_cid, reply_cid)
        _clear_para_id_parent(package, reply_para)


def _copy_comment_range_anchors(package, story, src_id: str, dst_id: str) -> None:
    root = story.root
    already = any(
        el.tag == q("commentRangeStart") and el.get(w_attr("id")) == dst_id for el in root.iter()
    )
    if already:
        return
    parents = parent_map_from(root)
    changed = False
    for el in list(root.iter()):
        if el.tag not in {q("commentRangeStart"), q("commentRangeEnd")}:
            continue
        if el.get(w_attr("id")) != src_id:
            continue
        parent = parents.get(el)
        if parent is None:
            continue
        clone = ET.Element(el.tag, {w_attr("id"): dst_id})
        idx = list(parent).index(el)
        parent.insert(idx + 1, clone)
        if el.tag == q("commentRangeEnd"):
            _insert_reference_after(clone, parent_map_from(root), _comment_reference_run(dst_id))
        changed = True
    if changed:
        persist_story(package, story)


def _comment_reference_run(cid: str) -> ET.Element:
    ref = ET.Element(q("r"))
    rpr = ET.SubElement(ref, q("rPr"))
    ET.SubElement(rpr, q("rStyle"), {w_attr("val"): "CommentReference"})
    ET.SubElement(ref, q("commentReference"), {w_attr("id"): cid})
    return ref


def _clear_para_id_parent(package, para_id: str) -> None:
    ext = package.files.get("word/commentsExtended.xml")
    if not ext:
        return
    root = parse_xml(ext)
    changed = False
    attr = f"{{{W15}}}paraIdParent"
    for el in root:
        if el.get(f"{{{W15}}}paraId") != para_id:
            continue
        if attr in el.attrib:
            del el.attrib[attr]
            changed = True
    if changed:
        package.files["word/commentsExtended.xml"] = write_tree(root, ext)


def strip_comment_ids(package, ids: set[str]) -> int:
    if not ids or "word/comments.xml" not in package.files:
        return 0
    _reanchor_public_replies(package, ids)
    root = parse_xml(package.files["word/comments.xml"])
    comments = [el for el in root if el.tag == q("comment")]
    para_ids: set[str] = set()
    removed = 0
    for el in comments:
        cid = el.get(w_attr("id"), "")
        if cid not in ids:
            continue
        pid = _comment_para_id(el)
        if pid:
            para_ids.add(pid)
        root.remove(el)
        removed += 1
    remaining = [el for el in root if el.tag == q("comment")]
    if not remaining:
        _strip_all_comment_parts(package)
        return removed
    package.files["word/comments.xml"] = write_tree(root, package.files["word/comments.xml"])
    _drop_satellite_para_ids(package, para_ids)
    _drop_document_anchors(package, ids)
    return removed


def _drop_satellite_para_ids(package, para_ids: set[str]) -> None:
    if not para_ids:
        return
    durable_ids: set[str] = set()
    ids_data = package.files.get("word/commentsIds.xml")
    if ids_data:
        root = parse_xml(ids_data)
        for el in list(root):
            if el.get(f"{{{W16CID}}}paraId") not in para_ids:
                continue
            durable = el.get(f"{{{W16CID}}}durableId")
            if durable:
                durable_ids.add(durable)
            root.remove(el)
        package.files["word/commentsIds.xml"] = write_tree(root, ids_data)
    ext_data = package.files.get("word/commentsExtended.xml")
    if ext_data:
        root = parse_xml(ext_data)
        for el in list(root):
            if el.get(f"{{{W15}}}paraId") in para_ids:
                root.remove(el)
        package.files["word/commentsExtended.xml"] = write_tree(root, ext_data)
    cex_data = package.files.get("word/commentsExtensible.xml")
    if cex_data and durable_ids:
        root = parse_xml(cex_data)
        for el in list(root):
            if el.get(f"{{{W16CEX}}}durableId") in durable_ids:
                root.remove(el)
        package.files["word/commentsExtensible.xml"] = write_tree(root, cex_data)


def _drop_document_anchors(package, ids: set[str] | None) -> None:
    for story in package.stories:
        parents = parent_map_from(story.root)
        changed = False
        for el in list(story.root.iter()):
            if el.tag not in {q("commentRangeStart"), q("commentRangeEnd")}:
                continue
            cid = el.get(w_attr("id"))
            if ids is not None and cid not in ids:
                continue
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)
                changed = True
        parents = parent_map_from(story.root)
        for el in list(story.root.iter(q("r"))):
            ref = el.find(q("commentReference"))
            if ref is None:
                continue
            cid = ref.get(w_attr("id"))
            if ids is not None and cid not in ids:
                continue
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)
                changed = True
        if changed:
            persist_story(package, story)


def _strip_all_comment_parts(package) -> None:
    for name in list(package.files):
        if name.startswith("word/comments"):
            package.files.pop(name, None)
    rels_name = "word/_rels/document.xml.rels"
    if rels_name in package.files:
        text = package.files[rels_name].decode("utf-8")
        text = re.sub(r"<Relationship[^>]+comments[^/]*/>", "", text)
        text = re.sub(r"<Relationship[^>]+comments[^>]*>\s*</Relationship>", "", text)
        package.files[rels_name] = text.encode("utf-8")
    ct = package.files.get("[Content_Types].xml")
    if ct:
        text = ct.decode("utf-8")
        text = re.sub(r"<Override[^>]+comments[^/]*/>", "", text)
        package.files["[Content_Types].xml"] = text.encode("utf-8")
    _drop_document_anchors(package, None)
