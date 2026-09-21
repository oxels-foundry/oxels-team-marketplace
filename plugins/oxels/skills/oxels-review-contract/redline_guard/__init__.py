"""Guardrail for keeping agent DOCX edits as Word tracked changes."""

from redline_guard.apply import ApplyError, apply_edits, list_paragraphs
from redline_guard.comments import add_comments, list_comments, scrub_internal_notes, set_comment_status
from redline_guard.tables import list_tables
from redline_guard.resolve import clean_docx, list_revisions, resolve_revisions
from redline_guard.verify import VerifyReport, format_report, verify_docx

__all__ = [
    "ApplyError",
    "VerifyReport",
    "add_comments",
    "apply_edits",
    "clean_docx",
    "format_report",
    "list_comments",
    "list_tables",
    "set_comment_status",
    "list_paragraphs",
    "list_revisions",
    "resolve_revisions",
    "scrub_internal_notes",
    "verify_docx",
]
