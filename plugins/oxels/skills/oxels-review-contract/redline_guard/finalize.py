"""Exact-file gate: finalize, attest, status (plan §17.4)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from redline_guard.comments import list_comments, scrub_internal_notes
from redline_guard.formatting import compare_formatting
from redline_guard.ooxml import enable_track_revisions, load_docx, refuse_overwrite, revision_view_shows_markup, save_docx, track_revisions_enabled
from redline_guard.render import render_docx, renderer_available
from redline_guard.resolution_log import (
    DEFAULT_AUTHOR,
    empty_resolution_log,
    file_sha256,
    log_path_for,
    require_author,
)
from redline_guard.structure import StructureError, schema_available, validate_structure
from redline_guard.verify import verify_docx


class FinalizeError(ValueError):
    """finalize refused to run."""


# Microsoft's Open XML SDK validator, which is not bundled: it is a .NET tool, and
# this layer is an optional strengthening rather than a required dependency. Point
# REDLINE_OPENXML_VALIDATE at a build to switch it on, the way REDLINE_SOFFICE does
# for the renderer.
BUNDLED_SDK_VALIDATOR = Path(__file__).resolve().parents[1] / "tools" / "openxml_validate" / "openxml-validate"

SDK_UNAVAILABLE_MESSAGE = (
    "The Open XML SDK validator is not installed, so conformance with Word's own rules was NOT "
    "checked; the ECMA schema check covers the published spec only. To switch this layer on, point "
    "REDLINE_OPENXML_VALIDATE at an openxml-validate build."
)


def sdk_validator() -> Path | None:
    """The validator to run, or None when this optional layer is switched off."""
    env = os.environ.get("REDLINE_OPENXML_VALIDATE", "").strip()
    if env:
        candidate = Path(env)
        return candidate if candidate.exists() else None
    return BUNDLED_SDK_VALIDATOR if BUNDLED_SDK_VALIDATOR.exists() else None


def _sdk_errors(path: Path | str) -> tuple[bool, list[dict]]:
    """Run Microsoft's Open XML SDK validator. Returns (available, errors)."""
    import subprocess

    validator = sdk_validator()
    if validator is None:
        return False, []
    with tempfile.TemporaryDirectory(prefix="redline-sdk-") as directory:
        report = Path(directory) / "sdk.json"
        proc = subprocess.run(
            [str(validator), "--max", "200", "--json", str(report), str(path)],
            capture_output=True, text=True,
        )
        if proc.returncode == 4 or not report.exists():
            return False, []
        data = json.loads(report.read_text())
    files = data.get("files") or [{}]
    return True, files[0].get("problems") or []


def _sdk_check(original: Path | str, candidate: Path | str, failures: list) -> dict:
    """Validate the source and our output, and fail only on defects we introduced.

    The ECMA schema check follows the published spec; Word enforces more, and the gap is where the
    "unreadable content" repair dialog lives. Counterparty files routinely arrive carrying their own
    defects, so failing on everything the validator reports would block legitimate work on
    documents we did not break.

    Defects are matched on (description, part), not on XPath: inserting a paragraph shifts every
    XPath below it, so position cannot identify "the same" defect across an edit. That means an
    introduced defect that happens to read identically to a pre-existing one in the same part is
    counted as pre-existing. The count guards against that for the common case: more occurrences
    than the original had is reported as introduced.
    """
    available, before = _sdk_errors(original)
    if not available:
        return {"ok": True, "available": False, "message": SDK_UNAVAILABLE_MESSAGE}
    _, after = _sdk_errors(candidate)

    def key(problem: dict) -> tuple:
        return (problem.get("description", ""), problem.get("part_uri", ""))

    from collections import Counter
    baseline = Counter(key(p) for p in before)
    introduced = []
    for problem in after:
        k = key(problem)
        if baseline[k] > 0:
            baseline[k] -= 1
            continue
        introduced.append(problem)

    result = {
        "ok": not introduced,
        "available": True,
        "source_errors": len(before),
        "send_errors": len(after),
        "introduced": introduced,
    }
    for problem in introduced:
        failures.append({
            "kind": "openxml_sdk",
            "location": problem.get("xpath") or problem.get("part_uri") or "",
            "story": "", "paragraph": 0,
            "message": ("This draft breaks a rule Word enforces that the source did not: "
                        f"{problem.get('description', '')} (part {problem.get('part_uri', '?')}). "
                        "Word may refuse to open the file or offer to repair it."),
            "baseline_excerpt": "", "edited_excerpt": "",
        })
    if before and not introduced:
        result["message"] = (f"The source already has {len(before)} Open XML SDK error(s); "
                             "this draft introduces none. Not blocking.")
    return result


@dataclass
class FinalizeReport:
    ok: bool
    status: str
    original: str
    draft: str
    send: str
    send_sha256: str
    manifest: str
    checks: dict = field(default_factory=dict)
    pages: list = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "original": self.original,
            "draft": self.draft,
            "send": self.send,
            "send_sha256": self.send_sha256,
            "manifest": self.manifest,
            "checks": self.checks,
            "pages": self.pages,
            "failures": self.failures,
        }


def finalize_docx(
    original: str | Path,
    draft: str | Path,
    send: str | Path,
    pages_dir: str | Path | None = None,
    author: str | Sequence[str] = DEFAULT_AUTHOR,
    resolved: list[str | Path] | None = None,
    prior_round: bool = False,
) -> FinalizeReport:
    """Prepare a scrubbed, checked copy. Only attest can mark it ready.

    Work on a temporary candidate, so exceptions cannot leave a partly checked
    DOCX at the send path. Existing source files and unrelated sidecars are never
    overwritten. The skill decides when the user has finished editing.

    ``author`` is one trusted name or, for a file several of our agents
    touched, a list of names; the checks receive it as given.
    """
    import shutil
    import tempfile
    from redline_guard.qa_common import check_record, file_record, read_json, stable_hash, write_json

    from redline_guard.verify import trusted_authors

    author = trusted_authors(_author_arg(author)).compat()  # str for one name, TrustedAuthors for several
    original, draft, send = (Path(p).resolve() for p in (original, draft, send))
    manifest_path = Path(f"{send}.finalize.json")
    if send in {original, draft}:
        raise FinalizeError("Refusing to overwrite an existing send file or an input; pass a new path.")
    if send.exists():
        # A send file this command wrote, never attested and unchanged since, is
        # replaced: the agent looked at the pages, fixed the draft, and runs
        # finalize again. Anything else is left alone.
        _release_unattested_send_file(send, manifest_path)
    for p in (original, draft):
        if not p.is_file():
            raise FinalizeError(f"Input file is missing: {p}")
    pages_dir = Path(pages_dir).resolve() if pages_dir is not None else Path(f"{send}.pages")
    logs = [Path(p).resolve() for p in (resolved or [])]
    sidecar = log_path_for(send)
    # A previous run can be repeated after removing its send file. Recognize its
    # own sidecars; do not overwrite arbitrary files merely sharing the suffix.
    if manifest_path.exists():
        try:
            previous = read_json(manifest_path)
            if previous.get("version") != 2 or previous.get("send") != str(send):
                raise ValueError("not a current finalization manifest")
            if sidecar.exists():
                record = next(r for r in previous.get("evidence", []) if r["path"] == str(sidecar))
                check_record(record)
        except (ValueError, KeyError, StopIteration, OSError) as exc:
            raise FinalizeError(f"Existing finalization sidecars cannot be reused: {exc}") from exc
    elif sidecar.exists():
        raise FinalizeError("The send path already has a resolution log; choose a new path.")

    failures, checks, pages = [], {}, []
    created = []
    payload = {"version": 2, "original": str(original), "draft": str(draft), "send": str(send),
               "send_sha256": "", "status": "failed", "checks": checks, "pages": pages,
               "author": _author_value(author), "resolved": [str(p) for p in logs], "evidence": []}
    try:
        inputs = [file_record(original), file_record(draft)]
        if log_path_for(draft).exists():
            inputs.append(file_record(log_path_for(draft)))
        inputs.extend(file_record(p) for p in logs)
        payload["original_sha256"] = inputs[0]["sha256"]
        payload["draft_sha256"] = inputs[1]["sha256"]
        with tempfile.TemporaryDirectory(prefix="redline-finalize-") as directory:
            candidate = Path(directory) / "candidate.docx"
            scrub_internal_notes(draft, candidate)
            # The send file always opens with Track Changes on and All Markup
            # shown, whatever view the draft was saved in.
            _show_markup(candidate)
            if not log_path_for(draft).exists():
                # A draft that arrives without its sidecar has no decisions to
                # replay; bind an empty log to the original rather than to the
                # draft, which verify would rightly reject.
                log_path_for(candidate).write_text(json.dumps(empty_resolution_log(original), indent=2) + "\n")
                checks["resolution_log"] = {
                    "ok": True,
                    "created": True,
                    "message": (
                        f"The draft has no resolution log beside it ({log_path_for(draft).name}); "
                        f"an empty log bound to {original} was written as {sidecar.name}. "
                        "Any accepted or rejected counterparty revision would then fail verify as untracked."
                    ),
                }
            candidate_hash = file_sha256(candidate)
            notes = _notes_check(candidate)
            failures.extend(notes.get("failures") or [])
            failures.extend(_settings_check(candidate))
            verified = verify_docx(original, candidate, resolved=logs, author=author, prior_round=prior_round)
            checks["verify"] = verified.to_dict()
            failures.extend(f.to_dict() for f in verified.failures)
            structured = validate_structure(candidate, original=original, schema="required")
            checks["structure"] = structured.to_dict()
            failures.extend(d.to_dict() for d in structured.defects)
            formatted = compare_formatting(original, candidate, author=author, resolved=logs)
            checks["formatting"] = formatted.to_dict()
            failures.extend({**f.to_dict(), "subkind": f.kind, "kind": "untracked_formatting"} for f in formatted.failures)
            checks["notes"] = notes
            # Conformance with Word's own rules, source vs send file. Runs before render because a
            # file Word will not open is not worth rendering. Keeps the preservation checks above:
            # a document can be perfectly conformant and still have changed the wrong words.
            checks["openxml_sdk"] = _sdk_check(original, candidate, failures)
            if not failures:
                checks["render"] = _render_or_dependency(candidate, pages_dir, original, author, failures)
                pages.extend(checks["render"].get("pages") or [])
            else:
                checks["render"] = {"ok": False, "pages": [], "failures": [{"message": "Not run because automatic checks failed."}]}
            for record in inputs:
                check_record(record)
            if file_sha256(candidate) != candidate_hash:
                raise FinalizeError("Candidate changed while validation was running.")
            if not failures:
                image_records = []
                for page in pages:
                    for field in ("image", "final_image", "before_image", "diff_image"):
                        if page.get(field):
                            image_records.append(file_record(page[field]))
                if not image_records:
                    raise FinalizeError("No page images were produced; visual review cannot be completed.")
                # Exclusive creation guards the interval since the initial check.
                with send.open("xb") as dest:
                    created.append(send)
                    with candidate.open("rb") as src:
                        shutil.copyfileobj(src, dest)
                if sidecar.exists():
                    sidecar.unlink()  # known evidence from the previous run only
                with sidecar.open("xb") as dest:
                    created.append(sidecar)
                    dest.write(log_path_for(candidate).read_bytes())
                payload["send_sha256"] = candidate_hash
                payload["evidence"] = inputs + [file_record(sidecar)] + image_records + [file_record(pages_dir / "pages.json")]
                payload["checks_sha256"] = stable_hash(checks)
                payload["pages_sha256"] = stable_hash(pages)
                payload["status"] = "inspect"
                defects = _evidence_failures(send, payload)
                if defects:
                    failures.extend(defects)
    except Exception as exc:
        failures.append({"kind": "dependency_missing" if isinstance(exc, StructureError) else "finalization_failed", "message": str(exc)})
    if failures:
        for path in created:
            path.unlink(missing_ok=True)
        payload["status"] = "failed"
    payload["failures"] = failures
    write_json(manifest_path, payload)
    return FinalizeReport(not failures, payload["status"], str(original), str(draft), str(send),
                          payload["send_sha256"], str(manifest_path), checks, pages, failures)


def _release_unattested_send_file(send: Path, manifest_path: Path) -> None:
    """Remove a previous send file so finalize can run again on a fixed draft.

    Only a file this command wrote for this path, still at ``inspect`` and
    byte-identical to what the manifest recorded, is removed, with its
    resolution log. A file attested ``ready`` may already have been sent, a
    file that changed since is someone's work, and a file without a manifest
    is not ours: each is refused with the route to a new path.
    """
    from redline_guard.qa_common import read_json

    try:
        data = read_json(manifest_path) if manifest_path.exists() else None
    except (ValueError, OSError):
        data = None
    if not data or data.get("version") != 2 or data.get("send") != str(send):
        raise FinalizeError("Refusing to overwrite an existing send file or an input; pass a new path.")
    if data.get("status") == "ready":
        raise FinalizeError(
            f"{send.name} was attested ready and may already have been sent; "
            f"finalize the fixed draft to a new path (for example {send.stem}-2{send.suffix})."
        )
    if file_sha256(send) != data.get("send_sha256"):
        raise FinalizeError(
            f"{send.name} changed after finalize wrote it, so it is not removed; "
            f"finalize to a new path (for example {send.stem}-2{send.suffix})."
        )
    send.unlink()
    log_path_for(send).unlink(missing_ok=True)


def _evidence_failures(send: Path, data: dict) -> list[dict]:
    """Bind readiness to the source, decision logs, checks, and every rendered view."""
    from redline_guard.qa_common import check_record, stable_hash

    try:
        if data.get("version") != 2:
            raise ValueError("Old or unsupported manifest; run finalize again.")
        if data.get("send") != str(send.resolve()):
            raise ValueError("Manifest belongs to another send path.")
        if not send.is_file() or data.get("send_sha256") != file_sha256(send):
            raise ValueError("file changed since finalize")
        checks, pages = data.get("checks", {}), data.get("pages", [])
        if any(not checks.get(name, {}).get("ok") for name in ("verify", "structure", "formatting", "render", "notes", "openxml_sdk")):
            raise ValueError("Automatic checks did not all pass.")
        if not checks["structure"].get("schema_checked"):
            raise ValueError("Required schema checks were not run.")
        if stable_hash(checks) != data.get("checks_sha256") or stable_hash(pages) != data.get("pages_sha256"):
            raise ValueError("Checks or page manifest changed since finalize.")
        if not pages:
            raise ValueError("No pages are recorded for inspection.")
        numbers = [p["number"] for p in pages]
        if numbers != list(range(1, len(pages) + 1)):
            raise ValueError("Page list is incomplete or contains duplicates.")
        for field, count_key in (("image", "page_count"), ("final_image", "final_page_count"), ("before_image", "original_page_count")):
            count = checks["render"].get(count_key, 0)
            actual = [p["number"] for p in pages if p.get(field)]
            if not isinstance(count, int) or count < 1 or actual != list(range(1, count + 1)):
                raise ValueError(f"The {field} view is missing pages.")
        evidence = data.get("evidence", [])
        recorded = {r["path"]: r for r in evidence}
        required = {data["original"], data["draft"], str(log_path_for(send))} | set(data.get("resolved", []))
        for page in pages:
            required.update(page[field] for field in ("image", "final_image", "before_image", "diff_image") if page.get(field))
        if not required.issubset(recorded):
            raise ValueError("Missing source, resolution-log, or page-image evidence.")
        for record in evidence:
            check_record(record)
        for key in ("original", "draft"):
            if recorded[data[key]]["sha256"] != data[key + "_sha256"]:
                raise ValueError(f"The {key} evidence disagrees with the manifest.")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return [{"kind": "stale_evidence", "message": str(exc)}]
    return []


def _read_manifest_report(send: str | Path):
    from redline_guard.qa_common import read_json
    send = Path(send).resolve()
    manifest = Path(f"{send}.finalize.json")
    report = _report_from_manifest(send, manifest)
    try:
        data = read_json(manifest)
    except (ValueError, OSError) as exc:
        report.failures.append({"message": f"No readable finalization manifest: {exc}"})
        return send, report, None
    report.original = data.get("original", "")
    report.draft = data.get("draft", "")
    report.send_sha256 = data.get("send_sha256", "")
    report.checks = data.get("checks", {})
    report.pages = data.get("pages", [])
    if data.get("status") == "failed":
        report.failures = data.get("failures") or [{"message": "checks failed"}]
        return send, report, None
    report.failures = _evidence_failures(send, data)
    if report.failures:
        return send, report, None
    return send, report, data


def attest_pages(send: str | Path, pages: str | list[int] = "all", by: str = "") -> FinalizeReport:
    from redline_guard.qa_common import write_json
    send, report, data = _read_manifest_report(send)
    if data is None:
        return report
    if data.get("status") != "inspect":
        report.failures.append({"message": f"status is {data.get('status')}"})
        return report
    available = [page["number"] for page in data["pages"]]
    wanted = available if pages == "all" else pages
    if not isinstance(wanted, list) or any(type(n) is not int for n in wanted) or set(wanted) != set(available) or len(wanted) != len(available):
        report.status = "inspect"
        report.failures.append({"message": f"Inspect all page numbers {available}, including every markup, final, and before image listed."})
        return report
    data["attested"] = {"pages": sorted(wanted), "by": by or _author_label(data.get("author", DEFAULT_AUTHOR)),
                         "at": datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")}
    data["status"] = "ready"
    write_json(report.manifest, data)
    report.status, report.ok = "ready", True
    return report


def finalize_status(send: str | Path) -> FinalizeReport:
    send, report, data = _read_manifest_report(send)
    if data is None:
        return report
    available = [page["number"] for page in data["pages"]]
    attested = data.get("attested") or {}
    if data.get("status") == "ready" and attested.get("pages") == available and attested.get("by") and attested.get("at"):
        report.status, report.ok = "ready", True
    else:
        report.status = "inspect"
        report.failures.append({"message": f"awaiting inspection of pages {', '.join(map(str, available))}"})
    return report


def _author_arg(author):
    """One name stays a string; several names become a list without duplicates."""
    if isinstance(author, str):
        return author
    names = list(dict.fromkeys(str(name) for name in author if str(name).strip()))
    if not names:
        return require_author(DEFAULT_AUTHOR)
    return names[0] if len(names) == 1 else names


def _author_value(author):
    """Manifest value: the single name as a string, several names as a list in the order given."""
    if isinstance(author, str):
        return author
    names = getattr(author, "names", None)
    return list(names) if names else [str(name) for name in author]


def _author_label(author) -> str:
    if isinstance(author, str):
        return author
    names = getattr(author, "names", None)
    return ", ".join(names) if names else ", ".join(str(name) for name in author)


_VIEW_FLAGS = ("markup", "insDel", "comments", "formatting")


def _show_markup(path: Path) -> None:
    """Turn Track Changes on and show all markup in the file's settings.

    Writing commands only add ``w:trackRevisions``; a draft saved in No Markup
    keeps ``w:revisionView w:markup="false"`` and finalize used to fail closed
    on it with no route.  The send file is what leaves, so its view is set here,
    before the settings check, by string edits that keep the rest of the part
    byte-identical.
    """
    package = load_docx(path)
    before = package.files.get("word/settings.xml")
    enable_track_revisions(package.files)
    text = package.files["word/settings.xml"].decode("utf-8")

    def show(match: re.Match) -> str:
        tag = match.group(0)
        for flag in _VIEW_FLAGS:
            tag = re.sub(rf'(\sw:{flag}=")(?:0|false|off|False)(")', r"\1true\2", tag)
        return tag

    text = re.sub(r"<w:revisionView\b[^>]*>", show, text)
    package.files["word/settings.xml"] = text.encode("utf-8")
    if package.files["word/settings.xml"] != before:
        save_docx(package, path)


def _settings_check(send: Path) -> list[dict]:
    """Fail the send file if tracking is off or markup is hidden, even when the original is too."""
    files = load_docx(send).files
    failures: list[dict] = []
    if not track_revisions_enabled(files):
        failures.append(
            {
                "kind": "settings",
                "part": "word/settings.xml",
                "message": "w:trackRevisions is missing or off on the send file.",
            }
        )
    if revision_view_shows_markup(files) is False:
        failures.append(
            {
                "kind": "settings",
                "part": "word/settings.xml",
                "message": "w:revisionView hides markup on the send file.",
            }
        )
    return failures


def _notes_check(send: Path) -> dict:
    leftover = [c for c in list_comments(str(send)) if c.internal]
    failures = [
        {
            "kind": "internal_note_present",
            "location": c.location,
            "message": f"internal note {c.id} is still in the send file",
        }
        for c in leftover
    ]
    return {"ok": not failures, "failures": failures}


def _render_or_dependency(
    send: Path,
    pages_dir: Path,
    original: Path,
    author: str,
    failures: list[dict],
) -> dict:
    tools = renderer_available()
    missing = [name for name, loc in tools.items() if not loc or not Path(loc).exists()]
    if missing:
        item = {
            "kind": "dependency_missing",
            "message": (
                f"{', '.join(missing)} is required for finalize. "
                "Install LibreOffice and poppler, or set REDLINE_SOFFICE / REDLINE_PDFTOPPM / REDLINE_PDFTOTEXT."
            ),
        }
        failures.append(item)
        return {"ok": False, "failures": [item], "pages": []}
    rendered = render_docx(send, pages_dir, original=original, author=author)
    data = rendered.to_dict()
    for item in rendered.failures:
        payload = item.to_dict()
        if item.kind in {"renderer_missing", "render_failed"}:
            payload["kind"] = "dependency_missing"
        failures.append(payload)
    return data


def _report_from_manifest(send: Path, manifest_path: Path) -> FinalizeReport:
    return FinalizeReport(
        ok=False,
        status="failed",
        original="",
        draft="",
        send=str(send),
        send_sha256="",
        manifest=str(manifest_path),
    )
