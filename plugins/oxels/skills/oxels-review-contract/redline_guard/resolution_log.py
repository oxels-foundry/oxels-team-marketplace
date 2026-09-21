"""Resolution log that travels with a DOCX and accounts for vanished revisions."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable, TextIO

# The name every tracked change, comment, and note carries. Set REDLINE_AUTHOR
# once per working session so no command needs --author; verify checks against it.
# There is deliberately no fallback name: whatever stands here is written into
# markup the counterparty reads, and a placeholder would be wrong in every deal,
# so a command that needs a name and has none refuses instead of guessing.
DEFAULT_AUTHOR = os.environ.get("REDLINE_AUTHOR", "").strip()


class MissingAuthorError(ValueError):
    """A command that signs its output had no author name to use."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "no author name; pass --author, or set REDLINE_AUTHOR to the name "
            "tracked changes, comments and notes should carry"
        )


def require_author(author: str | Iterable[str] | None):
    """Return the author name(s) as given, or refuse when there is none to sign with."""
    names = [author] if isinstance(author, str) else list(author or [])
    if not any(str(name or "").strip() for name in names):
        raise MissingAuthorError()
    return author


def resolution_entry_key(entry: dict[str, Any]) -> str:
    """A partial decision may leave the same revision available for another decision."""
    return str(entry.get("event_id") or entry.get("id", ""))


def log_path_for(docx_path: str | Path) -> Path:
    return Path(f"{docx_path}.resolved.json")


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_resolution_log(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Resolution log {path} must be a JSON object.")
    resolved = data.get("resolved") or []
    if not isinstance(resolved, list):
        raise ValueError(f"Resolution log {path} is missing a 'resolved' list.")
    return {
        "source": str(data.get("source", "")),
        "source_hash": str(data.get("source_hash", "")),
        "resolved": resolved,
    }


def copy_resolution_log(input_path: str | Path, output_path: str | Path) -> Path:
    """Carry the lineage log forward, creating one from the input on first touch."""
    dest = log_path_for(output_path)
    incoming = log_path_for(input_path)
    if incoming.exists() and incoming.resolve() != dest.resolve():
        dest.write_text(incoming.read_text())
        return dest
    if incoming.exists():
        return dest
    dest.write_text(json.dumps(empty_resolution_log(input_path), indent=2) + "\n")
    return dest


def write_resolve_log(
    input_path: str | Path,
    output_path: str | Path,
    entries: list[dict[str, Any]],
    log_path: str | Path | None = None,
) -> Path:
    dest = Path(log_path) if log_path else log_path_for(output_path)
    incoming = log_path_for(input_path)
    if incoming.exists():
        data = read_resolution_log(incoming)
    else:
        data = empty_resolution_log(input_path)
    if not data.get("source_hash") and data.get("source") and sources_match(data["source"], input_path):
        data["source_hash"] = file_sha256(input_path)
    seen = {resolution_entry_key(item) for item in data["resolved"]}
    for entry in entries:
        entry = dict(entry)
        entry["event_id"] = uuid.uuid4().hex
        rev_id = str(entry.get("id", ""))
        key = resolution_entry_key(entry)
        if not rev_id or key in seen:
            continue
        data["resolved"].append(entry)
        seen.add(key)
    text = json.dumps(data, indent=2)
    dest.write_text(text)
    default = log_path_for(output_path)
    if dest.resolve() != default.resolve():
        default.write_text(text)
    return dest


def reversal_index(entries: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """Counterparty revision id -> ids of our reversal markup still standing, in event order.

    A rejection written as a tracked change lists the ids it wrote under
    ``reversal_ids``. A later event whose ``withdraws`` names that revision
    takes its own id back out of the list (our reversal was removed, so the
    revision is pending again and may be decided afresh). Logs written before
    these fields existed yield an empty list for the revision; resolve then
    finds the reversal in the document itself.
    """
    index: dict[str, list[str]] = {}
    for entry in entries:
        rev_id = str(entry.get("id", ""))
        if entry.get("tracked") and entry.get("action") == "reject":
            index.setdefault(rev_id, []).extend(str(x) for x in entry.get("reversal_ids") or [])
        withdrawn = entry.get("withdraws")
        if withdrawn:
            ids = index.setdefault(str(withdrawn), [])
            index[str(withdrawn)] = [x for x in ids if x != rev_id]
    return index


def standing_tracked_rejections(entries: Iterable[dict[str, Any]]) -> set[str]:
    """Ids of counterparty revisions whose rejection as a tracked change still stands.

    A rejection stands from its ``tracked`` reject event until an event that
    ``withdraws`` it. Only these are rejections: our deletion nested in their
    insertion may also be an ordinary edit (``apply`` delete, ``delete_row``),
    which accepting theirs leaves pending, as the reference says.
    """
    standing: set[str] = set()
    index: dict[str, list[str]] = {}
    for entry in entries:
        rev_id = str(entry.get("id", ""))
        if entry.get("tracked") and entry.get("action") == "reject":
            index.setdefault(rev_id, []).extend(str(x) for x in entry.get("reversal_ids") or [])
            standing.add(rev_id)
        withdrawn = entry.get("withdraws")
        if withdrawn:
            # Withdrawing one of several partial reversals leaves the others standing.
            index[str(withdrawn)] = [x for x in index.get(str(withdrawn), []) if x != rev_id]
            if not index[str(withdrawn)]:
                standing.discard(str(withdrawn))
    return standing


def merge_resolution_logs(paths: Iterable[str | Path]) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge logs. Returns (entries, source paths)."""
    entries: list[dict[str, Any]] = []
    sources: list[str] = []
    seen: set[str] = set()
    for path in paths:
        data = read_resolution_log(path)
        if data["source"]:
            sources.append(data["source"])
        for item in data["resolved"]:
            rev_id = str(item.get("id", ""))
            key = resolution_entry_key(item)
            if not rev_id or key in seen:
                continue
            entries.append(item)
            seen.add(key)
    return entries, sources


def empty_resolution_log(input_path: str | Path) -> dict[str, Any]:
    return {"source": str(input_path), "source_hash": file_sha256(input_path), "resolved": []}


def sources_match(log_source: str, original: str | Path) -> bool:
    if not log_source:
        return False
    try:
        return Path(log_source).resolve() == Path(original).resolve()
    except OSError:
        return Path(log_source) == Path(original)


def log_matches_original(data: dict[str, Any], original: str | Path) -> bool:
    source = data.get("source") or ""
    stored_hash = data.get("source_hash") or ""
    if stored_hash:
        try:
            return stored_hash == file_sha256(original)
        except OSError:
            return False
    if source and sources_match(source, original):
        return True
    return not source


def document_authors(path: str | Path) -> set[str]:
    from redline_guard.comments import list_comments
    from redline_guard.resolve import list_revisions

    authors = {rev.author for rev in list_revisions(path) if rev.author}
    authors.update(comment.author for comment in list_comments(str(path)) if comment.author)
    return authors


def warn_if_author_exists(path: str | Path, author: str, stream: TextIO | None = None) -> bool:
    if not author or author.lower() == DEFAULT_AUTHOR.lower():
        return False
    existing = {name.lower() for name in document_authors(path)}
    if author.lower() not in existing:
        return False
    print(
        f"warning: author '{author}' already appears in this document; "
        "new edits will be attributed to them.",
        file=stream or sys.stderr,
    )
    return True
