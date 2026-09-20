"""Accept or reject existing tracked changes, and produce a clean copy."""

from __future__ import annotations

import copy

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from redline_guard.ooxml import (
    DEL_TAGS,
    FORMAT_CHANGE_TAGS,
    INS_TAGS,
    MOVE_RANGE_TAGS,
    WRAPPER_TAGS,
    _collect_revision_text,
    inline_char,
    iter_outside_fallback,
    iter_own_content,
    mirror_changed_text_boxes,
    text_box_snapshots,
    clone_run_shell,
    is_last_paragraph_in_cell,
    is_last_paragraph_in_header_or_footer,
    is_only_paragraph_in_body,
    is_only_paragraph_in_cell,
    is_only_paragraph_in_header_or_footer,
    load_docx,
    max_revision_id,
    paragraph_mark_kind,
    paragraph_texts,
    parent_map_from,
    persist_story,
    q,
    refuse_overwrite,
    sanitize_copied_properties,
    save_docx,
    set_text_node,
    utc_now,
    w_attr,
)
from redline_guard.resolution_log import DEFAULT_AUTHOR, require_author

WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"


class ResolveError(ValueError):
    """A revision could not be accepted or rejected."""


@dataclass
class RevisionRef:
    kind: str
    rev_id: str
    author: str
    text: str
    location: str
    story: str
    paragraph: int
    label: str
    element: ET.Element
    story_name: str
    date: str = ""
    move: str = ""  # the move's name when this is one half of a move
    move_role: str = ""  # "from" or "to"
    paired_with: str = ""  # ids of the other half, comma-separated


def list_revisions(path: str | Path) -> list[RevisionRef]:
    package = load_docx(path)
    out: list[RevisionRef] = []
    seen: set[str] = set()
    for story in package.stories:
        moves = _move_index(story.root)
        halves: dict[tuple[str, str], list[str]] = {}
        for el, (name, role) in moves.items():
            halves.setdefault((name, role), []).append(el.get(w_attr("id"), ""))
        for para in story.paragraphs:
            # A paragraph owns its own revisions, not those of a text box it
            # holds (listed on their own) nor the box's mc:Fallback mirror.
            for el in iter_own_content(para.element):
                if el.tag in INS_TAGS:
                    kind = "ins"
                elif el.tag in DEL_TAGS:
                    kind = "del"
                elif el.tag in FORMAT_CHANGE_TAGS:
                    kind = "format"
                else:
                    continue
                rev = next((r for r in para.revisions if r.rev_id == el.get(w_attr("id"), "")), None)
                rev_id = el.get(w_attr("id"), "")
                seen.add(rev_id)
                ref = RevisionRef(
                    kind=kind,
                    rev_id=rev_id,
                    author=el.get(w_attr("author"), "") if rev is None else rev.author,
                    text="" if rev is None else rev.text,
                    location=para.location,
                    story=para.story,
                    paragraph=para.index,
                    label=para.label,
                    element=el,
                    story_name=story.name,
                    date=el.get(w_attr("date"), "") if rev is None else rev.date,
                )
                if el in moves:
                    name, role = moves[el]
                    other = "to" if role == "from" else "from"
                    ref.move, ref.move_role = name, role
                    ref.paired_with = ", ".join(i for i in halves.get((name, other), []) if i)
                out.append(ref)
        parents = parent_map_from(story.root)
        for el in story.root.iter():
            if el.tag not in INS_TAGS | DEL_TAGS or not _is_row_revision(el, parents):
                continue
            rev_id = el.get(w_attr("id"), "")
            if not rev_id or rev_id in seen:
                continue
            seen.add(rev_id)
            tr = _row_of(el, parents)
            first = next(tr.iter(q("p")), None)
            para = next((p for p in story.paragraphs if p.element is first), None)
            out.append(
                RevisionRef(
                    kind="ins" if el.tag in INS_TAGS else "del",
                    rev_id=rev_id,
                    author=el.get(w_attr("author"), ""),
                    text=_row_text(tr),
                    location=para.location if para else f"{story.name} table row",
                    story=para.story if para else story.name,
                    paragraph=para.index if para else 0,
                    label=para.label if para else "",
                    element=el,
                    story_name=story.name,
                    date=el.get(w_attr("date"), ""),
                )
            )
    return out


def format_revisions(revisions: list[RevisionRef]) -> str:
    if not revisions:
        return "No tracked revisions."
    lines = []
    for rev in revisions:
        label = f"  ({rev.label})" if rev.label else ""
        if rev.kind == "ins":
            verb = "inserted paragraph mark" if not rev.text else "inserted"
        elif rev.kind == "del":
            verb = "deleted paragraph mark" if not rev.text else "deleted"
        else:
            verb = "changed formatting"
        head = f"[{rev.rev_id}] {rev.kind} {rev.location}{label}"
        if rev.move:
            # One move, two halves: either id accepts or rejects both.
            head += f"  (move {rev.move}: {rev.move_role}, pairs with [{rev.paired_with}])"
            verb = "moved from here" if rev.move_role == "from" else "moved here"
        lines.append(head)
        lines.append(f"    {rev.author} {verb}: {rev.text}")
    return "\n".join(lines)


def resolve_revisions(
    input_path: str | Path,
    output_path: str | Path,
    actions: list[dict[str, Any]],
    log_path: str | Path | None = None,
    author: str = DEFAULT_AUTHOR,
    date: str | None = None,
) -> list[str]:
    """Accept or reject revisions by id.

    Accept is Word's Accept: their markup goes and the text is agreed. Reject on
    a revision by another author is written as a tracked change of ours beside
    their pending revision (see ``_reject_as_tracked_change``), so the
    counterparty sees the reversal under our name. ``"untracked": true`` asks
    for Word's Reject instead, which removes their markup and shows nothing.
    Rejecting a revision we authored withdraws it, as Word does; accepting one
    is refused, because that would turn our tracked edit into untracked text.

    The batch is all-or-nothing: a refusal names the revision and nothing is
    written. Returns one line per action naming everything it resolved.
    """
    require_author(author)
    from redline_guard.resolution_log import write_resolve_log

    if not actions:
        raise ResolveError("No actions given; pass at least one accept or reject.")
    refuse_overwrite(input_path, output_path, ResolveError)
    session = _Session(input_path, author, date or utc_now())
    snapshots = text_box_snapshots(session.package)
    for spec in actions:
        session.run(spec)
    # A decision on a revision inside a text box is mirrored into the
    # mc:Fallback copy, so both branches read the same afterwards.
    session.dirty |= mirror_changed_text_boxes(session.package, snapshots, session.allocate)
    for story in session.package.stories:
        if story.part_name in session.dirty:
            persist_story(session.package, story)
    for part in _drop_orphan_notes(session.package, session.note_refs_before):
        persist_story(session.package, session.package.story(part))
    save_docx(session.package, output_path)
    write_resolve_log(input_path, output_path, session.log_entries, log_path=log_path)
    return session.done


@dataclass
class _Move:
    name: str = ""
    role: str = ""
    partners: list[tuple[str, str, ET.Element]] | None = None  # (id, kind, element) of the other half


class _Session:
    """State of one resolve batch: the package, its revision catalog, and the log so far."""

    def __init__(self, input_path: str | Path, author: str, when: str) -> None:
        self.input_path = input_path
        self.author = author
        self.when = when
        self.snapshot = {rev.rev_id: rev for rev in list_revisions(input_path)}
        self.package = load_docx(input_path)
        self.catalog = _index_revisions(self.package)
        self.done: list[str] = []
        self.dirty: set[str] = set()
        self.log_entries: list[dict[str, Any]] = []
        self.consumed_by: dict[str, tuple[str, str]] = {}
        self.decided: set[str] = set()
        self.reversals, self.standing = _standing_reversals(input_path)
        self.next_id = max_revision_id(self.package.files) + 1
        self.next_doc_pr = _max_doc_pr_id(self.package) + 1
        self.warned = False
        self.note_refs_before = _referenced_note_ids(self.package)

    def allocate(self) -> str:
        value = str(self.next_id)
        self.next_id += 1
        return value

    def doc_pr(self) -> str:
        value = str(self.next_doc_pr)
        self.next_doc_pr += 1
        return value

    # ------------------------------------------------------------- one action

    def run(self, spec: dict[str, Any]) -> None:
        known = {"action", "type", "id", "rev_id", "find", "untracked"}
        unknown = set(spec) - known
        if unknown:
            name = sorted(unknown)[0]
            raise ResolveError(f"Unsupported field {name!r} in resolve spec.")
        action = spec.get("action") or spec.get("type")
        if action not in {"accept", "reject"}:
            raise ResolveError(f"Unsupported action {action!r}; use accept or reject.")
        rev_id = str(spec.get("id") or spec.get("rev_id") or "")
        if not rev_id:
            raise ResolveError("Each accept/reject needs the revision 'id' from `redline_guard revisions`.")
        find = spec.get("find", "")
        if "find" in spec and (not isinstance(find, str) or not find):
            raise ResolveError("find must be a non-empty string; omit it to resolve the whole revision.")
        untracked = spec.get("untracked", False)
        if "untracked" in spec and type(untracked) is not bool:
            raise ResolveError("untracked must be true or false.")
        if untracked and action != "reject":
            raise ResolveError("untracked only applies to reject; accept always removes the markup.")
        try:
            self._run(action, rev_id, find, untracked)
        except ResolveError as exc:
            # A refusal in a batch must say which id it is about.
            message = str(exc)
            if rev_id not in message:
                message = f"revision {rev_id}: {message}"
            raise ResolveError(message) from None

    def _run(self, action: str, rev_id: str, find: str, untracked: bool) -> None:
        consumed = self.consumed_by.get(rev_id)
        if consumed is not None:
            prior_action, parent_id = consumed
            if action != prior_action:
                raise ResolveError(
                    f"Revision id {rev_id} was consumed by {prior_action} of revision "
                    f"{parent_id}; it cannot also be {action}ed."
                )
            if find:
                raise ResolveError(
                    f"Revision id {rev_id} was consumed by {prior_action} of revision "
                    f"{parent_id}; a partial resolution cannot be applied."
                )
            kind = self.snapshot[rev_id].kind if rev_id in self.snapshot else "revision"
            self.done.append(f"{action} consumed {kind} {rev_id} with {parent_id}")
            return
        if rev_id not in self.catalog:
            raise ResolveError(f"No tracked revision with id {rev_id}.")
        if not find and rev_id in self.decided:
            raise ResolveError(f"Revision {rev_id} was already decided earlier in this batch; remove the duplicate action.")
        kind, element, story = self.catalog[rev_id]
        parents = parent_map_from(story.root)
        structural = _is_row_revision(element, parents) or _is_paragraph_mark_revision(element, parents)
        if find and (kind == "format" or structural):
            raise ResolveError("find can only target a text insertion or deletion.")
        move = _move_of(story.root, element)
        if find and move.name:
            raise ResolveError(f"find cannot target part of a move; accept or reject move {move.name} ({rev_id}) as a whole.")
        ours = element.get(w_attr("author"), "") == self.author
        if action == "accept" and ours:
            raise ResolveError(
                f"Revision {rev_id} is our own tracked change; leave it tracked, or reject --id {rev_id} to withdraw it."
            )
        standing, whole = ([], False) if ours else self._our_reversal_of(rev_id, element, kind, parents)
        if standing and whole and action == "accept":
            # A partial reversal is different: accepting the whole revision then
            # accepts the rest and leaves our deletion of the span pending.
            raise ResolveError(
                f"Revision {rev_id} carries our tracked rejection ({', '.join(standing)}); "
                f"reject --id {standing[0]} to withdraw it first, then accept {rev_id}."
            )
        if standing and action == "reject" and not find and (whole or kind != "ins" or untracked):
            raise ResolveError(
                f"Revision {rev_id} already carries our tracked rejection ({', '.join(standing)}); "
                f"reject --id {standing[0]} to withdraw it before deciding again."
            )
        before = dict(self.catalog)
        first_new_id = self.next_id
        withdrawn: dict[str, str] = {}  # our id removed in this action -> the revision it restored
        withdraws = ""  # for a withdrawal of our own reversal: the revision it reversed
        notes: list[str] = []
        tracked = action == "reject" and not ours and kind != "format" and not untracked
        if tracked:
            if kind == "del" and not find:
                outer = _covering_insertion(element, parents, self.author)
                if outer is not None and outer.get(w_attr("id"), "") in self.standing:
                    # Their deletion sits inside an insertion we already struck in
                    # full: whatever happens to it, the text is gone.
                    self.done.append(f"reject del {rev_id} covered by our rejection of ins {outer.get(w_attr('id'), '')} (no change)")
                    return
            if not self.warned:
                from redline_guard.resolution_log import warn_if_author_exists

                warn_if_author_exists(self.input_path, self.author)
                self.warned = True
            if kind == "ins":
                withdrawn.update(self._withdraw_nested_restorations(element, parents))
                parents = parent_map_from(story.root)
            line = f"reject {kind} {rev_id} as a tracked change"
            note_refs = _note_refs(element) if kind == "del" and not find else []
            their_author, their_date = element.get(w_attr("author"), ""), element.get(w_attr("date"), "")
            self._reject_tracked(rev_id, kind, element, story, parents, find, move, first_new_id)
            if note_refs:
                _restore_note_text_tracked(self, note_refs, their_author, their_date)
            for other_id, other_kind, other_el in move.partners or []:
                other_first = self.next_id
                self._reject_tracked(other_id, other_kind, other_el, story, parent_map_from(story.root), "", move, other_first)
                self.consumed_by[other_id] = ("reject", rev_id)
            if move.partners:
                notes.append(f"move {move.name}: also rejects " + ", ".join(f"{k} {i}" for i, k, _ in move.partners))
        else:
            if ours:
                withdraws = self._withdrawn_id(rev_id, element, kind, parents)
            elif action == "reject" and kind == "ins":
                withdrawn.update(self._withdraw_nested_restorations(element, parents))
                parents = parent_map_from(story.root)
            if find:
                element = _isolate_revision_span(element, find, self.allocate, parents)
                parents = parent_map_from(story.root)
            note_refs = _note_refs(element) if kind == "del" and action == "reject" else []
            note_author, note_date = element.get(w_attr("author"), ""), element.get(w_attr("date"), "")
            _resolve_element(element, parents, kind, action)
            if note_refs:
                _restore_note_text(self, note_refs, note_author, note_date)
            for other_id, other_kind, other_el in move.partners or []:
                _resolve_element(other_el, parent_map_from(story.root), other_kind, action)
            self.dirty.add(story.part_name)
            self.catalog = _index_revisions(self.package)
            line = f"{action} {kind} {rev_id}"
            if find and rev_id in self.catalog:
                prior = self.snapshot.get(rev_id)
                self.log_entries.append({
                    "id": rev_id, "action": action, "kind": kind,
                    "author": element.get(w_attr("author"), ""),
                    "text": find, "find": find,
                    "split_ids": [str(i) for i in range(first_new_id, self.next_id)],
                    "location": "" if prior is None else prior.location,
                })
            if move.partners:
                notes.append(f"move {move.name}: also resolves " + ", ".join(f"{k} {i}" for i, k, _ in move.partners))
        partner_ids = {i for i, _, _ in move.partners or []}
        also: list[str] = []
        for vanished_id in [i for i in before if i not in self.catalog]:
            prior = self.snapshot.get(vanished_id)
            vanished_kind = before[vanished_id][0] if prior is None else prior.kind
            entry: dict[str, Any] = {
                "id": vanished_id,
                "action": action,
                "kind": vanished_kind,
                "author": "" if prior is None else prior.author,
                "date": "" if prior is None else prior.date,
                "text": "" if prior is None else prior.text,
                "location": "" if prior is None else prior.location,
            }
            if vanished_id == rev_id and withdraws:
                entry["withdraws"] = withdraws
            if vanished_id in withdrawn:
                entry["withdraws"] = withdrawn[vanished_id]
                self._forget_reversal(withdrawn[vanished_id], vanished_id)
            if vanished_id != rev_id:
                self.consumed_by[vanished_id] = (action, rev_id)
                if vanished_id not in withdrawn and vanished_id not in partner_ids:
                    also.append(f"{vanished_kind} {vanished_id}")
            self.log_entries.append(entry)
        if withdraws:
            self._forget_reversal(withdraws, rev_id)
            their_kind = before[withdraws][0] if withdraws in before else self.snapshot[withdraws].kind
            notes.append(f"withdraws our rejection of {their_kind} {withdraws}")
        if also:
            notes.append("also resolves " + ", ".join(also))
        for our_id, their_id in withdrawn.items():
            our_kind = before[our_id][0] if our_id in before else "ins"
            notes.append(f"withdraws our {our_kind} {our_id}, the restoration of del {their_id}")
        if notes:
            line += " (" + "; ".join(notes) + ")"
        self.done.append(line)
        if not find:
            self.decided.add(rev_id)

    def _reject_tracked(self, rev_id, kind, element, story, parents, find, move, first_new_id) -> None:
        acted, span = _reject_as_tracked_change(
            element, kind, find, self.author, self.when, self.allocate, parents, doc_pr=self.doc_pr, rev_id=rev_id,
        )
        self.dirty.add(story.part_name)
        self.catalog = _index_revisions(self.package)
        prior = self.snapshot.get(rev_id)
        entry: dict[str, Any] = {
            "id": rev_id, "action": "reject", "kind": kind, "tracked": True,
            "author": element.get(w_attr("author"), ""),
            "date": element.get(w_attr("date"), ""),
            "text": acted,
            "location": "" if prior is None else prior.location,
        }
        if span:
            entry["find"] = span
        ours = [
            str(i) for i in range(first_new_id, self.next_id)
            if str(i) in self.catalog and self.catalog[str(i)][1].get(w_attr("author"), "") == self.author
        ]
        entry["reversal_ids"] = ours
        if move.name:
            entry["move"] = move.name
        self.log_entries.append(entry)
        self.reversals.setdefault(rev_id, []).extend(ours)
        self.standing.add(rev_id)

    # -------------------------------------------------------- reversal lookup

    def _our_reversal_of(self, rev_id: str, element: ET.Element, kind: str, parents) -> tuple[list[str], bool]:
        """Ids of our standing reversal of their revision, and whether it covers the whole of it.

        The log decides whether a rejection stands; the document locates the
        reversal markup when the log did not record its ids.
        """
        if rev_id not in self.standing:
            return [], False
        ids = [i for i in self.reversals.get(rev_id, []) if i in self.catalog]
        if not ids:
            ids = _structural_reversal(element, kind, parents, self.author)
        if _is_paragraph_mark_revision(element, parents) or _is_row_revision(element, parents):
            whole = True
        elif kind == "ins":
            whole = _fully_struck(element, self.author)
        else:
            want = _collect_revision_text(element, deleted=True)
            whole = any(
                i in self.catalog and _collect_revision_text(self.catalog[i][1], deleted=False) == want for i in ids
            )
        return ids, whole

    def _withdrawn_id(self, rev_id: str, element: ET.Element, kind: str, parents) -> str:
        """The counterparty revision our revision ``rev_id`` reverses, if it is a standing reversal."""
        for their_id, ours in self.reversals.items():
            if rev_id in ours and their_id in self.standing and their_id in self.catalog:
                return their_id
        candidate = _structural_reversed(element, kind, parents, self.author)
        return candidate if candidate in self.standing else ""

    def _withdraw_nested_restorations(self, element: ET.Element, parents) -> dict[str, str]:
        """Remove our restorations of deletions nested in their insertion we are rejecting.

        Returns our removed ids mapped to the deletion each restored.
        """
        withdrawn: dict[str, str] = {}
        for deletion in list(element.iter()):
            if deletion.tag not in DEL_TAGS or deletion.get(w_attr("author"), "") == self.author:
                continue
            their_id = deletion.get(w_attr("id"), "")
            if their_id not in self.standing:
                continue
            found = [self.catalog[i][1] for i in self.reversals.get(their_id, []) if i in self.catalog]
            if not found:
                restoration = _restoration_after(deletion, parents, self.author)
                found = [restoration] if restoration is not None else []
            for node in found:
                our_id = node.get(w_attr("id"), "")
                _remove_revision_content(node, parents)
                withdrawn[our_id] = their_id
                parents = parent_map_from(_root_of(element, parents))
        return withdrawn

    def _forget_reversal(self, their_id: str, our_id: str) -> None:
        if their_id in self.reversals:
            self.reversals[their_id] = [i for i in self.reversals[their_id] if i != our_id]
        if not self.reversals.get(their_id):
            self.standing.discard(their_id)


def _standing_reversals(input_path: str | Path) -> tuple[dict[str, list[str]], set[str]]:
    """From the incoming log: their id -> our reversal ids, and the ids whose tracked rejection stands."""
    from redline_guard.resolution_log import log_path_for, read_resolution_log, reversal_index, standing_tracked_rejections

    incoming = log_path_for(input_path)
    if not incoming.exists():
        return {}, set()
    try:
        entries = read_resolution_log(incoming)["resolved"]
    except (OSError, ValueError):
        return {}, set()
    return reversal_index(entries), standing_tracked_rejections(entries)


def _max_doc_pr_id(package) -> int:
    best = 0
    for story in package.stories:
        for el in story.root.iter(f"{{{WP_NS}}}docPr"):
            value = el.get("id", "")
            if value.isdecimal():
                best = max(best, int(value))
    return best


def _root_of(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element:
    current = element
    while parents.get(current) is not None:
        current = parents[current]
    return current



# ------------------------------------------------------------------ footnotes and endnotes

NOTE_PARTS = {
    q("footnoteReference"): ("word/footnotes.xml", "footnote", q("footnoteReference")),
    q("endnoteReference"): ("word/endnotes.xml", "endnote", q("endnoteReference")),
}


def _note_refs(element: ET.Element) -> list[tuple[str, str, str]]:
    """(part, note tag, note id) for every note reference inside a revision."""
    return [(NOTE_PARTS[el.tag][0], NOTE_PARTS[el.tag][1], el.get(w_attr("id"), "")) for el in element.iter() if el.tag in NOTE_PARTS]


def _find_note(package, part: str, note_tag: str, nid: str):
    story = next((s for s in package.stories if s.part_name == part), None)
    if story is None:
        return None, None
    for note in story.root.iter(q(note_tag)):
        if note.get(w_attr("id"), "") == nid:
            return story, note
    return story, None


def _restore_note_text(session, refs, author: str, date: str) -> None:
    """A reference deletion is being undone (withdrawal, or Word's Reject): undo the
    matching strike of the note's text, which carries the same author and date."""
    from redline_guard.structure import _has_live_text

    for part, note_tag, nid in refs:
        story, note = _find_note(session.package, part, note_tag, nid)
        if note is None or _has_live_text(note):
            # A note that still shows text was edited on its own; its deletions
            # are separate decisions, not the strike that came with the reference.
            continue
        parents = parent_map_from(story.root)
        for struck in list(note.iter(q("del"))):
            if struck.get(w_attr("author"), "") == author and struck.get(w_attr("date"), "") == date:
                _restore_deletion(struck, parents)
                parents = parent_map_from(story.root)
        session.dirty.add(story.part_name)


def _restore_note_text_tracked(session, refs, author: str, date: str) -> None:
    """Tracked reject of their reference deletion: their strike of the note text stays
    pending and our insertion of the same text follows it, as in the body."""
    for part, note_tag, nid in refs:
        story, note = _find_note(session.package, part, note_tag, nid)
        if note is None:
            continue
        parents = parent_map_from(story.root)
        for struck in list(note.iter(q("del"))):
            if struck.get(w_attr("author"), "") != author or struck.get(w_attr("date"), "") != date:
                continue
            parent = parents.get(struck)
            if parent is None:
                continue
            ins = ET.Element(q("ins"), {w_attr("id"): session.allocate(), w_attr("author"): session.author, w_attr("date"): session.when})
            for run in struck:
                clone = copy.deepcopy(run)
                for t in clone.iter(q("delText")):
                    t.tag = q("t")
                ins.append(clone)
            parent.insert(list(parent).index(struck) + 1, ins)
        session.dirty.add(story.part_name)


def _referenced_note_ids(package) -> dict[str, set[str]]:
    """part -> ids of the notes some story still references."""
    refs: dict[str, set[str]] = {}
    for part, _note_tag, ref_tag in NOTE_PARTS.values():
        refs[part] = {el.get(w_attr("id"), "") for s in package.stories if s.part_name != part for el in s.root.iter(ref_tag)}
    return refs


def _drop_orphan_notes(package, before: dict[str, set[str]] | None = None) -> set[str]:
    """Notes whose reference was removed by the decisions vanish, as they do in Word
    when the deletion of a reference is accepted. ``before`` is the reference map
    taken before the decisions; a note that was never referenced is left alone.
    Returns the parts changed."""
    touched: set[str] = set()
    after = _referenced_note_ids(package)
    for part, note_tag, _ref_tag in NOTE_PARTS.values():
        story = next((s for s in package.stories if s.part_name == part), None)
        if story is None:
            continue
        was = before.get(part, set()) if before is not None else None
        for note in list(story.root.iter(q(note_tag))):
            if note.get(w_attr("type")) in {"separator", "continuationSeparator"}:
                continue
            nid = note.get(w_attr("id"), "")
            if nid in after[part]:
                continue
            if was is not None and nid not in was:
                continue
            story.root.remove(note)
            touched.add(part)
    return touched


def _resolve_element(element, parents, kind: str, action: str) -> None:
    """Apply one decision to an already-selected XML element."""
    mark = _is_paragraph_mark_revision(element, parents)
    move_root: ET.Element | None = None
    move_name = move_role = ""
    if element.tag in {q("moveFrom"), q("moveTo")}:
        move_root = _root_of(element, parents)
        move_name, move_role = _move_index(move_root).get(element, ("", ""))
    if _is_row_revision(element, parents):
        _resolve_row_revision(element, parents, kind, action)
    elif action == "accept":
        if kind == "ins":
            _unwrap_revision(element, parents)
        elif kind == "format":
            _remove_element(element, parents)
        elif mark:
            _accept_deleted_paragraph_mark(_paragraph_of(element, parents), parents)
        else:
            _remove_revision_content(element, parents)
    elif action == "reject":
        if kind == "format":
            _reject_format_change(element, parents)
        elif kind == "ins" and mark:
            _reject_inserted_paragraph_mark(_paragraph_of(element, parents), parents)
        elif kind == "ins":
            _remove_revision_content(element, parents)
        else:
            _restore_deletion(element, parents)
    else:
        raise ResolveError(f"Unsupported action {action!r}; use accept or reject.")
    if move_root is not None and move_name:
        # A resolved move half leaves its range markers empty; Word drops them.
        if not any(value == (move_name, move_role) for value in _move_index(move_root).values()):
            _drop_move_markers(move_root, move_name, move_role)


# ------------------------------------------------------------------ moves


def _move_index(root: ET.Element) -> dict[ET.Element, tuple[str, str]]:
    """moveFrom/moveTo element -> (move name, 'from' | 'to'), from the range markers around it."""
    index: dict[ET.Element, tuple[str, str]] = {}
    open_from: list[tuple[str, str]] = []
    open_to: list[tuple[str, str]] = []
    for el in root.iter():
        tag = el.tag
        if tag == q("moveFromRangeStart"):
            open_from.append((el.get(w_attr("id"), ""), el.get(w_attr("name"), "")))
        elif tag == q("moveFromRangeEnd"):
            open_from = [item for item in open_from if item[0] != el.get(w_attr("id"), "")]
        elif tag == q("moveToRangeStart"):
            open_to.append((el.get(w_attr("id"), ""), el.get(w_attr("name"), "")))
        elif tag == q("moveToRangeEnd"):
            open_to = [item for item in open_to if item[0] != el.get(w_attr("id"), "")]
        elif tag == q("moveFrom") and open_from and open_from[-1][1]:
            index[el] = (open_from[-1][1], "from")
        elif tag == q("moveTo") and open_to and open_to[-1][1]:
            index[el] = (open_to[-1][1], "to")
    return index


def _move_of(root: ET.Element, element: ET.Element) -> _Move:
    """The move ``element`` belongs to, with the elements of its other half."""
    index = _move_index(root)
    if element not in index:
        return _Move()
    name, role = index[element]
    partners = [
        (el.get(w_attr("id"), ""), "del" if el.tag in DEL_TAGS else "ins", el)
        for el, (other_name, other_role) in index.items()
        if other_name == name and other_role != role and el.get(w_attr("id"), "")
    ]
    return _Move(name, role, partners)


def _drop_move_markers(root: ET.Element, name: str, role: str) -> None:
    start_tag = q("moveFromRangeStart") if role == "from" else q("moveToRangeStart")
    end_tag = q("moveFromRangeEnd") if role == "from" else q("moveToRangeEnd")
    ids = {el.get(w_attr("id"), "") for el in root.iter(start_tag) if el.get(w_attr("name"), "") == name}
    parents = parent_map_from(root)
    for el in list(root.iter()):
        if el.tag in {start_tag, end_tag} and el.get(w_attr("id"), "") in ids:
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)


# ------------------------------------------------------ tracked rejection

TEXT_TAGS = {q("t"), q("delText"), q("tab"), q("br"), q("cr"), q("sym"), q("noBreakHyphen"), q("softHyphen")}
ZERO_WIDTH_TAGS = {
    q("bookmarkStart"), q("bookmarkEnd"), q("commentRangeStart"), q("commentRangeEnd"), q("proofErr"),
    q("permStart"), q("permEnd"),
} | MOVE_RANGE_TAGS
# Content a copy cannot carry faithfully: VML shapes and OLE objects carry ids Word
# wants unique, and a text box would duplicate its own paragraphs.
_UNCOPYABLE = {
    q("object"): "an embedded object",
    q("pict"): "a VML picture or shape",
    f"{{{MC_NS}}}AlternateContent": "a text box",
}
_PROPERTY_TAGS = {q("rPr"), q("pPr"), q("trPr"), q("tcPr"), q("tblPr"), q("tblGrid"), q("sdtPr"), q("sdtEndPr"), q("smartTagPr"), q("customXmlPr")}


def _reject_as_tracked_change(
    element: ET.Element,
    kind: str,
    find: str,
    author: str,
    date: str,
    allocate: Callable[[], str],
    parents: dict[ET.Element, ET.Element],
    doc_pr: Callable[[], str] | None = None,
    rev_id: str = "",
) -> tuple[str, str]:
    """Leave their revision pending and write our reversal beside it, as Word does.

    Their insertion keeps its id, author, and date; our ``w:del`` is nested
    inside it, which is the shape Word writes when someone deletes text another
    author inserted, so they see their words struck under our name. Their
    deletion stays and our ``w:ins`` of the same content follows it, so the
    restoration is visibly ours: runs with their formatting, footnote
    references (same footnote), fields, pictures (same image, a fresh drawing
    id), and content controls are copied whole. An inserted paragraph mark
    gets our deleted mark beside theirs; a deleted mark is answered by
    re-splitting the paragraph with our inserted mark; an inserted row gets
    our row deletion beside theirs and a deleted row is followed by our copy
    of it, nested tables included. Accept-all and reject-all then both read
    as the original did, which is what a rejection means.

    Returns the text acted on and the ``find`` span when it was a proper part.
    """
    copier = _Copier(author, date, allocate, doc_pr, rev_id)
    if _is_row_revision(element, parents):
        return _reject_row_as_tracked_change(element, parents, kind, copier), ""
    if _is_paragraph_mark_revision(element, parents):
        paragraph = _paragraph_of(element, parents)
        if kind == "ins":
            _add_paragraph_mark_marker(paragraph, "del", author, date, allocate)
        else:
            _split_paragraph_before_deleted_mark(paragraph, parents, author, date, allocate)
        return "", ""
    deleted = kind == "del"
    full = _collect_revision_text(element, deleted=deleted)
    start, end = 0, len(full)
    if find:
        start = full.find(find)
        if start < 0:
            raise ResolveError(f"Revision does not contain {find!r}.")
        end = start + len(find)
    partial = (start, end) != (0, len(full))
    span = full[start:end] if partial else ""
    if kind == "ins":
        if partial:
            _check_partial_span(element, start, end, deleted=False)
            _split_revision_text_nodes(element, {start, end})
            _, mid, _ = _partition_revision_children(element, start, end, deleted=False)
            _strike_runs([child for child in mid if child.tag == q("r")], element, author, date, allocate)
        else:
            _strike_inserted_content(element, author, date, allocate)
        return full[start:end], span
    if partial:
        # Split a copy so their deletion keeps its runs exactly as they were.
        _check_partial_span(element, start, end, deleted=True)
        source = ET.fromstring(ET.tostring(element, encoding="utf-8"))
        _split_revision_text_nodes(source, {start, end})
        _, mid, _ = _partition_revision_children(source, start, end, deleted=True)
        children = [child for child in mid if child.tag == q("r")]
    else:
        children = list(element)
    nodes = copier.content(children)
    if not nodes:
        raise ResolveError(f"Deletion {rev_id or element.get(w_attr('id'), '')} holds no content to restore; reject it with untracked instead.")
    parent = parents.get(element)
    if parent is None:
        raise ResolveError("Could not find the parent of that revision.")
    siblings = list(parent)
    index = siblings.index(element) + 1
    while index < len(siblings) and siblings[index].tag in {q("moveFromRangeEnd"), q("moveToRangeEnd")}:
        index += 1  # our restoration goes after the move range, not inside it
    _place_restoration(parent, index, copier.wrap(nodes), author, allocate, parents)
    return full[start:end], span


class _Copier:
    """Copies deleted content into our restoring insertion, the way Word restores it."""

    def __init__(self, author: str, date: str, allocate: Callable[[], str], doc_pr: Callable[[], str] | None, rev_id: str) -> None:
        self.author = author
        self.date = date
        self.allocate = allocate
        self.doc_pr = doc_pr
        self.rev_id = rev_id

    def revision(self, tag: str) -> ET.Element:
        return ET.Element(q(tag), {w_attr("id"): self.allocate(), w_attr("author"): self.author, w_attr("date"): self.date})

    def content(self, children: list[ET.Element]) -> list[ET.Element]:
        """Copies of ``children`` as they read with the deletion rejected, without revision markup.

        Text inside a further deletion is not restored; text inside an insertion
        within it is. Zero-width markers and comment reference runs stay with
        their deletion. Wrappers (content controls, hyperlinks, fields, smart
        tags) are copied around their restored content.
        """
        out: list[ET.Element] = []
        for child in children:
            tag = child.tag
            if tag in DEL_TAGS or tag in ZERO_WIDTH_TAGS or tag in _PROPERTY_TAGS or tag == q("lastRenderedPageBreak"):
                continue
            if tag in INS_TAGS:
                out.extend(self.content(list(child)))
                continue
            if tag == q("r"):
                run = self.run(child)
                if run is not None:
                    out.append(run)
                continue
            if tag in WRAPPER_TAGS or tag == q("smartTag"):
                inner = self.content(list(child))
                if not inner:
                    continue
                shell = ET.Element(child.tag, dict(child.attrib))
                for prop in child:
                    if prop.tag in _PROPERTY_TAGS:
                        shell.append(sanitize_copied_properties(prop))
                shell.extend(inner)
                out.append(shell)
                continue
            if tag in _UNCOPYABLE:
                self.refuse(tag)
        return out

    def run(self, run: ET.Element) -> ET.Element | None:
        if run.find(q("commentReference")) is not None and not any(n.tag in TEXT_TAGS for n in run):
            return None
        if not any(n.tag not in {q("rPr"), q("lastRenderedPageBreak")} for n in run):
            return None
        for node in run.iter():
            if node.tag in _UNCOPYABLE:
                self.refuse(node.tag)
        copy = _restored_run(run)
        if self.doc_pr is not None:
            for doc_pr in copy.iter(f"{{{WP_NS}}}docPr"):
                doc_pr.set("id", self.doc_pr())
        return copy

    def refuse(self, tag: str) -> None:
        what = _UNCOPYABLE[tag]
        raise ResolveError(
            f"Rejecting deletion {self.rev_id} as a tracked change would copy {what}; "
            "reject it with untracked, or restore the text with an apply insert."
        )

    def wrap(self, nodes: list[ET.Element]) -> list[ET.Element]:
        """Group restored nodes under our ``w:ins``.

        The schema does not allow a hyperlink or simple field inside ``w:ins``,
        so those wrappers stay outside with our insertion inside them, as Word
        writes an inserted hyperlink.
        """
        out: list[ET.Element] = []
        group: list[ET.Element] = []

        def flush() -> None:
            if group:
                ins = self.revision("ins")
                ins.extend(group)
                out.append(ins)
                group.clear()

        for node in nodes:
            if node.tag in {q("hyperlink"), q("fldSimple")}:
                flush()
                inner = [child for child in node if child.tag not in _PROPERTY_TAGS]
                for child in inner:
                    node.remove(child)
                node.extend(self.wrap(inner))
                out.append(node)
            else:
                group.append(node)
        flush()
        return out


def _place_restoration(
    parent: ET.Element,
    index: int,
    nodes: list[ET.Element],
    author: str,
    allocate: Callable[[], str],
    parents: dict[ET.Element, ET.Element],
) -> None:
    """Place our restoring insertion(s) at ``index`` in ``parent``, the way Word does.

    Word never nests one author's insertion inside another's. When the position
    lies inside the counterparty's ``w:ins``, their insertion is split around
    ours: the pieces keep their author and date (a fresh id on the second
    piece) and still spell out their text.
    """
    if parent.tag in INS_TAGS and parent.get(w_attr("author"), "") != author:
        grand = parents.get(parent)
        if grand is not None:
            position = list(grand).index(parent)
            tail_children = list(parent)[index:]
            if tail_children:
                tail = ET.Element(parent.tag, dict(parent.attrib))
                tail.set(w_attr("id"), allocate())
                for child in tail_children:
                    parent.remove(child)
                    tail.append(child)
                grand.insert(position + 1, tail)
            if len(parent) == 0:
                grand.remove(parent)
                position -= 1
            for offset, node in enumerate(nodes):
                grand.insert(position + 1 + offset, node)
            return
    for offset, node in enumerate(nodes):
        parent.insert(index + offset, node)


class _Allocator:
    """Adapter so apply's helpers can draw ids from resolve's allocator."""

    def __init__(self, allocate: Callable[[], str]) -> None:
        self.allocate = allocate


def _strike_inserted_content(element: ET.Element, author: str, date: str, allocate: Callable[[], str]) -> None:
    """Nest our deletion around every content run under their insertion.

    Consecutive runs share one ``w:del``. Runs already inside a deletion, comment
    reference runs, and zero-width markers (comment ranges, bookmarks, move
    ranges) stay as they are, so a comment on their text keeps its anchor.
    """

    def visit(node: ET.Element) -> None:
        group: list[ET.Element] = []

        def flush() -> None:
            if group:
                _strike_runs(list(group), node, author, date, allocate)
                group.clear()

        for child in list(node):
            if child.tag in DEL_TAGS or child.tag in {q("rPr"), q("pPr")}:
                flush()
                continue
            if child.tag == q("r"):
                if _is_strikeable_run(child):
                    group.append(child)
                else:
                    flush()
                continue
            flush()
            visit(child)
        flush()

    visit(element)


def _is_strikeable_run(run: ET.Element) -> bool:
    ignorable = {q("rPr"), q("commentReference"), q("lastRenderedPageBreak"), q("annotationRef")}
    return any(child.tag not in ignorable for child in run)


def _fully_struck(insertion: ET.Element, author: str) -> bool:
    """True when every content run of their insertion sits inside a deletion and at least one is ours."""
    has_ours = False

    def visit(node: ET.Element) -> bool:
        nonlocal has_ours
        for child in node:
            if child.tag in DEL_TAGS:
                if child.get(w_attr("author"), "") == author:
                    has_ours = True
                continue
            if child.tag == q("r"):
                if _is_strikeable_run(child):
                    return False
                continue
            if child.tag in _PROPERTY_TAGS:
                continue
            if not visit(child):
                return False
        return True

    return visit(insertion) and has_ours


def _covering_insertion(deletion: ET.Element, parents: dict[ET.Element, ET.Element], author: str) -> ET.Element | None:
    """The counterparty insertion holding ``deletion`` that we have already struck in full."""
    current = parents.get(deletion)
    while current is not None:
        if current.tag in INS_TAGS:
            if current.get(w_attr("author"), "") != author and _fully_struck(current, author):
                return current
            return None
        current = parents.get(current)
    return None


def _content_siblings(node: ET.Element, parents: dict[ET.Element, ET.Element], forward: bool) -> list[ET.Element]:
    """Siblings after (or before, nearest first) ``node`` that are not zero-width markers."""
    parent = parents.get(node)
    if parent is None:
        return []
    siblings = list(parent)
    index = siblings.index(node)
    chosen = siblings[index + 1:] if forward else list(reversed(siblings[:index]))
    return [s for s in chosen if s.tag not in ZERO_WIDTH_TAGS and s.tag not in _PROPERTY_TAGS]


def _restoration_after(deletion: ET.Element, parents: dict[ET.Element, ET.Element], author: str) -> ET.Element | None:
    """Our insertion that restores their deletion: the next content sibling, also past their enclosing insertion."""
    want = _collect_revision_text(deletion, deleted=True)
    node = deletion
    while node is not None:
        following = _content_siblings(node, parents, forward=True)
        if following:
            candidate = following[0]
            if candidate.tag in INS_TAGS and candidate.get(w_attr("author"), "") == author:
                got = _collect_revision_text(candidate, deleted=False)
                return candidate if got and got in want else None
            return None
        parent = parents.get(node)
        if parent is not None and parent.tag in INS_TAGS:
            node = parent
            continue
        return None
    return None


def _structural_reversal(element: ET.Element, kind: str, parents: dict[ET.Element, ET.Element], author: str) -> list[str]:
    """Ids of our reversal markup standing on their revision, found in the document itself."""
    holder = parents.get(element)
    if _is_row_revision(element, parents):
        if kind == "ins":
            return [n.get(w_attr("id"), "") for n in holder if n.tag in DEL_TAGS and n.get(w_attr("author"), "") == author]
        row = _row_of(element, parents)
        table = parents.get(row)
        rows = [child for child in table if child.tag == q("tr")] if table is not None else []
        index = rows.index(row)
        if index + 1 < len(rows):
            pr = rows[index + 1].find(q("trPr"))
            if pr is not None:
                return [n.get(w_attr("id"), "") for n in pr if n.tag in INS_TAGS and n.get(w_attr("author"), "") == author]
        return []
    if _is_paragraph_mark_revision(element, parents):
        if kind == "ins":
            return [n.get(w_attr("id"), "") for n in holder if n.tag in DEL_TAGS and n.get(w_attr("author"), "") == author]
        paragraph = _paragraph_of(element, parents)
        previous = _content_siblings(paragraph, parents, forward=False)
        if previous and previous[0].tag == q("p"):
            rpr = previous[0].find(f"{q('pPr')}/{q('rPr')}")
            if rpr is not None:
                return [n.get(w_attr("id"), "") for n in rpr if n.tag in INS_TAGS and n.get(w_attr("author"), "") == author]
        return []
    if kind == "ins":
        found: list[str] = []

        def visit(node: ET.Element) -> None:
            for child in node:
                if child.tag in DEL_TAGS:
                    if child.get(w_attr("author"), "") == author:
                        found.append(child.get(w_attr("id"), ""))
                    continue
                if child.tag in INS_TAGS and child.get(w_attr("author"), "") != element.get(w_attr("author"), ""):
                    continue
                visit(child)

        visit(element)
        return [i for i in found if i]
    if kind == "del":
        restoration = _restoration_after(element, parents, author)
        return [restoration.get(w_attr("id"), "")] if restoration is not None else []
    return []


def _structural_reversed(element: ET.Element, kind: str, parents: dict[ET.Element, ET.Element], author: str) -> str:
    """The counterparty revision id our ``element`` reverses, found in the document itself."""
    holder = parents.get(element)
    if _is_row_revision(element, parents):
        if kind == "del":
            return next((n.get(w_attr("id"), "") for n in holder if n.tag in INS_TAGS and n.get(w_attr("author"), "") != author), "")
        row = _row_of(element, parents)
        table = parents.get(row)
        rows = [child for child in table if child.tag == q("tr")] if table is not None else []
        index = rows.index(row)
        if index > 0:
            pr = rows[index - 1].find(q("trPr"))
            if pr is not None:
                return next((n.get(w_attr("id"), "") for n in pr if n.tag in DEL_TAGS and n.get(w_attr("author"), "") != author), "")
        return ""
    if _is_paragraph_mark_revision(element, parents):
        if kind == "del":
            return next((n.get(w_attr("id"), "") for n in holder if n.tag in INS_TAGS and n.get(w_attr("author"), "") != author), "")
        paragraph = _paragraph_of(element, parents)
        following = _content_siblings(paragraph, parents, forward=True)
        if following and following[0].tag == q("p"):
            nxt = following[0]
            _, accept_text, _ = paragraph_texts(nxt)
            rpr = nxt.find(f"{q('pPr')}/{q('rPr')}")
            if rpr is not None and not accept_text and not any(c.tag == q("r") for c in nxt.iter()):
                return next((n.get(w_attr("id"), "") for n in rpr if n.tag in DEL_TAGS and n.get(w_attr("author"), "") != author), "")
        return ""
    if kind == "del":
        current = parents.get(element)
        while current is not None:
            if current.tag in INS_TAGS:
                return current.get(w_attr("id"), "") if current.get(w_attr("author"), "") != author else ""
            current = parents.get(current)
        return ""
    if kind == "ins":
        ours = _collect_revision_text(element, deleted=False)
        previous = _content_siblings(element, parents, forward=False)
        if not previous:
            return ""
        candidate = previous[0]
        if candidate.tag in INS_TAGS and candidate.get(w_attr("author"), "") != author:
            inner = [c for c in candidate if c.tag not in ZERO_WIDTH_TAGS and c.tag not in _PROPERTY_TAGS]
            candidate = inner[-1] if inner else candidate
        if candidate.tag in DEL_TAGS and candidate.get(w_attr("author"), "") != author:
            theirs = _collect_revision_text(candidate, deleted=True)
            if ours and ours in theirs:
                return candidate.get(w_attr("id"), "")
    return ""


def _strike_runs(
    runs: list[ET.Element],
    parent: ET.Element,
    author: str,
    date: str,
    allocate: Callable[[], str],
) -> None:
    """Wrap sibling runs in our ``w:del``, one wrapper per consecutive group."""
    runs = [run for run in runs if _is_strikeable_run(run)]
    if not runs:
        return
    siblings = list(parent)
    groups: list[list[ET.Element]] = []
    for run in runs:
        if groups and siblings.index(run) == siblings.index(groups[-1][-1]) + 1:
            groups[-1].append(run)
        else:
            groups.append([run])
    for group in groups:
        index = list(parent).index(group[0])
        wrapper = ET.Element(q("del"), {w_attr("id"): allocate(), w_attr("author"): author, w_attr("date"): date})
        for run in group:
            parent.remove(run)
            for node in run:
                if node.tag == q("t"):
                    node.tag = q("delText")
                elif node.tag == q("instrText"):
                    node.tag = q("delInstrText")
            wrapper.append(run)
        parent.insert(index, wrapper)


def _restored_run(run: ET.Element) -> ET.Element:
    """A copy of a deleted run as plain content: formatting kept, revision history dropped."""
    copy = ET.fromstring(ET.tostring(run, encoding="utf-8"))
    rpr = copy.find(q("rPr"))
    if rpr is not None:
        copy.remove(rpr)
        copy.insert(0, sanitize_copied_properties(rpr))
    for node in list(copy):
        if node.tag == q("delText"):
            node.tag = q("t")
        elif node.tag == q("delInstrText"):
            node.tag = q("instrText")
        elif node.tag == q("lastRenderedPageBreak"):
            copy.remove(node)
    return copy


def _add_paragraph_mark_marker(
    paragraph: ET.Element, kind: str, author: str, date: str, allocate: Callable[[], str]
) -> None:
    from redline_guard.apply import _set_paragraph_mark_revision

    _set_paragraph_mark_revision(paragraph, kind, author, date, _Allocator(allocate))


def _split_paragraph_before_deleted_mark(
    paragraph: ET.Element,
    parents: dict[ET.Element, ET.Element],
    author: str,
    date: str,
    allocate: Callable[[], str],
) -> None:
    """Word's shape for re-splitting a paragraph whose mark another author deleted.

    The content moves into a new paragraph in front, carrying the same
    properties and our inserted mark; the paragraph with their deleted mark
    stays behind it, empty. Accept-all keeps our break and joins the empty
    paragraph away; reject-all joins ours back and keeps theirs.
    """
    parent = parents.get(paragraph)
    if parent is None:
        raise ResolveError("Could not find the parent of that paragraph.")
    new_p = ET.Element(q("p"))
    ppr = paragraph.find(q("pPr"))
    if ppr is not None:
        new_p.append(sanitize_copied_properties(ppr))
    _add_paragraph_mark_marker(new_p, "ins", author, date, allocate)
    for child in [c for c in paragraph if c.tag != q("pPr")]:
        paragraph.remove(child)
        new_p.append(child)
    parent.insert(list(parent).index(paragraph), new_p)


def _reject_row_as_tracked_change(
    element: ET.Element,
    parents: dict[ET.Element, ET.Element],
    kind: str,
    copier: _Copier,
) -> str:
    pr = parents[element]
    row = _row_of(element, parents)
    if kind == "ins":
        if not any(n.tag in DEL_TAGS and n.get(w_attr("author"), "") == copier.author for n in pr):
            marker = copier.revision("del")
            change = pr.find(q("trPrChange"))
            pr.insert(list(pr).index(change) if change is not None else len(pr), marker)
        return _row_text(row)
    table = parents.get(row)
    if table is None:
        raise ResolveError("Could not find the table for that row.")
    table.insert(list(table).index(row) + 1, _restored_row(row, copier))
    return _row_text(row)


def _restored_row(row: ET.Element, copier: _Copier) -> ET.Element:
    """Our inserted copy of a row they deleted: properties kept, cell content as our insertions."""
    new = ET.Element(q("tr"))
    pr = row.find(q("trPr"))
    new_pr = sanitize_copied_properties(pr) if pr is not None else ET.Element(q("trPr"))
    new.append(new_pr)
    new_pr.append(copier.revision("ins"))
    for cell in row.findall(q("tc")):
        new_cell = ET.SubElement(new, q("tc"))
        tcpr = cell.find(q("tcPr"))
        if tcpr is not None:
            new_cell.append(sanitize_copied_properties(tcpr))
        new_cell.extend(_restored_blocks([c for c in cell if c.tag != q("tcPr")], copier))
        if not any(child.tag == q("p") for child in new_cell):
            ET.SubElement(new_cell, q("p"))
    return new


def _restored_blocks(children: list[ET.Element], copier: _Copier) -> list[ET.Element]:
    """Copies of block content (paragraphs, nested tables, block controls) with text as our insertions."""
    out: list[ET.Element] = []
    for child in children:
        if child.tag == q("p"):
            new_para = ET.Element(q("p"))
            ppr = child.find(q("pPr"))
            if ppr is not None:
                new_para.append(sanitize_copied_properties(ppr))
            new_para.extend(copier.wrap(copier.content([c for c in child if c.tag != q("pPr")])))
            out.append(new_para)
        elif child.tag == q("tbl"):
            new_tbl = ET.Element(q("tbl"))
            for prop in child:
                if prop.tag in {q("tblPr"), q("tblGrid")}:
                    new_tbl.append(sanitize_copied_properties(prop))
            for tr in child.findall(q("tr")):
                pr = tr.find(q("trPr"))
                if pr is not None and any(n.tag in DEL_TAGS for n in pr):
                    continue  # a row already deleted inside the deleted row is not restored
                new_tbl.append(_restored_row(tr, copier))
            out.append(new_tbl)
        elif child.tag == q("sdt"):
            inner = _restored_blocks([c for c in child.find(q("sdtContent")) or []], copier)
            if not inner:
                continue
            shell = ET.Element(q("sdt"))
            for prop in child:
                if prop.tag in _PROPERTY_TAGS:
                    shell.append(sanitize_copied_properties(prop))
            content = ET.SubElement(shell, q("sdtContent"))
            content.extend(inner)
            out.append(shell)
    return out


def clean_docx(input_path: str | Path, output_path: str | Path, keep_comments: bool = False) -> None:
    """Accept every tracked change and optionally drop comments (signature copy)."""
    refuse_overwrite(input_path, output_path, ResolveError)
    package = load_docx(input_path)
    note_refs_before = _referenced_note_ids(package)
    for story in package.stories:
        _accept_all_in_story(story)
        persist_story(package, story)
    for part in _drop_orphan_notes(package, note_refs_before):
        persist_story(package, package.story(part))
    from redline_guard.comments import is_internal_comment, strip_comment_ids
    from redline_guard.ooxml import parse_xml

    if keep_comments and "word/comments.xml" in package.files:
        root = parse_xml(package.files["word/comments.xml"])
        internal_ids = {
            el.get(w_attr("id"), "")
            for el in root.iter(q("comment"))
            if is_internal_comment(
                el.get(w_attr("author"), ""),
                "".join((node.text or "") for node in el.iter(q("t"))),
            )
        }
        internal_ids.discard("")
        strip_comment_ids(package, internal_ids)
    elif not keep_comments:
        _strip_comments(package)
    save_docx(package, output_path)


def _accept_all_in_story(story) -> None:
    for paragraph in list(story.root.iter(q("p"))):
        parents = parent_map_from(story.root)
        if parents.get(paragraph) is None:
            continue
        if _has_paragraph_mark(paragraph, DEL_TAGS):
            _accept_deleted_paragraph_mark(paragraph, parents)
    parents = parent_map_from(story.root)
    for el in list(story.root.iter()):
        if el.tag not in INS_TAGS | DEL_TAGS or not _is_row_revision(el, parents):
            continue
        if el.tag in DEL_TAGS:
            _remove_row_of(el, parents)
        else:
            _remove_element(el, parents)
        parents = parent_map_from(story.root)
    parents = parent_map_from(story.root)
    for el in list(story.root.iter()):
        if el.tag in FORMAT_CHANGE_TAGS:
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)
    while True:
        parents = parent_map_from(story.root)
        target = None
        kind = ""
        for el in story.root.iter():
            if el.tag in INS_TAGS:
                target, kind = el, "ins"
                break
            if el.tag in DEL_TAGS:
                target, kind = el, "del"
                break
        if target is None:
            break
        if kind == "ins":
            _unwrap_revision(target, parents)
        else:
            _remove_revision_content(target, parents)
    parents = parent_map_from(story.root)
    for el in list(story.root.iter()):
        if el.tag not in MOVE_RANGE_TAGS:
            continue
        parent = parents.get(el)
        if parent is not None:
            parent.remove(el)


def _index_revisions(package) -> dict[str, tuple[str, ET.Element, Any]]:
    """Every revision by id. A text box's mc:Fallback mirror is not indexed: Word
    writes the same ids in both branches, the decision is made on the listed
    mc:Choice copy, and the mirror is rewritten from it afterwards."""
    found: dict[str, tuple[str, ET.Element, Any]] = {}
    for story in package.stories:
        for el in iter_outside_fallback(story.root):
            if el.tag in INS_TAGS:
                found[el.get(w_attr("id"), "")] = ("ins", el, story)
            elif el.tag in DEL_TAGS:
                found[el.get(w_attr("id"), "")] = ("del", el, story)
            elif el.tag in FORMAT_CHANGE_TAGS:
                found[el.get(w_attr("id"), "")] = ("format", el, story)
    found.pop("", None)
    return found


def _is_row_revision(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    parent = parents.get(element)
    if parent is None or parent.tag != q("trPr"):
        return False
    grand = parents.get(parent)
    return grand is not None and grand.tag == q("tr")


def _row_of(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element:
    current: ET.Element | None = element
    while current is not None and current.tag != q("tr"):
        current = parents.get(current)
    if current is None:
        raise ResolveError("Could not find the table row for that revision.")
    return current


def _row_text(row: ET.Element) -> str:
    parts: list[str] = []
    for para in row.iter(q("p")):
        _reject, accept, _revs = paragraph_texts(para)
        if accept:
            parts.append(accept)
    return " ".join(parts)


def _remove_row_of(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    _remove_row(_row_of(element, parents), parents)


def _remove_row(row: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    """Remove a table row the way Word does when a row revision is resolved.

    Comment ranges, comment reference runs, bookmarks, and move-range markers
    inside the row are zero-width markup that must not vanish with the row:
    they collapse into the nearest surviving paragraph, in
    order. A table left without rows is removed, and its container keeps at
    least one paragraph.
    """
    table = parents.get(row)
    if table is None:
        return
    kept = _revision_anchors(row)
    rows = [child for child in table if child.tag == q("tr")]
    index = rows.index(row)
    table.remove(row)
    target: ET.Element | None = None
    at_start = True
    if index + 1 < len(rows):
        target = next(rows[index + 1].iter(q("p")), None)
    elif index > 0:
        paragraphs = list(rows[index - 1].iter(q("p")))
        target, at_start = (paragraphs[-1] if paragraphs else None), False
    container = parents.get(table)
    if not any(child.tag == q("tr") for child in table) and container is not None:
        position = list(container).index(table)
        container.remove(table)
        siblings = list(container)
        following = next((s for s in siblings[position:] if s.tag == q("p")), None)
        preceding = next((s for s in reversed(siblings[:position]) if s.tag == q("p")), None)
        if following is not None:
            target, at_start = following, True
        elif preceding is not None:
            target, at_start = preceding, False
        else:
            target = ET.Element(q("p"))
            container.insert(position, target)
            at_start = True
    if not kept or target is None:
        return
    if at_start:
        offset = 1 if target.find(q("pPr")) is not None else 0
        for position, node in enumerate(kept):
            target.insert(offset + position, node)
    else:
        for node in kept:
            target.append(node)


def _resolve_row_revision(
    element: ET.Element,
    parents: dict[ET.Element, ET.Element],
    kind: str,
    action: str,
) -> None:
    keep_row = (action == "accept" and kind == "ins") or (action == "reject" and kind == "del")
    if keep_row:
        _remove_element(element, parents)
        return
    _remove_row_of(element, parents)


def _is_paragraph_mark_revision(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    parent = parents.get(element)
    if parent is None or parent.tag != q("rPr"):
        return False
    grand = parents.get(parent)
    return grand is not None and grand.tag == q("pPr")


def _has_paragraph_mark(paragraph: ET.Element, tags: set[str]) -> bool:
    rpr = paragraph.find(f"{q('pPr')}/{q('rPr')}")
    return rpr is not None and any(child.tag in tags for child in rpr)


def _paragraph_of(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element:
    current: ET.Element | None = element
    while current is not None and current.tag != q("p"):
        current = parents.get(current)
    if current is None:
        raise ResolveError("Could not find the paragraph for that revision.")
    return current


def _next_paragraph(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element | None:
    parent = parents.get(paragraph)
    if parent is None:
        return None
    siblings = list(parent)
    start = siblings.index(paragraph) + 1
    for sib in siblings[start:]:
        if sib.tag == q("p"):
            return sib
    return None


def _accept_deleted_paragraph_mark(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    """Join this paragraph into the next one, matching Word Accept on a deleted mark."""
    _merge_or_keep_paragraph(paragraph, parents, allow_drop=True)


def _reject_inserted_paragraph_mark(paragraph: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    """Undo a split. Drop the paragraph only when every run is itself an insertion."""
    if _all_runs_are_inserted(paragraph):
        if (
            is_only_paragraph_in_cell(paragraph, parents)
            or is_only_paragraph_in_header_or_footer(paragraph, parents)
            or is_only_paragraph_in_body(paragraph, parents)
        ):
            _clear_paragraph_content(paragraph)
            _clear_paragraph_mark(paragraph)
            return
        parent = parents.get(paragraph)
        if parent is not None:
            parent.remove(paragraph)
        return
    _merge_or_keep_paragraph(paragraph, parents, allow_drop=False)


def _merge_or_keep_paragraph(
    paragraph: ET.Element,
    parents: dict[ET.Element, ET.Element],
    allow_drop: bool,
) -> None:
    parent = parents.get(paragraph)
    if parent is None:
        return
    nxt = _next_paragraph(paragraph, parents)
    content = [child for child in list(paragraph) if child.tag != q("pPr")]
    _, accept_text, _ = paragraph_texts(paragraph)
    if nxt is not None:
        ppr = nxt.find(q("pPr"))
        insert_at = list(nxt).index(ppr) + 1 if ppr is not None else 0
        for offset, child in enumerate(content):
            nxt.insert(insert_at + offset, child)
        parent.remove(paragraph)
        return
    if (
        is_last_paragraph_in_cell(paragraph, parents)
        or is_last_paragraph_in_header_or_footer(paragraph, parents)
        or is_only_paragraph_in_body(paragraph, parents)
        or accept_text.strip()
        or not allow_drop
    ):
        _clear_paragraph_mark(paragraph)
        return
    parent.remove(paragraph)


def _all_runs_are_inserted(paragraph: ET.Element) -> bool:
    parents = parent_map_from(paragraph)
    for run in paragraph.iter(q("r")):
        if not any(child.tag in TEXT_TAGS for child in run):
            continue
        current: ET.Element | None = run
        inside = False
        while current is not None and current is not paragraph:
            if current.tag in INS_TAGS:
                inside = True
                break
            current = parents.get(current)
        if not inside:
            return False
    return True


def _clear_paragraph_mark(paragraph: ET.Element) -> None:
    rpr = paragraph.find(f"{q('pPr')}/{q('rPr')}")
    if rpr is None:
        return
    for child in list(rpr):
        if child.tag in INS_TAGS or child.tag in DEL_TAGS:
            rpr.remove(child)


def _clear_paragraph_content(paragraph: ET.Element) -> None:
    for child in list(paragraph):
        if child.tag != q("pPr"):
            paragraph.remove(child)


def _reject_format_change(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    parent = parents.get(element)
    if parent is None:
        raise ResolveError("Could not find the parent of that revision.")
    inner = next(iter(element), None)
    retained = []
    if element.tag == q("pPrChange"):
        retained = [child for child in parent if child.tag in {q("rPr"), q("sectPr")}]
    for child in list(parent):
        parent.remove(child)
    if inner is not None:
        for child in list(inner):
            parent.append(child)
    for child in retained:
        parent.append(child)


def _unwrap_revision(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    parent = parents.get(element)
    if parent is None:
        raise ResolveError("Could not find the parent of that revision.")
    idx = list(parent).index(element)
    children = list(element)
    parent.remove(element)
    for offset, child in enumerate(children):
        parent.insert(idx + offset, child)


def _remove_element(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    parent = parents.get(element)
    if parent is None:
        raise ResolveError("Could not find the parent of that revision.")
    parent.remove(element)


def _remove_revision_content(
    element: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> None:
    """Remove revision text but keep anchors Word treats as zero-width markup.

    Comment ranges and their reference run may sit inside a deleted or inserted
    revision. Accepting the deletion or rejecting the insertion collapses the
    range to the removal point; it must not orphan the comment body.
    """
    parent = parents.get(element)
    if parent is None:
        raise ResolveError("Could not find the parent of that revision.")
    kept = _revision_anchors(element)
    idx = list(parent).index(element)
    parent.remove(element)
    for offset, child in enumerate(kept):
        parent.insert(idx + offset, child)


def _revision_anchors(element: ET.Element) -> list[ET.Element]:
    markers = {
        q("commentRangeStart"),
        q("commentRangeEnd"),
        q("bookmarkStart"),
        q("bookmarkEnd"),
    } | MOVE_RANGE_TAGS
    kept: list[ET.Element] = []

    def visit(node: ET.Element) -> None:
        for child in node:
            if child.tag in markers:
                kept.append(ET.fromstring(ET.tostring(child, encoding="utf-8")))
                continue
            if child.tag == q("r") and child.find(q("commentReference")) is not None:
                kept.append(ET.fromstring(ET.tostring(child, encoding="utf-8")))
                continue
            visit(child)

    visit(element)
    return kept


def _restore_deletion(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> None:
    for node in element.iter(q("delText")):
        node.tag = q("t")
    _unwrap_revision(element, parents)


def _strip_comments(package) -> None:
    for name in list(package.files):
        if name.startswith("word/comments"):
            package.files.pop(name, None)
    rels_name = "word/_rels/document.xml.rels"
    if rels_name in package.files:
        text = package.files[rels_name].decode("utf-8")
        text = __import__("re").sub(r"<Relationship[^>]+comments[^/]*/>", "", text)
        text = __import__("re").sub(r"<Relationship[^>]+comments[^>]*>\s*</Relationship>", "", text)
        package.files[rels_name] = text.encode("utf-8")
    ct = package.files.get("[Content_Types].xml")
    if ct:
        text = ct.decode("utf-8")
        text = __import__("re").sub(r"<Override[^>]+comments[^/]*/>", "", text)
        package.files["[Content_Types].xml"] = text.encode("utf-8")
    for story in package.stories:
        for el in list(story.root.iter()):
            if el.tag in {q("commentRangeStart"), q("commentRangeEnd")}:
                parent = parent_map_from(story.root).get(el)
                if parent is not None:
                    parent.remove(el)
        parents = parent_map_from(story.root)
        for el in list(story.root.iter()):
            if el.tag != q("r"):
                continue
            if el.find(q("commentReference")) is None:
                continue
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)
        persist_story(package, story)


def _isolate_revision_span(
    element: ET.Element,
    find: str,
    allocate: Callable[[], str],
    parents: dict[ET.Element, ET.Element],
) -> ET.Element:
    """Split a revision so `find` is its own sibling; leftover keeps the original id."""
    deleted = element.tag in DEL_TAGS
    full = _collect_revision_text(element, deleted=deleted)
    start = full.find(find)
    if start < 0:
        raise ResolveError(f"Revision does not contain {find!r}.")
    end = start + len(find)
    if start == 0 and end == len(full):
        return element
    _check_partial_span(element, start, end, deleted)
    new_id = allocate()
    _split_revision_text_nodes(element, {start, end})
    before, mid, after = _partition_revision_children(element, start, end, deleted)
    parent = parents.get(element)
    if parent is None:
        raise ResolveError("Could not find the parent of that revision.")
    orig_id = element.get(w_attr("id"), "")
    for child in list(element):
        element.remove(child)

    def wrap(kids: list[ET.Element], rid: str) -> ET.Element:
        node = ET.Element(element.tag, dict(element.attrib))
        node.set(w_attr("id"), rid)
        for kid in kids:
            node.append(kid)
        return node

    idx = list(parent).index(element)
    if before and after:
        for kid in before:
            element.append(kid)
        match = wrap(mid, new_id)
        tail = wrap(after, allocate())
        parent.insert(idx + 1, match)
        parent.insert(idx + 2, tail)
        return match
    if before:
        for kid in before:
            element.append(kid)
        match = wrap(mid, new_id)
        parent.insert(idx + 1, match)
        return match
    if after:
        match = wrap(mid, new_id)
        for kid in after:
            element.append(kid)
        parent.insert(idx, match)
        return match
    for kid in mid:
        element.append(kid)
    element.set(w_attr("id"), orig_id)
    return element


def _check_partial_span(element: ET.Element, start: int, end: int, deleted: bool) -> None:
    """The span must lie in plain text runs; what sits beside it in the revision may be anything.

    A nested revision, a wrapper (hyperlink, field, content control), an object
    run, or a run carrying a formatting revision inside the span needs its own
    decision; a partial that stops beside one of them is fine.
    """
    text_tags = TEXT_TAGS | {q("rPr")}
    _, mid, _ = _partition_revision_children(element, start, end, deleted)
    for child in mid:
        if child.tag in INS_TAGS | DEL_TAGS:
            raise ResolveError("The span overlaps a nested revision; resolve that revision, or choose a span beside it.")
        if child.tag in WRAPPER_TAGS or child.tag == q("smartTag"):
            names = {q("hyperlink"): "hyperlink", q("sdt"): "content control", q("fldSimple"): "field"}
            raise ResolveError(
                f"The span overlaps a {names.get(child.tag, 'wrapper')}; resolve this revision in full, or choose a span beside it."
            )
        if child.tag == q("r"):
            if any(node.tag not in text_tags for node in child):
                raise ResolveError("The span covers a field, footnote reference, or picture; resolve this revision in full.")
            if child.find(f"{q('rPr')}/{q('rPrChange')}") is not None:
                raise ResolveError("Partial resolution of a formatting revision is not supported.")


def _partition_revision_children(
    element: ET.Element, start: int, end: int, deleted: bool
) -> tuple[list[ET.Element], list[ET.Element], list[ET.Element]]:
    before: list[ET.Element] = []
    mid: list[ET.Element] = []
    after: list[ET.Element] = []
    pos = 0
    for child in list(element):
        text = _child_revision_text(child, deleted, element)
        n = len(text)
        if n == 0:
            if pos <= start:
                before.append(child)
            elif pos >= end:
                after.append(child)
            else:
                mid.append(child)
            continue
        if pos + n <= start:
            before.append(child)
        elif pos >= end:
            after.append(child)
        else:
            mid.append(child)
        pos += n
    return before, mid, after


def _child_revision_text(child: ET.Element, deleted: bool, owner: ET.Element | None = None) -> str:
    """Text of one child as the revision's own text counts it (see ``_collect_revision_text``)."""
    if owner is not None:
        # Same accounting as the whole revision: a wrapper around the child alone.
        probe = ET.Element(owner.tag, dict(owner.attrib))
        probe.append(child)
        return _collect_revision_text(probe, deleted=deleted)
    if child.tag in INS_TAGS | DEL_TAGS:
        return _collect_revision_text(child, deleted=child.tag in DEL_TAGS)
    parts: list[str] = []
    for node in child.iter():
        text = inline_char(node)
        if text:
            parts.append(text)
    return "".join(parts)


def _split_revision_text_nodes(
    element: ET.Element, cuts: set[int]
) -> None:
    """Split direct runs at character boundaries, including tabs and breaks.

    Only runs a cut falls inside are split; ``_check_partial_span`` has already
    made sure the span itself lies in plain text runs.
    """
    text_tags = {q("t"), q("delText")}
    controls = TEXT_TAGS - text_tags  # tab, break, special hyphen, symbol: one character each
    pos = 0
    for run in list(element):
        length = len(_child_revision_text(run, element.tag in DEL_TAGS, element))
        local_cuts = sorted(cut - pos for cut in cuts if pos < cut < pos + length)
        pos += length
        if not local_cuts:
            continue
        if run.tag != q("r") or any(node.tag not in text_tags | controls | {q("rPr")} for node in run):
            raise ResolveError("Partial resolution requires plain text runs; resolve this complex revision in full.")
        pieces = []
        current = clone_run_shell(run)
        offset = 0
        for node in run:
            if node.tag == q("rPr"):
                continue
            text = (node.text or "") if node.tag in text_tags else ""
            size = len(text) if node.tag in text_tags else 1
            boundaries = [offset] + [cut for cut in local_cuts if offset < cut < offset + size] + [offset + size]
            for left, right in zip(boundaries, boundaries[1:]):
                clone = ET.fromstring(ET.tostring(node))
                if node.tag in text_tags:
                    set_text_node(clone, text[left - offset:right - offset])
                current.append(clone)
                if right in local_cuts:
                    pieces.append(current)
                    current = clone_run_shell(run)
            offset += size
        if any(node.tag != q("rPr") for node in current):
            pieces.append(current)
        index = list(element).index(run)
        element.remove(run)
        for offset, piece in enumerate(pieces):
            element.insert(index + offset, piece)
