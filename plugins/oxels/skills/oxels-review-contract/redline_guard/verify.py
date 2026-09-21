"""Compare an original DOCX to an edited copy and flag untracked body edits."""

from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from redline_guard.resolution_log import DEFAULT_AUTHOR, require_author
from redline_guard.ooxml import (
    DEL_TAGS,
    INS_TAGS,
    ParagraphView,
    load_docx,
    paragraph_mark_revision,
    parent_map_from,
    q,
    persist_story,
    save_docx,
    revision_reject_offsets,
    revision_view_shows_markup,
    track_revisions_enabled,
    w_attr,
)


@dataclass
class UntrackedHunk:
    before: str
    after: str


@dataclass
class Failure:
    location: str
    story: str
    paragraph: int
    message: str
    baseline_excerpt: str
    edited_excerpt: str
    untracked_change: UntrackedHunk | None = None
    kind: str = "untracked_edit"

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


@dataclass
class VerifyReport:
    ok: bool
    original: str
    edited: str
    failures: list[Failure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tracked_paragraphs: list[str] = field(default_factory=list)
    accepted_revisions: list[str] = field(default_factory=list)
    rejected_revisions: list[str] = field(default_factory=list)
    untracked_resolutions: list[str] = field(default_factory=list)
    formatting_checked: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "original": self.original,
            "edited": self.edited,
            "failures": [f.to_dict() for f in self.failures],
            "warnings": self.warnings,
            "tracked_paragraphs": self.tracked_paragraphs,
            "accepted_revisions": self.accepted_revisions,
            "rejected_revisions": self.rejected_revisions,
            "untracked_resolutions": self.untracked_resolutions,
            "formatting_checked": self.formatting_checked,
        }


class TrustedAuthors(frozenset):
    """The agent names ``verify`` trusts, in the order they were given.

    A frozenset of names that also compares equal to any one of them, so a
    reader that tests ``element.get(author) == author`` against a single name
    (the formatting and render checks) accepts every trusted name when it is
    handed this object instead of a string. ``compat()`` returns the plain
    string when there is only one name, which keeps the single-author path
    byte-identical to before.
    """

    names: tuple[str, ...]

    def __new__(cls, names):
        ordered = tuple(dict.fromkeys(names))
        self = super().__new__(cls, ordered)
        self.names = ordered
        return self

    def compat(self) -> "str | TrustedAuthors":
        return self.names[0] if len(self.names) == 1 else self

    def describe(self) -> str:
        if len(self.names) == 1:
            return repr(self.names[0])
        return "one of " + ", ".join(repr(name) for name in self.names)

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return other in self
        return frozenset.__eq__(self, other)

    def __ne__(self, other) -> bool:
        if isinstance(other, str):
            return other not in self
        return frozenset.__ne__(self, other)

    __hash__ = frozenset.__hash__

    def __str__(self) -> str:
        return ", ".join(self.names)

    def __repr__(self) -> str:
        return f"TrustedAuthors({list(self.names)!r})"


def trusted_authors(author) -> TrustedAuthors:
    """Normalise ``--author``: a name, a list of names, or nothing (the default author)."""
    if isinstance(author, TrustedAuthors):
        return author
    if author is None:
        names = []
    elif isinstance(author, str):
        names = [author]
    else:
        names = list(author)
    cleaned: list[str] = []
    for name in names:
        name = str(name or "").strip()
        if name and name not in cleaned:
            cleaned.append(name)
    return TrustedAuthors(cleaned or [require_author(DEFAULT_AUTHOR)])


def verify_docx(
    original: str | Path,
    edited: str | Path,
    resolved: list[str | Path] | None = None,
    author: "str | Iterable[str] | None" = DEFAULT_AUTHOR,
    formatting: bool = False,
    prior_round: bool = False,
) -> VerifyReport:
    """``prior_round`` says the original is the counterparty's return of an earlier draft of
    ours, so the trusted name legitimately appears in it already; the author guard is skipped
    and those earlier revisions are baseline, as before. Without it a trusted name that is
    already an author in the original is refused."""
    authors = trusted_authors(author)
    author = authors.compat()
    edit = load_docx(edited)
    report = VerifyReport(ok=True, original=str(original), edited=str(edited))
    clash = None if prior_round else _trusted_author_in_original(original, authors)
    if clash:
        # The gate would otherwise bless edits written under the other side's
        # name. A name that is already a revision or comment author in the
        # original is a party to it, not the agent.
        report.failures.append(Failure(
            location="", story="", paragraph=0, kind="untrusted_author",
            message=(
                f"verify failed: author {clash!r} already appears in the original as a revision or comment author; "
                "the trusted author cannot be a party to the original, so pass the team's name (REDLINE_AUTHOR); "
                "if this original is the counterparty's return of our earlier draft, pass --prior-round."
            ),
            baseline_excerpt="", edited_excerpt=clash,
        ))
        report.ok = False
        return report
    logged, _logged_ids = _load_resolution_entries(original, edited, resolved or [], report)

    if not track_revisions_enabled(edit.files):
        report.warnings.append(
            "Track Changes is off in the edited file (word/settings.xml has no w:trackRevisions). "
            "Future Word edits may not be recorded."
        )
    shown = revision_view_shows_markup(edit.files)
    if shown is False:
        report.warnings.append(
            "The edited file hides markup (w:revisionView). Tracked edits exist in XML but Word may open in No Markup."
        )

    with _resolved_baseline(original, logged, report) as baseline:
        expected = load_docx(baseline)
        orig_stories = {s.name: s for s in expected.stories}
        edit_stories = {s.name: s for s in edit.stories}
        failure_start = len(report.failures)
        for name in sorted(set(orig_stories) | set(edit_stories)):
            orig_story = orig_stories.get(name)
            edit_story = edit_stories.get(name)
            if orig_story is None:
                for para in edit_story.paragraphs if edit_story else []:
                    if para.reject_text.strip():
                        report.failures.append(_silent_add(para))
                continue
            if edit_story is None:
                for para in orig_story.paragraphs:
                    if para.reject_text.strip():
                        report.failures.append(_silent_remove(para))
                continue
            _compare_story(
                orig_story.paragraphs,
                edit_story.paragraphs,
                report,
                InlineContext(authors, _rels_targets(expected.files, orig_story.part_name), _rels_targets(edit.files, edit_story.part_name)),
            )
            _check_text_box_fallbacks(orig_story, edit_story, report)
        _check_logged_resolutions(baseline, edited, [e for e in logged if e.get("tracked")], report)
        _check_new_authors(baseline, edited, authors, report)
        _check_tracked_rejections(edit, logged, authors, report)
        _check_hidden_insertions(edit, authors, report)
        _check_fixed_height_rows(edit, authors, report)
        _check_note_separators(expected, edit, report)
        if logged and len(report.failures) > failure_start:
            report.failures.append(Failure(
                location="", story="", paragraph=0, kind="log_mismatch",
                message="The document does not match the original with the logged decisions applied.",
                baseline_excerpt="", edited_excerpt="",
            ))
        _check_comment_identity(baseline, edited, report)
    if formatting:
        from redline_guard.formatting import compare_formatting

        report.formatting_checked = True
        fmt = compare_formatting(original, edited, author=author, resolved=resolved)
        for item in fmt.failures:
            report.failures.append(
                Failure(
                    location=item.location,
                    story=item.story,
                    paragraph=item.paragraph,
                    message=f"{item.kind}: {item.message}",
                    baseline_excerpt=str(item.original),
                    edited_excerpt=str(item.edited),
                    kind="untracked_formatting",
                )
            )
    report.accepted_revisions = list(dict.fromkeys(report.accepted_revisions))
    report.rejected_revisions = list(dict.fromkeys(report.rejected_revisions))
    report.ok = not report.failures
    return report


def format_report(report: VerifyReport) -> str:
    refusal = next((f for f in report.failures if f.kind == "untrusted_author"), None)
    if refusal is not None:
        return refusal.message
    lines: list[str] = []
    if report.ok:
        lines.append("OK: every edit on top of the original document is tracked.")
        if report.accepted_revisions:
            lines.append("Accepted existing redlines:")
            lines.extend(f"  - {item}" for item in report.accepted_revisions)
        if report.rejected_revisions:
            lines.append("Rejected existing redlines:")
            lines.extend(f"  - {item}" for item in report.rejected_revisions)
        if report.tracked_paragraphs:
            lines.append("Tracked edits found in:")
            lines.extend(f"  - {loc}" for loc in report.tracked_paragraphs)
    else:
        lines.append("FAIL: some edits are not tracked redlines.")
        for failure in report.failures:
            lines.append(f"- {failure.message}")
            if failure.untracked_change:
                lines.append(f"    untracked change: {failure.untracked_change.before!r} → {failure.untracked_change.after!r}")
            if failure.baseline_excerpt:
                lines.append(f"    baseline: {failure.baseline_excerpt!r}")
            if failure.edited_excerpt:
                lines.append(f"    edited:   {failure.edited_excerpt!r}")
    for warning in report.warnings:
        lines.append(f"warning: {warning}")
    return "\n".join(lines)


def _load_resolution_entries(
    original: str | Path,
    edited: str | Path,
    extra: list[str | Path],
    report: VerifyReport,
) -> tuple[list[dict], set[str]]:
    from redline_guard.resolution_log import log_matches_original, log_path_for, read_resolution_log, resolution_entry_key

    paths: list[str | Path] = []
    auto = log_path_for(edited)
    if auto.exists():
        paths.append(auto)
    paths.extend(extra)
    entries: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        try:
            data = read_resolution_log(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report.failures.append(
                Failure(
                    location="",
                    story="",
                    paragraph=0,
                    message=f"Could not read resolution log {path}: {exc}",
                    baseline_excerpt="",
                    edited_excerpt="",
                    kind="wrong_resolution_log",
                )
            )
            continue
        if not log_matches_original(data, original):
            belongs = data["source"] or "a different document"
            report.failures.append(
                Failure(
                    location="",
                    story="",
                    paragraph=0,
                    message=f"Resolution log belongs to {belongs}, not {original}.",
                    baseline_excerpt="",
                    edited_excerpt="",
                    kind="wrong_resolution_log",
                )
            )
            continue
        for item in data["resolved"]:
            rev_id = str(item.get("id", ""))
            key = resolution_entry_key(item)
            if not rev_id or key in seen:
                continue
            entries.append(item)
            seen.add(key)
    entries = effective_resolution_entries(entries)
    return entries, {str(item["id"]) for item in entries}


def effective_resolution_entries(entries: list[dict]) -> list[dict]:
    """Replay the log in order so a later decision supersedes an earlier tracked rejection.

    A tracked rejection (``"tracked": true``) leaves their revision pending with
    our reversal beside it, and ``verify`` demands that reversal. Three later
    events on the same revision end that demand:

    - a withdrawal: a ``reject`` event carrying ``"withdraws": "<their id>"`` (``"reversal_of"`` is read too),
      written when ``reject --id <ours>`` removes our reversal. It cancels every
      earlier tracked reject event on the revision it names, or only the events
      with the same ``find`` when the withdrawal names a span, and is then
      dropped: it names one of our revisions, which the original never holds;
    - a whole ``accept`` of the revision (no ``find``);
    - a whole ``reject`` without markup (no ``find``, not tracked).

    A partial later decision (``find``) leaves the tracked rejection standing,
    and a tracked rejection logged again after any of these is demanded again.
    """
    superseded: set[int] = set()
    standing: dict[str, list[dict]] = {}
    kept: list[dict] = []
    for entry in entries:
        rid = str(entry.get("id", ""))
        target = entry.get("reversal_of", entry.get("withdraws"))  # resolve writes "withdraws"
        if target is not None and entry.get("action") == "reject" and not entry.get("tracked"):
            target = str(target)
            span = entry.get("find")
            remaining = []
            for prior in standing.get(target, []):
                if span and prior.get("find") != span:
                    remaining.append(prior)
                    continue
                superseded.add(id(prior))
            standing[target] = remaining
            continue
        kept.append(entry)
        if entry.get("kind") == "comment_status":
            continue
        action = entry.get("action")
        if action == "reject" and entry.get("tracked"):
            standing.setdefault(rid, []).append(entry)
        elif action in {"accept", "reject"} and not entry.get("find"):
            for prior in standing.pop(rid, []):
                superseded.add(id(prior))
    return [entry for entry in kept if id(entry) not in superseded]


def _trusted_author_in_original(original: str | Path, authors: TrustedAuthors) -> str:
    """The first trusted name that is already a revision or comment author in the original."""
    from redline_guard.resolution_log import document_authors

    present = {name.lower() for name in document_authors(original)}
    for name in authors.names:
        if name.lower() in present:
            return name
    return ""


def _check_logged_resolutions(
    original: str | Path,
    edited: str | Path,
    logged: list[dict],
    report: VerifyReport,
    vanished_row_inner_ids: set[str] | None = None,
) -> None:
    from redline_guard.resolve import list_revisions

    orig_revs = [rev for rev in list_revisions(original) if rev.rev_id]
    edit_revs = [rev for rev in list_revisions(edited) if rev.rev_id]
    edit_ids = {rev.rev_id for rev in edit_revs}
    recognized = _recognized_original_ids(orig_revs, edit_revs, original, edited)
    logged_by_id = {str(item.get("id")): item for item in logged}
    for rev in orig_revs:
        if rev.rev_id in edit_ids or rev.rev_id in recognized:
            continue
        if vanished_row_inner_ids and rev.rev_id in vanished_row_inner_ids:
            continue
        entry = logged_by_id.get(rev.rev_id)
        if entry is None:
            detail = (
                f"In {rev.location} {rev.kind} [{rev.rev_id}] by {rev.author} "
                f"({rev.text!r}) vanished without a resolution log."
            )
            report.untracked_resolutions.append(detail)
            report.failures.append(
                Failure(
                    location=rev.location,
                    story=rev.story,
                    paragraph=rev.paragraph,
                    message=detail,
                    baseline_excerpt=_excerpt(rev.text),
                    edited_excerpt="",
                    kind="untracked_resolution",
                )
            )
            continue
        if entry.get("tracked"):
            # A tracked rejection leaves their revision in place; a log that
            # says so while the revision is gone describes another document.
            report.failures.append(Failure(
                location=rev.location, story=rev.story, paragraph=rev.paragraph, kind="log_mismatch",
                message=(
                    f"In {rev.location} {rev.kind} [{rev.rev_id}] by {rev.author} ({rev.text!r}) is logged as "
                    "rejected by a tracked change, but the revision is gone."
                ),
                baseline_excerpt=_excerpt(rev.text), edited_excerpt="",
            ))
            continue
        action = entry.get("action")
        if action == "accept":
            if rev.kind == "ins":
                verb = "insert"
            elif rev.kind == "del":
                verb = "deletion"
            else:
                verb = rev.kind
            report.accepted_revisions.append(f"accepted {verb} [{rev.rev_id}] in {rev.location}")
        else:
            report.rejected_revisions.append(f"rejected {rev.kind} [{rev.rev_id}] in {rev.location}")


def _check_new_authors(
    original: str | Path,
    edited: str | Path,
    expected: "str | Iterable[str] | TrustedAuthors",
    report: VerifyReport,
) -> None:
    from redline_guard.comments import INTERNAL_AUTHOR_MARK, list_comments
    from redline_guard.resolve import list_revisions

    authors = trusted_authors(expected)
    orig_revs = [rev for rev in list_revisions(original) if rev.rev_id]
    edit_revs = [rev for rev in list_revisions(edited) if rev.rev_id]
    orig_ids = {rev.rev_id for rev in orig_revs}
    preexisting_edits = _recognized_edit_keys(orig_revs, edit_revs, original, edited)
    for rev in edit_revs:
        if not rev.rev_id or rev.rev_id in orig_ids:
            continue
        if _revision_key(rev) in preexisting_edits:
            continue
        if rev.author in authors:
            continue
        report.failures.append(
            Failure(
                location=rev.location,
                story=rev.story,
                paragraph=rev.paragraph,
                message=(
                    f"In {rev.location} new {rev.kind} [{rev.rev_id}] is authored "
                    f"{rev.author!r}, not {authors.describe()}."
                ),
                baseline_excerpt="",
                edited_excerpt=rev.author,
                kind="wrong_author",
            )
        )
    orig_comments = list_comments(str(original))
    orig_comment_ids = {comment.id for comment in orig_comments}
    orig_comment_content = {(comment.author, comment.text) for comment in orig_comments}
    allowed = set(authors.names) | {f"{name} {INTERNAL_AUTHOR_MARK}" for name in authors.names}
    for comment in list_comments(str(edited)):
        if comment.id in orig_comment_ids or (comment.author, comment.text) in orig_comment_content:
            continue
        if comment.author in allowed:
            continue
        report.failures.append(
            Failure(
                location=comment.location or "",
                story=comment.story or "",
                paragraph=comment.paragraph or 0,
                message=(
                    f"In {comment.location or 'a comment'} new comment [{comment.id}] is authored "
                    f"{comment.author!r}, not {authors.describe()}."
                ),
                baseline_excerpt="",
                edited_excerpt=comment.author,
                kind="wrong_author",
            )
        )


@contextmanager
def _resolved_baseline(original: str | Path, logged: list[dict], report: VerifyReport):
    """Replay decisions in order, then compare against that expected document.

    Paragraph numbers may change during editing; revision identities and the
    recorded split IDs locate the decisions in the original tree instead.
    """
    from redline_guard.resolve import (
        ResolveError, _index_revisions, _isolate_revision_span,
        _is_paragraph_mark_revision, _resolve_element,
    )

    if not logged:
        yield original
        return
    package = load_docx(original)
    from redline_guard.ooxml import mirror_changed_text_boxes, text_box_snapshots
    from redline_guard.resolve import _referenced_note_ids

    note_refs_before = _referenced_note_ids(package)
    box_snapshots = text_box_snapshots(package)
    for entry in logged:
        rid = str(entry.get("id", ""))
        action = entry.get("action")
        if entry.get("reversal_of", entry.get("withdraws")) is not None:
            # A withdrawal names one of our revisions; the original never holds it.
            continue
        try:
            if entry.get("kind") == "comment_status":
                from redline_guard.comments import _set_comment_status, _existing_comment_para_id

                if action not in {"resolve", "reopen"} or type(entry.get("before")) is not bool or entry.get("after") is not (action == "resolve"):
                    raise ResolveError("Invalid logged comment status decision.")
                comments_xml = package.files.get("word/comments.xml", b"")
                from redline_guard.ooxml import parse_xml
                present = bool(comments_xml) and any(n.get(w_attr("id")) == rid for n in parse_xml(comments_xml).iter(q("comment")))
                if present:
                    _, before = _set_comment_status(package, rid, action == "resolve")
                    if before != entry["before"]:
                        raise ResolveError("Comment status does not match the recorded previous state.")
                continue
            if action not in {"accept", "reject"}:
                raise ResolveError(f"Invalid logged action {action!r}.")
            catalog = _index_revisions(package)
            if rid not in catalog:
                # A parent decision can consume its nested revisions. Decisions
                # about newly added revisions have no counterpart in the original.
                continue
            kind, element, story = catalog[rid]
            parents = parent_map_from(story.root)
            mark = _is_paragraph_mark_revision(element, parents)
            find = entry.get("find")
            if "find" in entry and (not isinstance(find, str) or not find):
                raise ResolveError("Logged find must be a non-empty string.")
            if entry.get("tracked"):
                # Their revision stays pending; our reversal beside it is
                # ordinary tracked markup that the comparison sees as ours.
                if action != "reject":
                    raise ResolveError("Only a reject can be recorded as a tracked change.")
                label = ("deleted" if kind == "del" else "inserted") + " paragraph mark" if mark else kind
                detail = f"rejected {label} [{rid}]"
                if find:
                    detail += f" ({find!r})"
                report.rejected_revisions.append(detail + " as a tracked change")
                continue
            if find:
                ids = list(entry.get("split_ids", []))
                used = {el.get(w_attr("id")) for st in package.stories for el in st.root.iter()}
                def allocate():
                    if not ids:
                        raise ResolveError("Partial resolution is missing its split IDs.")
                    value = str(ids.pop(0))
                    if not value.isdecimal() or value in used:
                        raise ResolveError("Partial resolution has an invalid or reused split ID.")
                    used.add(value)
                    return value
                element = _isolate_revision_span(element, find, allocate, parents)
                if ids:
                    raise ResolveError("Partial resolution has unused split IDs.")
                parents = parent_map_from(story.root)
            _resolve_element(element, parents, kind, action)
            verb = "accepted" if action == "accept" else "rejected"
            label = "insert" if kind == "ins" and action == "accept" else "deletion" if kind == "del" and action == "accept" else kind
            if mark:
                label = ("deleted" if kind == "del" else "inserted") + " paragraph mark"
            detail = f"{verb} {label} [{rid}]"
            if find:
                detail += f" ({find!r})"
            target = report.accepted_revisions if action == "accept" else report.rejected_revisions
            target.append(detail)
        except (ValueError, TypeError, KeyError) as exc:
            report.failures.append(Failure(
                location="", story="", paragraph=0, kind="log_mismatch",
                message=f"Cannot replay resolution [{rid}]: {exc}",
                baseline_excerpt="", edited_excerpt="",
            ))
    from redline_guard.resolve import _drop_orphan_notes

    _drop_orphan_notes(package, note_refs_before)  # an accepted reference deletion takes its note with it, as in Word
    # A replayed decision inside a text box is mirrored into the mc:Fallback
    # copy, as resolve does, so the expected document reads the same in both.
    highest = max(
        (int(el.get(w_attr("id"))) for story in package.stories for el in story.root.iter() if (el.get(w_attr("id")) or "").isdigit()),
        default=0,
    )

    def next_id() -> str:
        nonlocal highest
        highest += 1
        return str(highest)

    mirror_changed_text_boxes(package, box_snapshots, next_id)
    for story in package.stories:
        persist_story(package, story)
    with tempfile.TemporaryDirectory(prefix="redline-verify-") as directory:
        baseline = Path(directory) / "expected.docx"
        save_docx(package, baseline)
        yield baseline


def _check_comment_identity(original: str | Path, edited: str | Path, report: VerifyReport) -> None:
    from redline_guard.comments import list_comments

    orig = {comment.id: comment for comment in list_comments(str(original))}
    edit = {comment.id: comment for comment in list_comments(str(edited))}
    edit_content = {(comment.author, comment.text) for comment in edit.values()}
    orig_content = {(comment.author, comment.text) for comment in orig.values()}
    orig_anchor = _comment_anchor_baselines(original)
    edit_anchor = _comment_anchor_baselines(edited)
    for cid, before in orig.items():
        after = edit.get(cid)
        if after is not None and (after.author, after.text) != (before.author, before.text) and (after.author, after.text) in orig_content:
            # Word renumbered the comments and this id now names another
            # comment we know; judge the original one by its content.
            after = None
        if after is None:
            if before.internal or (before.author, before.text) in edit_content:
                continue
            report.failures.append(
                Failure(
                    location=before.location or "",
                    story=before.story or "",
                    paragraph=before.paragraph or 0,
                    message=(
                        f"In {before.location or 'a comment'} "
                        f"comment [{cid}] was removed outside the tool."
                    ),
                    baseline_excerpt=_excerpt(before.text),
                    edited_excerpt="",
                    untracked_change=UntrackedHunk(before=before.text, after=""),
                    kind="untracked_comment_delete",
                )
            )
            continue
        if before.resolved != after.resolved:
            report.failures.append(Failure(
                location=after.location or "", story=after.story or "", paragraph=after.paragraph or 0,
                kind="untracked_comment_status", message=f"Comment [{cid}] status changed without a matching logged decision.",
                baseline_excerpt=str(before.resolved), edited_excerpt=str(after.resolved),
            ))
        if before.text == after.text and before.author == after.author:
            if _minute(before.date) != _minute(after.date):
                report.failures.append(Failure(
                    location=after.location or "", story=after.story or "", paragraph=after.paragraph or 0,
                    kind="untracked_comment_edit",
                    message=f"In {after.location or 'a comment'} comment [{cid}] date changed from {before.date} to {after.date}.",
                    baseline_excerpt=before.date, edited_excerpt=after.date,
                ))
            if cid in orig_anchor and cid in edit_anchor and orig_anchor[cid] != edit_anchor[cid]:
                report.failures.append(Failure(
                    location=after.location or "", story=after.story or "", paragraph=after.paragraph or 0,
                    kind="untracked_comment_edit",
                    message=f"Comment [{cid}] was moved: it anchored to {_excerpt(orig_anchor[cid][1])!r} and now anchors to {_excerpt(edit_anchor[cid][1])!r}.",
                    baseline_excerpt=_excerpt(orig_anchor[cid][1]), edited_excerpt=_excerpt(edit_anchor[cid][1]),
                ))
            continue
        if (before.author, before.text) in edit_content:
            continue
        report.failures.append(
            Failure(
                location=after.location or before.location or "",
                story=after.story or before.story or "",
                paragraph=after.paragraph or before.paragraph or 0,
                message=(
                    f"In {after.location or before.location or 'a comment'} "
                    f"comment [{cid}] was edited outside the tool."
                ),
                baseline_excerpt=_excerpt(before.text),
                edited_excerpt=_excerpt(after.text),
                untracked_change=UntrackedHunk(before=before.text, after=after.text),
                kind="untracked_comment_edit",
            )
        )


def _check_inserted_paragraph_positions(
    original: list[ParagraphView],
    edited: list[ParagraphView],
    report: VerifyReport,
    context: "InlineContext | None",
) -> None:
    """A paragraph the counterparty inserted must still follow the same original text (1.2.1).

    Alignment by baseline text cannot see it move, because its baseline is
    empty; its revision ids find it in the edited file, and the nearest
    preceding paragraph that has baseline text is its anchor in both.
    """
    from redline_guard.ooxml import INS_TAGS

    authors = trusted_authors(context.author) if context is not None else None

    def theirs_ids(para: ParagraphView) -> frozenset:
        ids = set()
        for el in para.element.iter():
            if el.tag in INS_TAGS and (authors is None or el.get(w_attr("author"), "") not in authors):
                ids.add(el.get(w_attr("id"), ""))
        ids.discard("")
        return frozenset(ids)

    def anchors(paras: list[ParagraphView]) -> dict[frozenset, tuple[str, str]]:
        found: dict[frozenset, tuple[str, str]] = {}
        previous = ""
        for para in paras:
            if para.reject_text.strip():
                previous = " ".join(para.reject_text.split())
                continue
            if _tracked_inserted_paragraph(para):
                ids = theirs_ids(para)
                if ids:
                    found[ids] = (previous, para.location)
        return found

    before = anchors(original)
    if not before:
        return
    after = anchors(edited)
    after_by_id = {rid: (ids, value) for ids, value in after.items() for rid in ids}
    for ids, (anchor, location) in before.items():
        match = next((after_by_id[rid] for rid in ids if rid in after_by_id), None)
        if match is None:
            continue  # gone: the resolution checks report it
        _ids, (edited_anchor, edited_location) = match
        if edited_anchor != anchor:
            report.failures.append(Failure(
                location=edited_location, story=edited[0].story if edited else "", paragraph=0,
                kind="mutated_revision",
                message=(
                    f"In {edited_location} the paragraph the counterparty inserted [{', '.join(sorted(ids))}] moved: "
                    f"it followed {_excerpt(anchor, 60)!r} in the original and now follows {_excerpt(edited_anchor, 60)!r}."
                ),
                baseline_excerpt=_excerpt(anchor), edited_excerpt=_excerpt(edited_anchor),
            ))


def _compare_story(
    original: list[ParagraphView],
    edited: list[ParagraphView],
    report: VerifyReport,
    context: "InlineContext | None" = None,
) -> None:
    _check_inserted_paragraph_positions(original, edited, report, context)
    i = 0
    j = 0
    while i < len(original) and j < len(edited):
        merged = _explained_by_paragraph_mark_merge(original, i, edited, edited[j], report)
        if merged:
            for consumed in original[i : i + merged]:
                _check_revision_identity(consumed, edited[j], report)
            i += merged
            j += 1
            continue
        orig_p = original[i]
        edit_p = edited[j]
        if orig_p.reject_text == edit_p.reject_text:
            _check_revision_identity(orig_p, edit_p, report)
            _check_inline_objects(orig_p, edit_p, report, context)
            if (
                orig_p.accept_text != edit_p.accept_text
                and not _struck_paragraph_with_inserted_mark(orig_p, edit_p)
            ):
                report.tracked_paragraphs.append(edit_p.location)
            i += 1
            j += 1
            continue
        if orig_p.reject_text.strip() == edit_p.reject_text.strip() and not _agent_inserted_paragraph(edit_p, context.author if context else None):
            # Whitespace changed outside markup. Report it here and stay
            # aligned: one stray space must not desynchronise the whole story.
            # A paragraph the agent inserted has no baseline to compare and is
            # handled by the inserted-paragraph rule below.
            _check_revision_identity(orig_p, edit_p, report)
            _check_inline_objects(orig_p, edit_p, report, context)
            report.failures.append(_untracked_rewrite(orig_p, edit_p))
            i += 1
            j += 1
            continue
        if _explained_by_accepts(orig_p, edit_p):
            i += 1
            j += 1
            continue
        if _tracked_inserted_paragraph(edit_p):
            # A paragraph that exists only as a tracked insertion has no
            # counterpart in the original: consume it here. Its empty baseline
            # must not pair with an empty original paragraph further down, which
            # read as "this paragraph deleted, the next one rewritten".
            if edit_p.accept_text.strip():
                report.tracked_paragraphs.append(edit_p.location)
            j += 1
            continue
        if i + 1 < len(original) and original[i + 1].reject_text == edit_p.reject_text:
            if orig_p.reject_text.strip():
                report.failures.append(_silent_remove(orig_p))
            i += 1
            continue
        # Skip any run of inserted paragraphs (empty baseline). One look-ahead
        # is not enough for a multi-paragraph clause reinsertion mid-story;
        # the trailing-loop rule is the model.
        if not edit_p.reject_text.strip() and j + 1 < len(edited):
            if edit_p.accept_text.strip():
                report.tracked_paragraphs.append(edit_p.location)
            j += 1
            continue
        if j + 1 < len(edited) and orig_p.reject_text == edited[j + 1].reject_text:
            if edit_p.reject_text.strip():
                report.failures.append(_silent_add(edit_p))
            elif edit_p.accept_text.strip():
                report.tracked_paragraphs.append(edit_p.location)
            j += 1
            continue
        report.failures.append(_untracked_rewrite(orig_p, edit_p))
        i += 1
        j += 1

    while i < len(original):
        if original[i].reject_text.strip():
            report.failures.append(_silent_remove(original[i]))
        i += 1
    while j < len(edited):
        if edited[j].reject_text.strip():
            report.failures.append(_silent_add(edited[j]))
        elif edited[j].accept_text.strip():
            report.tracked_paragraphs.append(edited[j].location)
        j += 1


def _struck_paragraph_with_inserted_mark(
    original: ParagraphView,
    edited: ParagraphView,
) -> bool:
    """Do not report a separate note for striking a counterparty-created split.

    The new tracked deletion is the response to the existing inserted paragraph
    mark; verify still checks its identity, author, and reject-all baseline.
    """
    mark = paragraph_mark_revision(original.element)
    return bool(mark and mark[0] == "ins" and not edited.accept_text)


def _explained_by_paragraph_mark_merge(
    original: list[ParagraphView],
    start: int,
    edited: list[ParagraphView],
    edit_p: ParagraphView,
    report: VerifyReport,
) -> int:
    """Return how many original paragraphs were joined by resolving a paragraph mark."""
    if start + 1 >= len(original) or not original[start].reject_text:
        return 0
    edit_ids = _story_revision_ids(edited)
    combined = original[start].reject_text
    notes: list[tuple[str, ParagraphView]] = []
    consumed = 1
    while start + consumed < len(original):
        head = original[start + consumed - 1]
        found = paragraph_mark_revision(head.element)
        if found is None:
            return 0
        kind, rev_id = found
        if rev_id and rev_id in edit_ids:
            return 0
        # Word may renumber the mark; a still-present mark of the same kind
        # is not a merge.
        edit_mark = paragraph_mark_revision(edit_p.element)
        if edit_mark and edit_mark[0] == kind:
            return 0
        combined += original[start + consumed].reject_text
        consumed += 1
        notes.append(("accepted" if kind == "del" else "rejected", head))
        if combined == edit_p.reject_text:
            for action, para in notes:
                if action == "accepted":
                    report.accepted_revisions.append(
                        f"accepted deleted paragraph mark in {para.location}"
                    )
                else:
                    report.rejected_revisions.append(
                        f"rejected inserted paragraph mark in {para.location}"
                    )
            return consumed
        if not edit_p.reject_text.startswith(combined):
            return 0
    return 0


def _story_revision_ids(paragraphs: list[ParagraphView]) -> set[str]:
    ids: set[str] = set()
    for para in paragraphs:
        for rev in para.revisions:
            if rev.rev_id:
                ids.add(rev.rev_id)
        found = paragraph_mark_revision(para.element)
        if found and found[1]:
            ids.add(found[1])
    return ids


def _revision_key(rev: object) -> tuple[str, str, str, str, str, str]:
    return (
        getattr(rev, "kind", ""),
        getattr(rev, "rev_id", ""),
        getattr(rev, "author", ""),
        getattr(rev, "date", ""),
        getattr(rev, "text", ""),
        getattr(rev, "location", ""),
    )


def _paragraph_baselines(path: str | Path) -> dict[tuple[str, int], str]:
    from redline_guard.apply import list_paragraphs

    return {(para.story, para.index): para.reject_text for para in list_paragraphs(path)}


def _group_revisions(
    revs: list, baselines: dict[tuple[str, int], str] | None = None
) -> dict[tuple, list]:
    groups: dict[tuple, list] = {}
    for rev in revs:
        if baselines is None:
            key: tuple = (rev.story, rev.paragraph)
        else:
            key = (rev.story, baselines.get((rev.story, rev.paragraph), ""))
        groups.setdefault(key, []).append(rev)
    return groups


def _content_key(rev: object) -> tuple[str, str, str]:
    return (getattr(rev, "kind", ""), getattr(rev, "author", ""), getattr(rev, "date", ""))


def _recognize_revisions(orig_revs: list, edit_revs: list) -> tuple[list[bool], list[bool], list[tuple]]:
    """Match revisions by concatenated text of same kind, author, and date.

    Word may renumber ids, split one revision, or merge adjacent same-author
    pieces. Report a mutation only when the concatenations differ. Empty
    concatenations match only when both sides still have pieces.
    """
    orig_used = [False] * len(orig_revs)
    edit_used = [False] * len(edit_revs)
    mutated: list[tuple] = []
    keys: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for rev in list(orig_revs) + list(edit_revs):
        key = _content_key(rev)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    for key in keys:
        orig_idxs = [i for i, rev in enumerate(orig_revs) if _content_key(rev) == key]
        edit_idxs = [i for i, rev in enumerate(edit_revs) if _content_key(rev) == key]
        orig_text = "".join(orig_revs[i].text for i in orig_idxs)
        edit_text = "".join(edit_revs[i].text for i in edit_idxs)
        if orig_text == edit_text and bool(orig_idxs) == bool(edit_idxs):
            for i in orig_idxs:
                orig_used[i] = True
            for i in edit_idxs:
                edit_used[i] = True
            continue
        if orig_text and edit_text and orig_text != edit_text:
            mutated.append((orig_revs[orig_idxs[0]], edit_text))
    return orig_used, edit_used, mutated


def _recognized_original_ids(
    orig_revs: list, edit_revs: list, original: str | Path, edited: str | Path
) -> set[str]:
    recognized: set[str] = set()
    orig_groups = _group_revisions(orig_revs, _paragraph_baselines(original))
    edit_groups = _group_revisions(edit_revs, _paragraph_baselines(edited))
    for key, origs in orig_groups.items():
        orig_used, _, _ = _recognize_revisions(origs, edit_groups.get(key, []))
        for used, rev in zip(orig_used, origs):
            if used and rev.rev_id:
                recognized.add(rev.rev_id)
    return recognized


def _recognized_edit_keys(
    orig_revs: list, edit_revs: list, original: str | Path, edited: str | Path
) -> set[tuple[str, str, str, str, str, str]]:
    used: set[tuple[str, str, str, str, str, str]] = set()
    orig_groups = _group_revisions(orig_revs, _paragraph_baselines(original))
    edit_groups = _group_revisions(edit_revs, _paragraph_baselines(edited))
    for key, origs in orig_groups.items():
        _, edit_used, _ = _recognize_revisions(origs, edit_groups.get(key, []))
        for marked, rev in zip(edit_used, edit_groups.get(key, [])):
            if marked:
                used.add(_revision_key(rev))
    return used


def _check_revision_identity(original: ParagraphView, edited: ParagraphView, report: VerifyReport) -> None:
    """Same reject-all text can still hide a rewrite or silent reject of existing markup."""
    _, _, mutated = _recognize_revisions(original.revisions, edited.revisions)
    reported: set[str] = set()
    for orig_rev, after in mutated:
        reported.add(orig_rev.rev_id)
        report.failures.append(
            Failure(
                location=edited.location,
                story=edited.story,
                paragraph=edited.index,
                message=(
                    f"In {edited.location} you rewrote existing tracked {orig_rev.kind} "
                    f"[{orig_rev.rev_id}] from {orig_rev.text!r} to {after!r}."
                ),
                baseline_excerpt=_excerpt(orig_rev.text),
                edited_excerpt=_excerpt(after),
                untracked_change=UntrackedHunk(before=orig_rev.text, after=after),
                kind="mutated_revision",
            )
        )
    # Compare attribution and placement independently of revision IDs: Word
    # legitimately renumbers and splits/merges revisions on save.
    if original.reject_text == edited.reject_text:
        before = _positioned_revision_text(original)
        after = _positioned_revision_text(edited)
        for key, positions in before.items():
            actual = after.get(key)
            if actual == positions:
                continue
            # A vanished revision is diagnosed by the package-level check.
            # A same-ID attribution change is diagnosed below.
            if actual is None:
                continue
            if any(r.rev_id in reported and _content_key(r) == key for r in original.revisions):
                continue
            report.failures.append(Failure(
                location=edited.location, story=edited.story, paragraph=edited.index,
                kind="mutated_revision", message=f"In {edited.location} an existing tracked change moved or changed.",
                baseline_excerpt="".join(ch for _, ch in positions),
                edited_excerpt="".join(ch for _, ch in actual),
            ))
    edit_by_id = {rev.rev_id: rev for rev in edited.revisions if rev.rev_id}
    for rev in original.revisions:
        counterpart = edit_by_id.get(rev.rev_id)
        if counterpart is not None and (rev.author, rev.date) != (counterpart.author, counterpart.date):
            report.failures.append(Failure(
                location=edited.location, story=edited.story, paragraph=edited.index,
                kind="mutated_revision", message=f"In {edited.location} author or date of revision [{rev.rev_id}] changed.",
                baseline_excerpt=f"{rev.author} {rev.date}", edited_excerpt=f"{counterpart.author} {counterpart.date}",
            ))


_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _check_text_box_fallbacks(orig_story, edit_story, report: VerifyReport) -> None:
    """The mc:Fallback copy of a text box is not a listed paragraph; check it here.

    Word keeps both copies identical, so the Fallback paragraph must read as
    its listed mc:Choice twin does with changes rejected and with changes
    accepted (the twin itself is compared to the original like any paragraph);
    anything else is an untracked change reported on the Choice paragraph's
    number. A box added or removed shows up as its listed paragraphs.
    """
    from redline_guard.ooxml import paragraph_texts

    def boxes(story):
        found = []
        for alternate in story.root.iter(f"{{{_MC_NS}}}AlternateContent"):
            choice = alternate.find(f"{{{_MC_NS}}}Choice")
            fallback = alternate.find(f"{{{_MC_NS}}}Fallback")
            if choice is None or fallback is None:
                continue
            found.append((list(choice.iter(q("p"))), list(fallback.iter(q("p")))))
        return found

    before, after = boxes(orig_story), boxes(edit_story)
    if len(before) != len(after):
        return
    by_element = {para.element: para for para in edit_story.paragraphs}
    for (_orig_choice, orig_fallback), (edit_choice, edit_fallback) in zip(before, after):
        if len(edit_choice) != len(edit_fallback):
            listed = next((by_element[p] for p in edit_choice if p in by_element), None)
            if listed is not None:
                report.failures.append(Failure(
                    location=listed.location, story=listed.story, paragraph=listed.index,
                    kind="untracked_edit", message=f"In {listed.location} the text box's fallback copy has a different number of paragraphs.",
                    baseline_excerpt="", edited_excerpt="",
                ))
            continue
        for edit_p, choice_p in zip(edit_fallback, edit_choice):
            listed = by_element.get(choice_p)
            if listed is None:
                continue
            edit_reject, edit_accept, _ = paragraph_texts(edit_p)
            if edit_reject == listed.reject_text and edit_accept == listed.accept_text:
                continue
            report.failures.append(Failure(
                location=listed.location, story=listed.story, paragraph=listed.index,
                kind="untracked_edit",
                message=f"In {listed.location} the text box's fallback copy does not match the edit (reads {edit_accept!r}).",
                baseline_excerpt=listed.accept_text, edited_excerpt=edit_accept,
                untracked_change=UntrackedHunk(before=listed.accept_text, after=edit_accept),
            ))


def _positioned_revision_text(para: ParagraphView) -> dict[tuple, list[tuple[int, str]]]:
    offsets = revision_reject_offsets(para.element)
    result: dict[tuple, list[tuple[int, str]]] = {}
    for rev in para.revisions:
        start = offsets.get(rev.rev_id, 0)
        positions = result.setdefault(_content_key(rev), [])
        positions.extend((start + (i if rev.kind == "del" else 0), ch) for i, ch in enumerate(rev.text))
    return result


def _explained_by_accepts(
    original: ParagraphView, edited: ParagraphView
) -> bool:
    """An accept of an existing ins/del changes reject-all; that is intentional."""
    edit_ids = {rev.rev_id for rev in edited.revisions}
    vanished = [rev for rev in original.revisions if rev.rev_id and rev.rev_id not in edit_ids]
    if not vanished:
        return False
    expected_orig = original.reject_text
    expected_edit = edited.reject_text
    for rev in vanished:
        if rev.kind == "ins" and rev.text and rev.text in expected_edit and rev.text not in original.reject_text:
            stripped = _strip_once(expected_edit, rev.text)
            if stripped is None:
                return False
            expected_edit = stripped
        elif rev.kind == "del" and rev.text and rev.text in expected_orig and rev.text not in edited.reject_text:
            stripped = _strip_once(expected_orig, rev.text)
            if stripped is None:
                return False
            expected_orig = stripped
        else:
            # Rejected markup does not change reject-all; ignore here.
            continue
    return expected_orig == expected_edit


def _strip_once(text: str, part: str) -> str | None:
    idx = text.find(part)
    if idx < 0:
        return None
    return text[:idx] + text[idx + len(part) :]


def _untracked_rewrite(original: ParagraphView, edited: ParagraphView) -> Failure:
    hunk = _first_hunk(original.reject_text, edited.reject_text)
    detail = ""
    if hunk:
        detail = f" Untracked change: {hunk.before!r} → {hunk.after!r}."
    message = (
        f"In {edited.location} you edited and it's not part of the redline/tracked.{detail}"
    )
    return Failure(
        location=edited.location,
        story=edited.story,
        paragraph=edited.index,
        message=message,
        baseline_excerpt=_excerpt(original.reject_text),
        edited_excerpt=_excerpt(edited.reject_text),
        untracked_change=hunk,
        kind="untracked_edit",
    )


def _silent_add(para: ParagraphView) -> Failure:
    return Failure(
        location=para.location,
        story=para.story,
        paragraph=para.index,
        message=(
            f"In {para.location} you added a paragraph and it's not part of the redline/tracked."
        ),
        baseline_excerpt="",
        edited_excerpt=_excerpt(para.reject_text),
        untracked_change=UntrackedHunk(before="", after=para.reject_text),
        kind="untracked_paragraph_add",
    )


def _silent_remove(para: ParagraphView) -> Failure:
    return Failure(
        location=para.location,
        story=para.story,
        paragraph=para.index,
        message=(
            f"In {para.location} you deleted a paragraph and it's not part of the redline/tracked."
        ),
        baseline_excerpt=_excerpt(para.reject_text),
        edited_excerpt="",
        untracked_change=UntrackedHunk(before=para.reject_text, after=""),
        kind="untracked_paragraph_delete",
    )


def _first_hunk(before: str, after: str) -> UntrackedHunk | None:
    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    started = False
    start_i = start_j = end_i = end_j = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" and not started:
            continue
        # Keep 1–2 character matches inside the hunk so "12" → "24" stays one change.
        if tag == "equal" and started and (i2 - i1) >= 3:
            break
        if not started:
            started = True
            start_i, start_j = i1, j1
        end_i, end_j = i2, j2
    if not started:
        return None
    return UntrackedHunk(before=before[start_i:end_i], after=after[start_j:end_j])


def _excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


# ---------------------------------------------------------------- inline objects


R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass
class InlineContext:
    author: "str | TrustedAuthors"
    original_rels: dict[str, str]
    edited_rels: dict[str, str]


def _rels_targets(files: dict[str, bytes], part_name: str) -> dict[str, str]:
    """Relationship id -> target for a story part, so hyperlinks compare by target."""
    directory, _, base = part_name.rpartition("/")
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    data = files.get(rels_name)
    if not data:
        return {}
    from redline_guard.ooxml import parse_xml

    targets: dict[str, str] = {}
    for rel in parse_xml(data):
        rid = rel.get("Id")
        if rid:
            targets[rid] = rel.get("Target", "")
    return targets


def _minute(date: str) -> str:
    return (date or "")[:16]


def _inline_tokens(paragraph: ET.Element, author: "str | TrustedAuthors", rels: dict[str, str]) -> list[tuple]:
    """Content that is not text but changes what the paragraph says or links to.

    Hyperlink targets, field instructions, footnote and endnote references,
    pictures and objects, and symbol characters. Content inside the agent's own
    tracked insertions is new and is not compared. Content inside the agent's
    own tracked deletions is still counted: an object struck under our name,
    also when our deletion is nested in the counterparty's insertion, is
    deleted with markup, not removed.
    """
    from redline_guard.ooxml import INS_TAGS

    authors = trusted_authors(author)
    tokens: list[tuple] = []
    instructions: list[str] = []
    # Characters of the original reading seen so far, so a moved object is a
    # change (1.2.2). Text inside anyone's insertion is not in the original
    # reading, so a change to it does not shift the objects after it.
    offset = [0]

    def walk(el: ET.Element, in_ins: bool = False) -> None:
        for child in el:
            tag = child.tag
            if tag in INS_TAGS and child.get(w_attr("author"), "") in authors:
                continue
            local = tag.rsplit("}", 1)[-1]
            if tag in {q("t"), q("delText")}:
                if not in_ins:
                    offset[0] += len(child.text or "")
                continue
            if tag in INS_TAGS:
                walk(child, True)
                continue
            if tag == q("hyperlink"):
                rid = child.get(f"{{{R_NS}}}id")
                target = rels.get(rid, rid) if rid else "#" + (child.get(w_attr("anchor")) or "")
                tokens.append(("hyperlink", target, offset[0]))
            elif tag == q("fldSimple"):
                instructions.append(" ".join((child.get(w_attr("instr")) or "").split()))
            elif tag == q("instrText"):
                instructions.append((child.text or ""))
                continue
            elif tag in {q("footnoteReference"), q("endnoteReference")}:
                tokens.append((local, child.get(w_attr("id"), ""), offset[0]))
                continue
            elif tag in {q("drawing"), q("pict"), q("object")}:
                tokens.append(("object", local, offset[0]))
                continue
            elif tag == q("sym"):
                tokens.append(("sym", child.get(w_attr("font"), ""), child.get(w_attr("char"), ""), offset[0]))
                offset[0] += 0 if in_ins else 1
                continue
            elif tag in {q("noBreakHyphen"), q("softHyphen")}:
                tokens.append((local, offset[0]))
                offset[0] += 0 if in_ins else 1
                continue
            walk(child, in_ins)

    walk(paragraph)
    if instructions:
        tokens.append(("fields", " ".join("".join(instructions).split()), -1))
    return tokens


def _describe_token(token: tuple) -> str:
    kind, *rest = token
    detail = " ".join(str(x) for x in rest[:-1])
    return f"{kind} {detail!r}" if detail else kind


def _check_inline_objects(
    original: ParagraphView,
    edited: ParagraphView,
    report: VerifyReport,
    context: "InlineContext | None",
) -> None:
    if context is None:
        return
    # Paragraphs align by baseline text. Two empty-baseline paragraphs (a
    # picture-only paragraph and an inserted one, say) may be paired without
    # being the same paragraph; compare them only when their wording agrees.
    if not original.reject_text.strip() and original.accept_text.strip() != edited.accept_text.strip():
        return
    before = _inline_tokens(original.element, context.author, context.original_rels)
    after = _inline_tokens(edited.element, context.author, context.edited_rels)
    if before == after:
        return
    from collections import Counter

    missing = list((Counter(before) - Counter(after)).elements())
    added = list((Counter(after) - Counter(before)).elements())
    identity = lambda t: t[:-1]  # the token without its position
    if missing and added and Counter(map(identity, missing)) == Counter(map(identity, added)):
        detail, what = missing[0], "moved"
    elif missing and not added:
        detail, what = missing[0], "removed"
    elif added and not missing:
        detail, what = added[0], "added" if Counter(map(identity, before))[identity(added[0])] == 0 else "duplicated"
    elif missing:
        detail, what = missing[0], "removed"
    else:
        detail, what = (added or after or before)[0], "changed"
    report.failures.append(Failure(
        location=edited.location, story=edited.story, paragraph=edited.index,
        kind="untracked_object_change",
        message=(
            f"In {edited.location} a {_describe_token(detail)} was {what} "
            "without markup (hyperlink target, field code, footnote reference, picture, or symbol)."
        ),
        baseline_excerpt=", ".join(_describe_token(t) for t in before)[:180],
        edited_excerpt=", ".join(_describe_token(t) for t in after)[:180],
    ))


def _check_tracked_rejections(package, logged: list[dict], author: "str | TrustedAuthors", report: VerifyReport) -> None:
    """A rejection logged as a tracked change must show our reversal in the document.

    Their insertion must carry our deletion of the rejected text, where a part
    another author had already struck inside it counts as struck; their deletion
    must be followed by our insertion of it; a mark or row must carry our
    counter-marker. Word may renumber ids, so a revision is found by id first
    and by kind, author, and date otherwise.
    """
    from redline_guard.ooxml import DEL_TAGS, INS_TAGS

    authors = trusted_authors(author)
    entries = [e for e in logged if e.get("tracked") and e.get("action") == "reject"]
    if not entries:
        return
    by_id: dict[str, tuple] = {}
    by_content: dict[tuple, list[tuple]] = {}
    parents_of: dict = {}
    for story in package.stories:
        parents_of[story.name] = parent_map_from(story.root)
        for el in story.root.iter():
            if el.tag not in INS_TAGS | DEL_TAGS:
                continue
            kind = "ins" if el.tag in INS_TAGS else "del"
            by_id.setdefault(el.get(w_attr("id"), ""), (el, story))
            by_content.setdefault((kind, el.get(w_attr("author"), ""), el.get(w_attr("date"), "")), []).append((el, story))
    for entry in entries:
        rid = str(entry.get("id", ""))
        kind = str(entry.get("kind", ""))
        want = str(entry.get("find") or entry.get("text") or "")
        found = [by_id[rid]] if rid in by_id else by_content.get((kind, str(entry.get("author", "")), str(entry.get("date", ""))), [])
        if not found:
            continue  # its absence is reported by the vanished-revision check
        if any(_tracked_reversal_present(el, kind, want, authors, parents_of[story.name]) for el, story in found):
            continue
        report.failures.append(Failure(
            location=str(entry.get("location", "")), story="", paragraph=0, kind="log_mismatch",
            message=(
                f"In {entry.get('location') or 'the document'} {kind} [{rid}] is logged as rejected by a tracked "
                f"change, but the document shows no reversal of it by {authors.describe()}."
            ),
            baseline_excerpt=_excerpt(want), edited_excerpt="",
        ))


def _tracked_reversal_present(el, kind: str, want: str, author: "str | TrustedAuthors", parents: dict) -> bool:
    from redline_guard.ooxml import DEL_TAGS, INS_TAGS, run_text

    authors = trusted_authors(author)

    def by_author(node) -> bool:
        return node.get(w_attr("author"), "") in authors

    holder = parents.get(el)
    if holder is not None and holder.tag == q("trPr"):
        row = parents.get(holder)
        if kind == "ins":
            return any(n.tag in DEL_TAGS and by_author(n) for n in holder)
        table = parents.get(row)
        if table is None:
            return False
        rows = [child for child in table if child.tag == q("tr")]
        index = rows.index(row)
        if index + 1 >= len(rows):
            return False
        following = rows[index + 1].find(q("trPr"))
        return following is not None and any(n.tag in INS_TAGS and by_author(n) for n in following)
    if holder is not None and holder.tag == q("rPr") and parents.get(holder) is not None and parents[holder].tag == q("pPr"):
        paragraph = parents.get(parents[holder])
        if kind == "ins":
            return any(n.tag in DEL_TAGS and by_author(n) for n in holder)
        container = parents.get(paragraph)
        if container is None:
            return False
        siblings = list(container)
        index = siblings.index(paragraph)
        previous = next((s for s in reversed(siblings[:index]) if s.tag == q("p")), None)
        if previous is None:
            return False
        rpr = previous.find(f"{q('pPr')}/{q('rPr')}")
        return rpr is not None and any(n.tag in INS_TAGS and by_author(n) for n in rpr)
    if kind == "ins":
        # Text inside any deletion nested in their insertion is struck: ours
        # covers what still stood, and a part another author had already
        # deleted needs no second strike. What nobody struck stands.
        struck: list[str] = []

        def visit(node, inside: bool) -> None:
            for child in node:
                if child.tag in DEL_TAGS:
                    visit(child, True)
                elif child.tag == q("r"):
                    if inside:
                        struck.append(run_text(child))
                else:
                    visit(child, inside)

        visit(el, False)
        return want in "".join(struck)
    paragraph = el
    while paragraph is not None and paragraph.tag != q("p"):
        paragraph = parents.get(paragraph)
    if paragraph is None:
        return False
    restored: list[str] = []
    for node in paragraph.iter():
        if node.tag in INS_TAGS and by_author(node):
            restored.append("".join(run_text(run) for run in node.iter(q("r"))))
    return want in "".join(restored)


def _check_hidden_insertions(package, author: "str | TrustedAuthors", report: VerifyReport) -> None:
    """Text the agent inserted must be visible: no hidden or web-hidden runs."""
    from redline_guard.ooxml import INS_TAGS

    authors = trusted_authors(author)
    for story in package.stories:
        for para in story.paragraphs:
            for ins in para.element.iter():
                if ins.tag not in INS_TAGS or ins.get(w_attr("author"), "") not in authors:
                    continue
                for run in ins.iter(q("r")):
                    rpr = run.find(q("rPr"))
                    if rpr is None:
                        continue
                    hidden = rpr.find(q("vanish")) is not None or rpr.find(q("webHidden")) is not None
                    if hidden:
                        text = "".join(t.text or "" for t in run.iter(q("t")))
                        report.failures.append(Failure(
                            location=para.location, story=para.story, paragraph=para.index,
                            kind="hidden_insertion",
                            message=f"In {para.location} inserted text {_excerpt(text)!r} is formatted as hidden.",
                            baseline_excerpt="", edited_excerpt=_excerpt(text),
                        ))
                        break


def _check_fixed_height_rows(package, author: "str | TrustedAuthors", report: VerifyReport) -> None:
    """Warn when our edit lands in a table row that cannot grow.

    A row carrying ``<w:trHeight w:hRule="exact"/>`` keeps that height whatever it contains: Word
    and LibreOffice both clip the overflow rather than growing the row, so text can be present in
    the file, correctly tracked, and simply absent from the page. Confirmed in Word on a
    governing-law table in an MSA converted from PDF.

    This is a warning, not a failure. The markup is valid and the edit may well fit; only the
    render can say. Documents converted from PDF carry these rows in bulk, so failing on them
    would block legitimate work. Deletions warn too: a tracked deletion still shows struck
    through until it is accepted, so it takes up space in the markup view like any other text.
    """
    from redline_guard.ooxml import INS_TAGS, DEL_TAGS

    authors = trusted_authors(author)
    revision_tags = INS_TAGS | DEL_TAGS
    for story in package.stories:
        by_element = {id(para.element): para for para in story.paragraphs}
        for row in story.root.iter(q("tr")):
            height = row.find(f"{q('trPr')}/{q('trHeight')}")
            if height is None or height.get(w_attr("hRule")) != "exact":
                continue
            touched = [
                by_element[id(para)]
                for para in row.iter(q("p"))
                if id(para) in by_element
                and any(el.tag in revision_tags and el.get(w_attr("author"), "") in authors
                        for el in para.iter())
            ]
            if not touched:
                continue
            where = ", ".join(para.location for para in touched[:3])
            if len(touched) > 3:
                where += f" and {len(touched) - 3} more"
            report.warnings.append(
                f"{where}: this table row has a fixed height (w:trHeight w:hRule=\"exact\", "
                f"{height.get(w_attr('val'), '?')} twips), so Word will clip anything that no longer fits "
                "instead of growing the row. Check the rendered page, or keep the replacement no longer "
                "than the text it replaces."
            )


def _note_separator_texts(package) -> list[tuple[str, str, str]]:
    from redline_guard.ooxml import NOTE_SEPARATOR_TYPES

    found: list[tuple[str, str, str]] = []
    for part in ("word/footnotes.xml", "word/endnotes.xml"):
        data = package.files.get(part)
        if not data:
            continue
        from redline_guard.ooxml import parse_xml

        root = parse_xml(data)
        for note in root.iter():
            if note.tag not in {q("footnote"), q("endnote")} or note.get(w_attr("type")) not in NOTE_SEPARATOR_TYPES:
                continue
            text = "".join(
                (el.text or "") if el.tag in {q("t"), q("delText")} else f"<{el.tag.rsplit('}', 1)[-1]}>"
                for el in note.iter()
                if el.tag in {q("t"), q("delText"), q("separator"), q("continuationSeparator"), q("br"), q("tab")}
            )
            found.append((part, note.get(w_attr("type"), ""), text))
    return found


def _check_note_separators(expected, edited, report: VerifyReport) -> None:
    """Word's separator notes are not document text; any change there is untracked."""
    before = _note_separator_texts(expected)
    after = _note_separator_texts(edited)
    if before == after:
        return
    part = (after or before)[0][0]
    story = "footnotes" if "footnotes" in part else "endnotes"
    report.failures.append(Failure(
        location=f"{story} separator", story=story, paragraph=0,
        kind="untracked_edit",
        message=f"The {story} separator notes changed outside markup.",
        baseline_excerpt=str(before)[:180], edited_excerpt=str(after)[:180],
    ))


def _comment_anchor_baselines(path: str | Path) -> dict[str, tuple[str, str]]:
    """Comment id -> (story, baseline text of the paragraph it anchors to)."""
    package = load_docx(path)
    anchors: dict[str, tuple[str, str]] = {}
    for story in package.stories:
        for para in story.paragraphs:
            for el in para.element.iter():
                if el.tag in {q("commentRangeStart"), q("commentReference")}:
                    cid = el.get(w_attr("id"))
                    if cid and cid not in anchors:
                        anchors[cid] = (story.name, para.reject_text)
    return anchors


def _agent_inserted_paragraph(para: ParagraphView, author: "str | Iterable[str] | None") -> bool:
    """A paragraph with no baseline whose mark or every text run is the agent's insertion."""
    from redline_guard.ooxml import INS_TAGS

    if para.reject_text.strip():
        return False
    names = None if author is None else trusted_authors(author)
    mark = para.element.find(f"{q('pPr')}/{q('rPr')}/{q('ins')}")
    if mark is not None:
        return names is None or mark.get(w_attr("author"), "") in names
    parents = {child: parent for parent in para.element.iter() for child in parent}
    runs = [run for run in para.element.iter(q("r")) if any(t.tag in {q("t"), q("delText")} for t in run)]
    if not runs:
        return True
    for run in runs:
        node = parents.get(run)
        while node is not None and not (node.tag in INS_TAGS and (names is None or node.get(w_attr("author"), "") in names)):
            node = parents.get(node)
        if node is None:
            return False
    return True


def _tracked_inserted_paragraph(para: ParagraphView) -> bool:
    """A paragraph that exists only as a tracked insertion, by anyone.

    Its mark is an inserted paragraph mark, or every text run sits inside an
    insertion. An empty paragraph with no markup is not one: it may be the
    original's own empty paragraph. Whose insertion it is, is checked
    separately by the authorship rule.
    """
    from redline_guard.ooxml import INS_TAGS

    if para.reject_text.strip():
        return False
    mark = paragraph_mark_revision(para.element)
    if mark is not None and mark[0] == "ins":
        return True
    parents = {child: parent for parent in para.element.iter() for child in parent}
    runs = [run for run in para.element.iter(q("r")) if any(t.tag in {q("t"), q("delText")} for t in run)]
    if not runs:
        return False
    for run in runs:
        node = parents.get(run)
        while node is not None and node.tag not in INS_TAGS:
            node = parents.get(node)
        if node is None:
            return False
    return True
