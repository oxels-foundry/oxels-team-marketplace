"""CLI for listing paragraphs, applying tracked edits, and verifying them."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

from redline_guard.apply import ApplyError, apply_edits, format_paragraph_list, list_paragraphs
from redline_guard.comments import CommentError, add_comments, format_comments, list_comments, scrub_internal_notes, set_comment_status
from redline_guard.resolution_log import DEFAULT_AUTHOR, require_author
from redline_guard.resolve import ResolveError, clean_docx, format_revisions, list_revisions, resolve_revisions
from redline_guard.verify import format_report, verify_docx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="redline_guard",
        description=(
            "Keep agent edits to a user-supplied DOCX as Word tracked changes, "
            "and fail with a paragraph-level message when an edit is silent."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List 1-based paragraph indexes the other commands use.")
    list_p.add_argument("input")
    list_p.add_argument("--story", help="Limit to one story (body, header, footer, footnotes).")
    list_p.add_argument("--json", action="store_true")

    tables_p = sub.add_parser("tables", help="List table/row indexes and cell text for row edits.")
    tables_p.add_argument("input")
    tables_p.add_argument("--story")
    tables_p.add_argument("--json", action="store_true")

    apply_p = sub.add_parser("apply", help="Apply find/replace/insert/delete as tracked changes.")
    apply_p.add_argument("input")
    apply_p.add_argument("output")
    apply_p.add_argument("--edits", required=True, help="JSON file of edits, or a JSON list string.")
    apply_p.add_argument("--author", default=DEFAULT_AUTHOR)

    verify_p = sub.add_parser("verify", help="Fail if any edit vs the original is not tracked.")
    verify_p.add_argument("original")
    verify_p.add_argument("edited")
    verify_p.add_argument("--json", action="store_true")
    verify_p.add_argument(
        "--resolved",
        action="append",
        default=[],
        help="Resolution log JSON (may be repeated). Auto-loads <edited>.resolved.json.",
    )
    verify_p.add_argument(
        "--author",
        action="append",
        default=None,
        help="Trusted author name (may be repeated for a file touched by several of our agents). Default: REDLINE_AUTHOR.",
    )
    verify_p.add_argument(
        "--prior-round",
        action="store_true",
        help="The original is the counterparty's return of our earlier draft, so our name already appears in it.",
    )
    verify_p.add_argument(
        "--formatting",
        action="store_true",
        help="Also fail on untracked formatting differences of original content.",
    )

    validate_p = sub.add_parser("validate", help="Check OPC, revision, comment, and optional schema structure.")
    validate_p.add_argument("docx")
    validate_p.add_argument("--original")
    validate_p.add_argument("--schema", choices=("auto", "required", "off"), default="auto")
    validate_p.add_argument("--json", action="store_true")

    render_p = sub.add_parser("render", help="Render markup and final page images with LibreOffice.")
    render_p.add_argument("docx")
    render_p.add_argument("out_dir")
    render_p.add_argument("--original")
    render_p.add_argument("--json", action="store_true")

    finalize_p = sub.add_parser("finalize", help="Scrub a draft and run the send-file gate.")
    finalize_p.add_argument("original")
    finalize_p.add_argument("draft")
    finalize_p.add_argument("send")
    finalize_p.add_argument("--pages")
    finalize_p.add_argument("--author", action="append", default=None, help="Trusted author name (may be repeated). Default: REDLINE_AUTHOR.")
    finalize_p.add_argument("--resolved", action="append", default=[])
    finalize_p.add_argument("--prior-round", action="store_true", help="The original is the counterparty's return of our earlier draft.")
    finalize_p.add_argument("--json", action="store_true")

    attest_p = sub.add_parser("attest", help="Record that every rendered page was inspected.")
    attest_p.add_argument("send")
    attest_p.add_argument("--pages", required=True)
    attest_p.add_argument("--by", default="")

    status_p = sub.add_parser("status", help="Print whether a send file is ready.")
    status_p.add_argument("send")

    comments_p = sub.add_parser("comments", help="List Word comments and the paragraph they sit on.")
    comments_p.add_argument("input")
    comments_p.add_argument("--json", action="store_true")

    comment_p = sub.add_parser("comment", help="Add a Word comment anchored to a paragraph.")
    comment_p.add_argument("input")
    comment_p.add_argument("output")
    comment_p.add_argument("--paragraph", type=int, help="1-based paragraph index from `list`.")
    comment_p.add_argument("--text", help="Comment body.")
    comment_p.add_argument("--find", help="Optional text in the paragraph to highlight.")
    comment_p.add_argument("--occurrence", type=int, default=1, help="1-based occurrence of --find.")
    comment_p.add_argument("--story", default="body")
    comment_p.add_argument("--author", default=DEFAULT_AUTHOR)
    comment_p.add_argument("--comments", help="JSON list of comments instead of --paragraph/--text.")
    comment_p.add_argument("--reply-to", help="Existing comment id to reply to (threaded).")
    comment_p.add_argument(
        "--internal",
        action="store_true",
        help="Mark as an internal owner note (never send; stripped by clean/scrub).",
    )

    note_p = sub.add_parser(
        "note",
        help="Add an INTERNAL reasoning note for the redline owner. Never for the customer.",
    )
    note_p.add_argument("input")
    note_p.add_argument("output")
    note_p.add_argument("--paragraph", type=int, help="1-based paragraph index from `list` (not with --reply-to).")
    note_p.add_argument("--text", required=True)
    note_p.add_argument("--find")
    note_p.add_argument("--occurrence", type=int, default=1)
    note_p.add_argument("--story", default="body")
    note_p.add_argument("--author", default=DEFAULT_AUTHOR)
    note_p.add_argument("--reply-to", help="Existing comment id to reply to; the note shares its anchor.")

    for command in ("resolve-comment", "reopen-comment"):
        cp = sub.add_parser(command, help="Resolve/reopen a comment thread, preserving its contents and recording the decision.")
        cp.add_argument("input")
        cp.add_argument("output")
        cp.add_argument("--id", required=True, help="Root or reply ID from `comments`.")
        cp.add_argument("--author", default=DEFAULT_AUTHOR)

    rev_p = sub.add_parser("revisions", help="List existing tracked insertions and deletions.")
    rev_p.add_argument("input")
    rev_p.add_argument("--json", action="store_true")

    accept_p = sub.add_parser("accept", help="Accept a tracked revision by id.")
    accept_p.add_argument("input")
    accept_p.add_argument("output")
    accept_p.add_argument("--id", required=True, help="Revision id from `revisions`.")
    accept_p.add_argument("--find", help="Resolve only this exact text within the revision.")
    accept_p.add_argument("--log", help="Resolution log path (default: <output>.resolved.json).")
    accept_p.add_argument("--author", default=DEFAULT_AUTHOR)

    reject_p = sub.add_parser(
        "reject",
        help="Reject a tracked revision by id: theirs stays pending and our reversal is a tracked change beside it.",
    )
    reject_p.add_argument("input")
    reject_p.add_argument("output")
    reject_p.add_argument("--id", required=True, help="Revision id from `revisions`.")
    reject_p.add_argument("--find", help="Resolve only this exact text within the revision.")
    reject_p.add_argument("--log", help="Resolution log path (default: <output>.resolved.json).")
    reject_p.add_argument("--author", default=DEFAULT_AUTHOR, help="Name on our reversal (default: REDLINE_AUTHOR).")
    reject_p.add_argument(
        "--untracked",
        action="store_true",
        help="Word's Reject: remove their markup and show nothing. Only on instruction.",
    )

    resolve_p = sub.add_parser("resolve", help="Accept/reject several revisions from JSON.")
    resolve_p.add_argument("input")
    resolve_p.add_argument("output")
    resolve_p.add_argument(
        "--actions",
        required=True,
        help='JSON list: [{"id":"12","action":"accept"},{"id":"34","action":"reject","untracked":true}]',
    )
    resolve_p.add_argument("--log", help="Resolution log path (default: <output>.resolved.json).")
    resolve_p.add_argument("--author", default=DEFAULT_AUTHOR)

    clean_p = sub.add_parser("clean", help="Accept all redlines into a signature copy.")
    clean_p.add_argument("input")
    clean_p.add_argument("output")
    clean_p.add_argument(
        "--keep-comments",
        action="store_true",
        help="Keep customer-facing comments. Internal notes are still removed.",
    )

    scrub_p = sub.add_parser(
        "scrub",
        help="Remove internal agent notes only. Keeps redlines and customer comments.",
    )
    scrub_p.add_argument("input")
    scrub_p.add_argument("output")

    args = parser.parse_args(argv)
    try:
        return _dispatch(args, parser)
    except FileNotFoundError as exc:
        return _fail(args, f"file not found: {exc.filename or exc}")
    except zipfile.BadZipFile as exc:
        return _fail(args, f"not a .docx package (the file is not a zip archive): {exc}")
    except OSError as exc:
        # Any other IO error while reading inputs or writing outputs.
        where = f": {exc.filename}" if getattr(exc, "filename", None) else ""
        return _fail(args, f"{exc.strerror or exc}{where}")
    except json.JSONDecodeError as exc:
        return _fail(args, f"invalid JSON: {exc}")
    except KeyError as exc:
        return _fail(args, f"unknown story or key {exc}")
    except (ApplyError, CommentError, ResolveError, ValueError) as exc:
        return _fail(args, str(exc))


def _fail(args: argparse.Namespace, message: str) -> int:
    print(f"{args.command} failed: {message}", file=sys.stderr)
    return 1


def _authors(args: argparse.Namespace):
    """The trusted author names for verify and finalize.

    One name is passed as a string, as before; several names (a repeated
    --author) as a list in the order given, duplicates dropped.  Without the
    flag the single name from REDLINE_AUTHOR applies.
    """
    names = list(dict.fromkeys(name.strip() for name in (args.author or []) if name and name.strip()))
    if not names:
        return DEFAULT_AUTHOR
    return names[0] if len(names) == 1 else names


# Commands that sign what they write, or check a signature, and so need a name.
# verify and finalize take a repeatable --author, so their effective name comes
# from _authors; the rest carry a single --author defaulting to REDLINE_AUTHOR.
_AUTHOR_COMMANDS = frozenset(
    {"apply", "comment", "note", "resolve-comment", "reopen-comment", "accept", "reject", "resolve"}
)
_AUTHOR_LIST_COMMANDS = frozenset({"verify", "finalize"})


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command in _AUTHOR_LIST_COMMANDS:
        require_author(_authors(args))
    elif args.command in _AUTHOR_COMMANDS:
        require_author(args.author)
    if args.command == "list":
        return _cmd_list(args)
    if args.command == "tables":
        from redline_guard.tables import list_tables

        records = list_tables(args.input, args.story)
        if args.json:
            print(json.dumps(records, indent=2))
        else:
            for table in records:
                for row in table["rows"]:
                    print(f"{table['story']} table {table['table']} row {row['row']}\t{' | '.join(row['cells'])}" + (f"  {row['revisions']}" if row['revisions'] else ""))
        return 0
    if args.command in {"resolve-comment", "reopen-comment"}:
        try:
            cid = set_comment_status(args.input, args.output, args.id, resolved=args.command == "resolve-comment", author=args.author)
        except CommentError as exc:
            print(f"{args.command} failed: {exc}", file=sys.stderr)
            return 1
        print(f"Comment thread [{cid}] {'resolved' if args.command == 'resolve-comment' else 'reopened'} -> {args.output}")
        return 0
    if args.command == "apply":
        return _cmd_apply(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "comments":
        return _cmd_comments(args)
    if args.command == "comment":
        return _cmd_comment(args)
    if args.command == "note":
        return _cmd_note(args)
    if args.command == "revisions":
        return _cmd_revisions(args)
    if args.command == "accept":
        return _cmd_resolve_one(args, "accept")
    if args.command == "reject":
        return _cmd_resolve_one(args, "reject")
    if args.command == "resolve":
        return _cmd_resolve(args)
    if args.command == "clean":
        return _cmd_clean(args)
    if args.command == "scrub":
        return _cmd_scrub(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "render":
        return _cmd_render(args)
    if args.command == "finalize":
        return _cmd_finalize(args)
    if args.command == "attest":
        return _cmd_attest(args)
    if args.command == "status":
        return _cmd_status(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _cmd_list(args: argparse.Namespace) -> int:
    paragraphs = list_paragraphs(args.input, story=args.story)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "location": p.location,
                        "story": p.story,
                        "paragraph": p.index,
                        "accept_text": p.accept_text,
                        "reject_text": p.reject_text,
                        "revision_count": len(p.revisions),
                        "label": p.label,
                    }
                    for p in paragraphs
                ],
                indent=2,
            )
        )
    else:
        print(format_paragraph_list(paragraphs))
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    edits = _load_edits(args.edits)
    try:
        apply_edits(args.input, args.output, edits, author=args.author)
    except ApplyError as exc:
        print(f"apply failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote tracked edits to {args.output}")
    return 0


def _refuse_reply_anchor(args: argparse.Namespace) -> None:
    """A reply shares the anchor of the comment it answers; its own anchor is refused, not ignored."""
    if args.reply_to and (args.paragraph is not None or args.find):
        raise CommentError(
            "--paragraph and --find do not apply with --reply-to; a reply shares the anchor of the "
            "comment it answers. Drop them, or drop --reply-to to anchor a new comment."
        )


def _cmd_comment(args: argparse.Namespace) -> int:
    _refuse_reply_anchor(args)
    if args.comments:
        specs = _load_edits(args.comments)
    elif args.reply_to and args.text:
        specs = [{"reply_to": args.reply_to, "text": args.text}]
    elif args.paragraph is not None and args.text:
        specs = [
            {
                "paragraph": args.paragraph,
                "text": args.text,
                "find": args.find or "",
                "occurrence": args.occurrence,
                "story": args.story,
            }
        ]
    else:
        print("comment failed: pass --paragraph and --text, --reply-to and --text, or --comments JSON.", file=sys.stderr)
        return 2
    try:
        ids = add_comments(
            args.input,
            args.output,
            specs,
            author=args.author,
            internal=getattr(args, "internal", False),
        )
    except CommentError as exc:
        print(f"comment failed: {exc}", file=sys.stderr)
        return 1
    kind = "internal note(s)" if getattr(args, "internal", False) else "comment(s)"
    print(f"Added {kind} {', '.join(ids)} to {args.output}")
    return 0


def _cmd_note(args: argparse.Namespace) -> int:
    _refuse_reply_anchor(args)
    if args.reply_to:
        specs = [{"reply_to": args.reply_to, "text": args.text, "internal": True}]
    elif args.paragraph is None:
        print("note failed: pass --paragraph and --text, or --reply-to and --text.", file=sys.stderr)
        return 2
    else:
        specs = [
            {
                "paragraph": args.paragraph,
                "text": args.text,
                "find": args.find or "",
                "occurrence": args.occurrence,
                "story": args.story,
                "internal": True,
            }
        ]
    try:
        ids = add_comments(args.input, args.output, specs, author=args.author, internal=True)
    except CommentError as exc:
        print(f"note failed: {exc}", file=sys.stderr)
        return 1
    print(f"Added INTERNAL note(s) {', '.join(ids)} to {args.output}")
    return 0


def _cmd_revisions(args: argparse.Namespace) -> int:
    revisions = list_revisions(args.input)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": r.rev_id,
                        "kind": r.kind,
                        "author": r.author,
                        "text": r.text,
                        "location": r.location,
                        "story": r.story,
                        "paragraph": r.paragraph,
                        "label": r.label,
                        "move": r.move,
                        "move_role": r.move_role,
                        "paired_with": [i for i in r.paired_with.split(", ") if i],
                    }
                    for r in revisions
                ],
                indent=2,
            )
        )
    else:
        print(format_revisions(revisions))
    return 0


def _cmd_resolve_one(args: argparse.Namespace, action: str) -> int:
    spec = {"id": args.id, "action": action}
    if args.find is not None:
        spec["find"] = args.find
    if getattr(args, "untracked", False):
        spec["untracked"] = True
    try:
        done = resolve_revisions(
            args.input,
            args.output,
            [spec],
            log_path=getattr(args, "log", None),
            author=args.author,
        )
    except ResolveError as exc:
        print(f"{action} failed: {exc}", file=sys.stderr)
        return 1
    print(f"{done[0]} -> {args.output}")
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    try:
        done = resolve_revisions(
            args.input,
            args.output,
            _load_edits(args.actions),
            log_path=getattr(args, "log", None),
            author=args.author,
        )
    except ResolveError as exc:
        print(f"resolve failed: {exc}", file=sys.stderr)
        return 1
    for line in done:
        print(line)
    print(f"Resolved {len(done)} revision(s) -> {args.output}")
    return 0


def _cmd_clean(args: argparse.Namespace) -> int:
    clean_docx(args.input, args.output, keep_comments=args.keep_comments)
    print(f"Wrote clean copy to {args.output} (internal notes removed)")
    return 0


def _cmd_scrub(args: argparse.Namespace) -> int:
    removed = scrub_internal_notes(args.input, args.output)
    print(f"Removed {removed} internal note(s) -> {args.output}")
    return 0


def _cmd_comments(args: argparse.Namespace) -> int:
    comments = list_comments(args.input)
    if args.json:
        print(json.dumps([c.to_dict() for c in comments], indent=2))
    else:
        print(format_comments(comments))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    report = verify_docx(
        args.original,
        args.edited,
        resolved=args.resolved,
        author=_authors(args),
        formatting=args.formatting,
        prior_round=args.prior_round,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    from redline_guard.structure import StructureError, validate_structure

    try:
        report = validate_structure(args.docx, original=args.original, schema=args.schema)
    except StructureError as exc:
        print(f"validate failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("OK" if report.ok else "FAIL")
        for item in report.defects:
            print(f"- {item.check} @ {item.part}: {item.message}")
        for warning in report.warnings:
            print(f"warning: {warning}")
    return 0 if report.ok else 1


def _cmd_render(args: argparse.Namespace) -> int:
    from redline_guard.render import render_docx

    report = render_docx(args.docx, args.out_dir, original=args.original)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("OK" if report.ok else "FAIL")
        for page in report.pages:
            print(f"  page {page.number}: {page.image}")
        for item in report.failures:
            print(f"- {item.kind}: {item.message}")
    return 0 if report.ok else 1


def _cmd_finalize(args: argparse.Namespace) -> int:
    from redline_guard.finalize import FinalizeError, finalize_docx

    try:
        report = finalize_docx(
            args.original,
            args.draft,
            args.send,
            pages_dir=args.pages,
            author=_authors(args),
            resolved=args.resolved or None,
            prior_round=args.prior_round,
        )
    except FinalizeError as exc:
        print(f"finalize refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.status)
        note = (report.checks.get("resolution_log") or {}).get("message")
        if note:
            print(f"note: {note}")
        # A layer that did not run is stated, not assumed to have passed: the send
        # file was gated without it.
        sdk = report.checks.get("openxml_sdk") or {}
        if not sdk.get("available") and sdk.get("message"):
            print(f"not checked: {sdk['message']}")
        for item in report.failures:
            print(f"- {_failure_line(item)}")
        if not report.ok:
            for line in _finalize_next_steps(report):
                print(line)
        if report.ok:
            for page in report.pages:
                image = page.get("image") if isinstance(page, dict) else getattr(page, "image", "")
                print(image)
    return 0 if report.ok else 1


def _failure_line(item) -> str:
    """One readable line per finalize failure: kind, where, what."""
    if not isinstance(item, dict):
        return str(item)
    kind = item.get("kind") or item.get("check") or "failure"
    where = item.get("location") or item.get("part") or ""
    message = " ".join(str(item.get("message", "")).split())
    return f"{kind}{f' @ {where}' if where else ''}: {message}"


_FIX_THE_DRAFT = (
    "fix the draft through the commands from the last file that verified, "
    "then run verify original draft --formatting until it prints OK"
)
_NEXT_STEP = {
    "dependency_missing": "install the tool named above (references/docx-tool.md, Runtime requirements)",
    "wrong_resolution_log": "put the draft's .resolved.json back beside it, or finalize the draft it belongs to",
    "untrusted_author": "use the team's name from REDLINE_AUTHOR; for round two of a negotiation pass --prior-round",
    "render_incomplete": (
        "the renderer could not show the whole document, so the pages cannot be inspected; "
        "tell commercial legal, who can check the file in Word or approve a paragraph between the table and the text box"
    ),
    "render_markup_missing": "open the page images to see what did not render (often an edit inside a field or text box), then " + _FIX_THE_DRAFT,
    "render_wording_missing": "open the page images to see what did not render (often an edit inside a field or text box), then " + _FIX_THE_DRAFT,
    "finalization_failed": "read the message above; if it names the draft, " + _FIX_THE_DRAFT,
}


def _finalize_next_steps(report) -> list[str]:
    """What the agent does after a failed finalize: fix the draft, never the send file, and run finalize again."""
    kinds: list[str] = []
    for item in report.failures:
        kind = (item.get("kind") or item.get("check") or "") if isinstance(item, dict) else ""
        if kind not in kinds:
            kinds.append(kind)
    lines = ["next:"]
    seen: set[str] = set()
    for kind in kinds:
        step = _NEXT_STEP.get(kind, _FIX_THE_DRAFT)
        if step not in seen:
            seen.add(step)
            lines.append(f"  - {step}")
    lines.append("  - then run the same finalize command again; the same send path is fine, nothing was written there")
    return lines


def _parse_pages(raw: str):
    if raw == "all":
        return "all"
    pages: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def _cmd_attest(args: argparse.Namespace) -> int:
    from redline_guard.finalize import attest_pages

    report = attest_pages(args.send, _parse_pages(args.pages), by=args.by)
    print(report.status if report.ok else (report.failures[0].get("message") if report.failures else "failed"))
    return 0 if report.ok else 1


def _cmd_status(args: argparse.Namespace) -> int:
    from redline_guard.finalize import finalize_status

    report = finalize_status(args.send)
    if report.ok and report.status == "ready":
        print("ready")
        return 0
    reason = report.failures[0].get("message") if report.failures else report.status
    print(reason)
    return 1


def _load_edits(raw: str) -> list[dict]:
    """A JSON file path, or an inline JSON list. Anything else is named for what it is."""
    path = Path(raw)
    try:
        is_dir, is_file = path.is_dir(), path.is_file()
    except (OSError, ValueError):
        is_dir = is_file = False
    if is_dir:
        raise ApplyError(f"{raw} is a directory; pass a JSON file or an inline JSON list.")
    if is_file:
        payload = json.loads(path.read_text())
    elif raw.lstrip().startswith(("[", "{")):
        payload = json.loads(raw)
    else:
        raise ApplyError(f"file not found: {raw} (pass a JSON file path or an inline JSON list)")
    if isinstance(payload, dict) and "edits" in payload:
        return payload["edits"]
    if isinstance(payload, list):
        return payload
    raise ApplyError("Edits JSON must be a list or an object with an 'edits' list.")


if __name__ == "__main__":
    raise SystemExit(main())
