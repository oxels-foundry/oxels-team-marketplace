# DOCX tool reference

## Runtime requirements

The editing commands run on Python 3 and use the standard library. Resolve `scripts/redline.py` relative to the skill's `SKILL.md` and set its absolute path once:

```bash
export REDLINE_TOOL="/absolute/path/to/this-skill/scripts/redline.py"
```

Set the author name once as well. Every command that writes tracked changes, comments, or notes signs them with it, and there is no default, so a writing command refuses without it:

```bash
export REDLINE_AUTHOR="<the name the counterparty should see>"
```

The launcher's location, not the terminal's working directory, locates the bundled `redline_guard` package and its `schemas/` directory. No package installation is needed for `list`, `tables`, `revisions`, `comments`, `apply`, `accept`, `reject`, `resolve`, `comment`, `note`, `resolve-comment`, `reopen-comment`, `scrub`, `verify`, `clean`, `attest`, or `status`. `validate` also runs without anything installed, skipping its schema layer with a warning.

The send-file gate deliberately has additional requirements:

- `lxml`, for required ECMA-376 schema validation.
- LibreOffice, for markup and final-view rendering.
- Poppler's `pdftoppm` and `pdftotext`, for page images and rendered-text checks.

Install the Python dependency in the active Python environment:

```bash
python3 -m pip install lxml
```

The renderer searches normal system locations. If a tool is installed elsewhere, set its absolute path:

```bash
export REDLINE_SOFFICE="/absolute/path/to/soffice"
export REDLINE_PDFTOPPM="/absolute/path/to/pdftoppm"
export REDLINE_PDFTOTEXT="/absolute/path/to/pdftotext"
```

`finalize` fails closed when any of those three is unavailable. Do not bypass schema validation or visual rendering to produce a send file.

### Optional: conformance with Word's own rules

The ECMA schema check covers the published spec. Word enforces more — part and relationship rules, version-targeted constraints, and semantic rules an XSD cannot express — and that gap is where the "Word found unreadable content" repair dialog lives. A clean LibreOffice render does not close it: LibreOffice is tolerant and opens files Word rejects.

Microsoft's Open XML SDK validator (`OpenXmlValidator` from `DocumentFormat.OpenXml`) is the only thing that checks those rules. It is a .NET tool and is deliberately not bundled, so this layer is off by default. Point `REDLINE_OPENXML_VALIDATE` at an `openxml-validate` build to switch it on:

```bash
export REDLINE_OPENXML_VALIDATE="/absolute/path/to/openxml_validate/openxml-validate"
```

Switched on, `finalize` compares the source and the send file and fails only on defects the edit introduced, since counterparty files routinely arrive with their own. Switched off, `finalize` still runs every other check and produces a send file, and says which layer did not run:

```text
not checked: The Open XML SDK validator is not installed, so conformance with Word's own rules was NOT checked; ...
```

Treat that line as a real gap, not noise: nothing has verified that Word will open the file without complaint.

## Command conventions

All commands below use `python3 "$REDLINE_TOOL" <command> ...`.

Every writing command takes `input output` and writes a new file. An existing output is replaced, except a finalized send file (one with a `.finalize.json` manifest beside it), which every writing command refuses: `Refusing to overwrite <file>: it is a finalized send file (status ...); write to a new path`. The author name on everything written comes from `--author`, else the `REDLINE_AUTHOR` environment variable. There is no default: a command that signs its output and has neither refuses with `no author name; pass --author, or set REDLINE_AUTHOR ...`, because whatever name it carried would be read by the counterparty. `verify` and `finalize` check against the same name, so set the variable once and leave the flags alone. Exit codes: 0 success, 1 the command refused with a one-line reason on stderr (`<command> failed: ...`, also for a missing file, a path that is a directory, any other IO error, a file that is not a .docx package, invalid JSON, or an unknown story), 2 wrong arguments.

Paragraph numbers count every paragraph in document order, including table cells; Word's footnote and endnote separators are not paragraphs and are never listed or edited.

## list

`list input.docx [--story NAME] [--json]`

One line per paragraph: `body paragraph 24  <label>  <text as it reads with changes accepted> [has revisions]`. Paragraph numbers count every paragraph in document order, including table cells. Headers, footers, and footnotes are separate stories with their own numbering; the story name printed here is what `--story` and the `"story"` field take. `--json` gives `accept_text` and `reject_text` per paragraph. Paragraphs inside a tracked row show `[has revisions]` with the row's revision counted; a deleted row's cells are empty in `accept_text`, as text inside a tracked deletion is. A text box is stored twice (`mc:Choice` and `mc:Fallback`) and listed once, under the paragraph numbers of the `mc:Choice` copy right after the paragraph that holds the box; an edit to those paragraphs is mirrored into the `mc:Fallback` copy, `comments` reports a comment in the box on the box's own paragraph number, and `verify` checks that the fallback copy still matches; comments, notes and replies placed in the box, and accept or reject decisions on revisions inside it, are mirrored into the fallback copy as well. A non-breaking hyphen shows as U+2011, a soft hyphen as U+00AD, and a symbol character (`w:sym`, Symbol or Wingdings) as the private-use character Word stores for it (U+F0xx); copy them from `list` or `list --json` into a find string like any other character.

## tables

`tables input.docx [--story NAME] [--json]`

One line per table row: `body table 2 row 3  <cell text> | <cell text>`, with the row's tracked insertion or deletion when it has one. Tables and rows are numbered in document order within the story, nested tables after the table that contains them. `insert_row` and `delete_row` take these numbers, from the file the batch starts from.

## revisions

`revisions input.docx [--json]`

Every existing tracked change with its id, kind (`ins`, `del`, `format`), author, location, and text. Paragraph-mark and table-row revisions show with empty text. A move is listed as its two halves, each naming the move and the other half's id (`move mv1: from, pairs with [109]`); either id resolves both. Ids are what `accept`, `reject`, and `resolve` take.

## comments

`comments input.docx [--json]`

Every comment with id, author, paragraph, reply parent, and whether it is an internal note.

## apply

`apply input.docx output.docx --edits edits.json [--author NAME]`

`--edits` is a path or an inline JSON list. Edit types: `replace` (`find`, `replace`), `insert` (`text` plus at most one of `after`, `before`, `find`; none means end of paragraph, after a trailing field; two anchors are refused), `delete` (`find`), `insert_paragraph` (`text`, which may be empty for a blank paragraph; optional `position: "before"` to put the new paragraph before the anchor instead of after it, `numbering: false` to drop the anchor's list numbering, and `style` to set the paragraph style, which must be a paragraph style id from `word/styles.xml`), `delete_paragraph`, `format_run` (`find`, `properties`), `format_paragraph` (`properties`), `insert_row` (`table`, `row`, `cells`, optional `position`), `delete_row` (`table`, `row`). Required on paragraph edits: `paragraph`. Optional: `story`, `occurrence`. Any other field is refused. Output must be a different file from the input.

A newline in `text` becomes a line break inside the paragraph, the way `list` shows a line break as a newline; a tab becomes a tab. Text that needs a new paragraph goes through `insert_paragraph`.

**Tracked formatting.** `format_run` changes the formatting of the exact span `find` names and records it as a Word formatting revision (`rPrChange`) under the author, so Accept keeps the new look and Reject restores the old one. Properties: `bold`, `italic`, `strike`, `superscript` (true, false, or null to clear), `underline` (true, false, or any Word underline style: `single`, `words`, `double`, `thick`, `dotted`, `dottedHeavy`, `dash`, `dashedHeavy`, `dashLong`, `dashLongHeavy`, `dotDash`, `dashDotHeavy`, `dotDotDash`, `dashDotDotHeavy`, `wave`, `wavyHeavy`, `wavyDouble`, `none`), `font` (name), `size` (points, half-point steps), `color` (six hex digits or `auto`), `highlight` (a Word highlight name), `style` (a character style id the document defines in `styles.xml`; an unknown id, or a paragraph style, is refused). `format_paragraph` does the same for the paragraph (`pPrChange`): `style` (a paragraph style id the document defines; unknown ids are refused), `alignment` (`left`, `center`, `right`, `both`), `keep_next`, `keep_lines`, `page_break_before`, `space_before`, `space_after` (twips, non-negative, or null to clear), `indent_left`, `indent_right` (twips, negative for an outdent, or null), `first_line`, `hanging` (twips or null; a paragraph has one or the other, so setting one replaces the other, a negative `first_line` is written as the equivalent `hanging` the way Word stores it, and clearing one leaves the other). A second change of ours on the same text folds into the first revision, so the counterparty sees one change whose old state is the original. Changing text back to its original look leaves nothing tracked. `format_run` and `format_paragraph` on a span or paragraph that carries the counterparty's pending formatting change are refused until that change is accepted or rejected. Text edits and comments that split a run carrying a formatting revision, ours or theirs, are fine: every fragment keeps the revision under its own id, which is how Word records it.

**Tracked rows.** `insert_row` adds a row after the row named by `table` and `row` from `tables` (`"position": "before"` for before), copying that row's properties and cell formatting but not its content or history; `cells` is a list of one string per cell, empty strings allowed. The row and its text are tracked insertions. `delete_row` marks the row as a tracked deletion and keeps its cells until the deletion is accepted; comments and bookmarks inside a row survive acceptance by collapsing into the next row. Revisions inside the cells stay pending, as inside a struck paragraph. Deleting a row the counterparty inserted nests our deletion beside their insertion, so rejecting theirs removes the row and accepting theirs leaves ours pending. Deleting a row we inserted withdraws it, and text in a row we inserted is edited in place like any insertion of ours. Row edits work anywhere except through a vertical merge: inserting between two rows one cell spans, or deleting a row inside the span, is refused with a message naming the rows (`Rows 2 to 3 of table 2 are joined by a vertical merge; insert before row 2 or after row 3 instead`); rows outside the span and tables whose only merges are horizontal (`gridSpan`) work, and an inserted row keeps the template row's `gridSpan` layout without joining its vertical merge. Several inserts into the same gap land in batch order. Refusals: a row that is already a tracked deletion, the vertical-merge cases above, a `cells` list whose length differs from the template row (one string per cell as `tables` lists them; a horizontally merged cell counts once).

**Your own earlier changes.** A span inside text you inserted earlier edits that insertion in place: the words change inside your `w:ins`, a deletion removes them, and an insertion emptied this way disappears; nothing is nested. A span crossing from your insertion into plain text or into their insertion treats each part its own way. A span that passes over text you struck earlier is refused with the id to `reject` first, and so is a span inside the insertion that records a tracked rejection of theirs. `delete_paragraph` strikes a paragraph whatever revisions it carries (their insertion gets your deletion nested inside it, their deletion stays) and withdraws a paragraph you inserted; only a paragraph whose mark is already a tracked deletion is refused. Footnote references and pictures covered by a span are struck inside your deletion, as in Word; a symbol, a non-breaking hyphen or a soft hyphen is a character of the paragraph (U+F0xx, U+2011, U+00AD as `list` shows them), so a find can name it and a span that covers it strikes it, while a span boundary always falls before or after it; a struck footnote or endnote reference takes the note's text with it (struck under the same name and date), and withdrawing that deletion brings the note text back. A span that covers a field result (PAGE, DATE, REF, SEQ and the like) is refused, because Word regenerates the result; edit the text around it or the field in Word.

Refusals, all naming the paragraph:

- `could not find '...' (occurrence N) in the current text`: the find string is not in the paragraph as it reads with changes accepted. Re-copy it from `list`; a non-breaking hyphen, soft hyphen or symbol in the paragraph is a character there (U+2011, U+00AD, U+F0xx) and must be in the find string too.
- `target text overlaps existing tracked changes ('...')`: the span touches text the counterparty deleted. Spans inside their insertion, or crossing into or out of it, are fine and are recorded with your deletion nested in theirs for the inserted part; replacement or inserted text is placed beside their insertion, splitting it into pieces that keep their author and date, which is how Word records it. Narrow the find string away from their deleted text.
- `target text spans text you already struck (del [N], '...'); reject --id N to withdraw that deletion first` and `target text lies in your tracked reversal of del [N]; reject --id M to withdraw the reversal`.
- `target text covers the result of the PAGE field ('1'), which Word regenerates` and `the paragraph holds a PAGE field, which Word regenerates`.
- `insert takes one of after, before or find`.
- `Unsupported field '...' in edit spec`: a key the command does not implement. Nothing is ignored silently.
- `this paragraph is already a tracked deletion; accept or reject that revision instead`.
- `Accept or reject the pending formatting change by '...' before ...`: the span or paragraph carries their formatting revision and the edit is a formatting edit.
- `unknown paragraph style '...'; word/styles.xml defines no paragraph style with that id`, `No character style '...' in word/styles.xml`, `No paragraph style '...' in word/styles.xml`: check `unzip -p file.docx word/styles.xml | grep styleId`.
- `No such table/row in the document as loaded; use tables to inspect indexes`.
- `This row is already a tracked deletion; accept or reject that revision instead`.
- `Rows N to M of table T are joined by a vertical merge; insert before row N or after row M instead` and `Row N of table T is inside a vertical merge spanning rows N to M; split the merge in Word first`.
- `Reject or accept the row deletion before editing its contents`: the cell belongs to a row the counterparty deleted.
- `has no paragraph N in the document as loaded`: stale number; run `list` on the file this batch starts from.
- `warning: author '...' already appears in this document`: the name belongs to someone already in the file. Not fatal, but `verify` and `finalize` refuse that name as the trusted author when it already appears in the original.

## verify

`verify original.docx edited.docx [--resolved LOG ...] [--author NAME ...] [--prior-round] [--formatting] [--json]`

Compares the edited file to the original and fails unless every difference is a tracked change by a trusted author (`--author`, else `REDLINE_AUTHOR`; repeat the flag for a file touched by more than one of our names), or a counterparty change accounted for in the resolution log. A name that is already a revision or comment author in the original is refused before anything is compared, in one line (`verify failed: author '...' already appears in the original ...`): the trusted author cannot be a party to the original. The one legitimate case is round two of a negotiation, where the original is the counterparty's return of our earlier draft and carries our name: pass `--prior-round` and those earlier revisions are baseline. The log at `edited.docx.resolved.json` loads on its own; `--resolved` adds others. Failure kinds: `untracked_edit` (text or whitespace changed without markup, including Word's footnote and endnote separators), `untracked_paragraph_add`, `untracked_paragraph_delete`, `mutated_revision` (a counterparty revision's text, author, date, or position changed, including a paragraph they inserted that now follows different text), `untracked_resolution`, `wrong_author`, `untrusted_author` (the name passed as `--author` is a revision or comment author in the original), `wrong_resolution_log`, `log_mismatch` (the log says accept or reject but the document shows the opposite), `untracked_comment_edit` (a counterparty comment's text, author, date, or anchor changed), `untracked_comment_delete`, `untracked_comment_add`, `untracked_comment_status` (a thread resolved or reopened without a logged decision), `untracked_object_change` (a hyperlink target, field code, footnote or endnote reference, picture, object, symbol, or special hyphen removed, added, duplicated, or moved within its paragraph outside the agent's markup, or text newly wrapped in or unwrapped from a hyperlink), `hidden_insertion` (text the agent inserted is formatted hidden). Warnings: tracking off, markup hidden.

Replays logged decisions, including comment status decisions, against the original before comparing the body, headers, footers, footnotes, endnotes, and comment text. Revision placement is checked even when IDs were renumbered, and comments are matched by content when Word renumbered them. Partial decisions without their log fail verification. A tracked rejection is demanded only while it stands: withdrawing our reversal (`reject --id <ours>`, logged with `withdraws`), or a later whole accept or untracked reject of the same revision, ends the demand, and the revision is judged by that later decision. Text inside a deletion nested in their insertion counts as struck, whoever struck it, and an object inside our deletion is deleted with markup, not removed; a note whose reference deletion was accepted is gone from the expected document, as in Word. `--formatting` adds the formatting comparison (`untracked_formatting`); without it, formatting-only changes are not checked.

## comment and note

`comment input output --paragraph N --text "..." [--find "..."] [--story NAME] [--author NAME]`
`comment input output --reply-to ID --text "..."`
`comment input output --comments comments.json`
`note input output --paragraph N --text "..." [--find "..."] [--story NAME] [--author NAME]`
`note input output --reply-to ID --text "..."`

`--find` anchors the comment to exactly that text as the paragraph reads with markup shown: the accepted text with the deleted text in place. Copy live words from `list` and deleted words from `revisions`. A span inside a deletion, theirs or our tracked reversal, anchors there with the range inside the deletion; a span that reads across a deletion (the accepted words on both sides, as `list` shows them) still matches; a span may cross hyperlinks, fields, line breaks, and the counterparty's insertions. Runs are split at the boundaries so the highlighted range is the words named and nothing around them, and a run carrying a formatting revision keeps it on every piece. The reference mark is written after the insertion or deletion the range ends in, so the comment survives when they accept or reject that revision. `--occurrence N` counts matches in document order as shown. Without `--find` the whole paragraph is anchored; text inside a deleted row is deleted text, so anchor the whole paragraph there. A newline in `--text` is a line break in the comment. A reply (`--reply-to`) shares the anchor of the comment it answers and takes no `--paragraph` or `--find`; giving one is refused. `note` is `comment --internal`: the author and body are marked so `scrub` and `clean` remove it. Refusals: `could not find '...' to anchor the comment (copy it from list, or from revisions for deleted words)`, `--paragraph and --find do not apply with --reply-to`, `No comment with id N to reply to`.

## resolve-comment and reopen-comment

`resolve-comment input output --id N [--author NAME]`
`reopen-comment input output --id N [--author NAME]`

Mark a comment thread resolved (Word's "Resolve", `w15:done`) or open again. The id may be the root or any reply; the whole thread changes together. Text, author, date, replies, and anchors are untouched. The decision is appended to the resolution log with the previous state, and `verify` replays it; a thread whose status changed without a log entry is `untracked_comment_status`. Refusals: `No comment with id N`, `Refusing to overwrite the input file`.

## accept, reject, resolve

`accept input output --id N [--find TEXT] [--log PATH] [--author NAME]`
`reject input output --id N [--find TEXT] [--untracked] [--log PATH] [--author NAME]`
`resolve input output --actions '[{"id":"12","action":"accept"},{"id":"34","action":"reject"},{"id":"56","action":"reject","untracked":true}]'`

Act on a counterparty revision by id from `revisions`.

**Accept** is Word's Accept: their markup is removed and the text becomes agreed wording. Accepting a deletion that holds a footnote or endnote reference removes the note with it, as Word does.

**Reject** leaves their revision pending and writes our reversal beside it as a tracked change under `--author`, so the counterparty sees what we reversed. Their insertion is struck under our name: our `w:del` is nested inside their `w:ins`, the shape Word writes when someone deletes text another author inserted. The words they struck come back as our `w:ins` right after their deletion, copied exactly with their run formatting. An inserted paragraph mark gets our deleted mark beside theirs; a deleted mark is answered by re-splitting the paragraph with our inserted mark in front of it; an inserted row gets our row deletion beside theirs, as `delete_row` writes it; a deleted row is followed by our copy of it with the cell text as our insertions. The copy carries what the deletion carried: run formatting, footnote references (the same footnote, whose struck text comes back as our insertion beside theirs), fields, content controls, pictures (the same image, a fresh drawing id), and nested tables; a deletion inside a hyperlink is restored inside it. Only an embedded object, a VML shape, or a text box cannot be copied, and the refusal names the id. Accept All and Reject All of the returned file then both read as the original did. Rejecting their insertion withdraws any restoration of ours for a deletion nested inside it, and rejecting a deletion nested in an insertion we already struck in full changes nothing (the line says so), so a reject-all batch reads as the original in either order. While our reversal of a revision stands, accept and a second reject of it are refused; reject our reversal by its id to withdraw it first. Moves are one decision: accept or reject either half and both halves are resolved together and the empty move markers removed; a tracked reject reverses both halves. The command prints `reject ins N as a tracked change`. Rejecting a revision we authored withdraws it, as Word does; the log records which revision of theirs the withdrawal reopens, so it can be decided again. Accepting a revision we authored is refused (it would turn our tracked edit into untracked text): leave it tracked, or reject it. A formatting revision cannot carry two authors' decisions, so rejecting one restores the old properties, as Word does.

`--untracked` (`"untracked": true` in a `resolve` action) is Word's Reject: their markup is removed, the text returns to the original wording, and nothing shows. Only on instruction. Refused with `accept`.

Add `"find": "<span>"` in a `resolve` action, or `--find` on `accept`/`reject`, to act on part of a revision. With `accept` and with `--untracked`, the named span is resolved and the rest stays tracked under the counterparty. With the default `reject`, only that span is struck or restored and their revision keeps its id. Partial resolution supports direct text runs, including fragmented text, tabs and line breaks. The span may sit beside a nested revision, a hyperlink, a field, or a content control inside the same revision; a span that overlaps one of them, or a pending formatting revision, is refused before writing and the message names it. A move cannot be resolved in part.

Each decision, including repeated partial decisions on the same revision, appends an event to the resolution log at `output.resolved.json`, which every later command carries forward and `verify` reads; a rejection written as a tracked change is recorded with `"tracked": true` and the ids of our reversal markup as `"reversal_ids"`; withdrawing a reversal (rejecting our own revision) records `"withdraws"`: the id it reopens. `verify` fails with `log_mismatch` when a standing tracked rejection's revision is gone or our reversal is missing. Each command prints one line per decision naming every revision it also resolved (a consumed paragraph text, the other half of a move, a withdrawn restoration). A batch is all-or-nothing: a refusal names the revision and nothing is written. Refusals: `No tracked revision with id N`, `Revision N was already decided earlier in this batch`, `Revision N carries our tracked rejection (M); reject --id M to withdraw it first`, `Revision N is our own tracked change`, `No actions given`, `Unsupported action`, `Revision does not contain '...'`, `The span overlaps a nested revision|hyperlink|content control|field`, `find cannot target part of a move`, `Unsupported field '...' in resolve spec`, `untracked only applies to reject`, `Rejecting deletion N as a tracked change would copy an embedded object|a VML picture or shape|a text box` (reject it with `--untracked`, or restore the text with an `apply` insert).

## scrub

`scrub input output`

Removes internal notes only. Keeps every tracked change and every customer-facing comment. Run before anything leaves for the counterparty.

## clean

`clean input output [--keep-comments]`

Accepts every tracked change, including the counterparty's, and removes all comments; `--keep-comments` keeps customer-facing comments and still removes internal notes. Matches what Word's Accept All produces, including dropping a footnote whose reference deletion is accepted. For the signature copy only; never verify a clean copy.

## validate

`validate file.docx [--original ORIGINAL] [--schema auto|required|off] [--json]`

Checks the package structure without changing it: every XML part parses; every part has a content type and every relationship resolves; every relationship id used in a part exists; revision ids are unique and carry author and date; `w:t` never sits inside a deletion and `w:delText` only inside one; comment anchors are paired and ordered, every reference has a body, and every comment body, replies included, has its range start, range end and reference run in some story (a body without them is invisible in Word); footnotes and endnotes each have a paragraph, no note's last paragraph mark is a tracked deletion, and a note whose every reference is struck has its text struck too; comment part ids are consistent; paragraph ids are valid; tracking is on and markup shown (reported as a warning here, a failure in `finalize`). With `lxml` installed the WordprocessingML, content-types, and relationship parts are also validated against the ECMA-376 schemas; `--schema required` refuses to run without it, `--schema off` skips it. `--original` runs the same checks on the original and reports only defects that are new in this file, listing the rest as pre-existing. Prints `OK` or `FAIL` with one line per defect (`- check @ part: message`). Exit 0 clean, 1 defects, 2 the check could not run.

## render

`render file.docx OUT_DIR [--original ORIGINAL] [--json]`

Renders every page with LibreOffice in the markup view and, from a temporary clean copy, the final view: `page-01.png`, `page-01.final.png`, and with `--original` also `page-01.before.png` and `page-01.diff.png` (changed pixels marked), plus `pages.json` with image hashes and the changed fraction per page, and `renderer.log`. `OUT_DIR` must be new or a previous render directory. Mechanical checks on the rendered text: every revision of ours appears in the markup render (`render_markup_missing`) and every paragraph we changed reads correctly in the final render (`render_wording_missing`; a row we deleted is expected to be absent from it, and field results such as page numbers and dates are regenerated by the renderer, so the text on either side of a field is checked on its own); `render_incomplete` means the last paragraph of the body is not on any page in the markup or final view, so the page set cannot be trusted (LibreOffice drops everything after a text box placed directly after a table; put a paragraph between them); `renderer_missing` and `render_failed` name the tool and the command tried. Page differences are advisory and never fail. Needs LibreOffice and Poppler. Exit 0 or 1.

## finalize

`finalize original.docx draft.docx final.docx [--pages DIR] [--author NAME ...] [--prior-round] [--resolved LOG ...] [--json]`

Makes the send file from the approved draft and gates it on the exact bytes written. Steps, in order: strip internal notes into `final.docx` and set its view (Track Changes on, All Markup shown, whatever view the draft was saved in); check the settings; `verify` with the formatting comparison against the original, with the draft's resolution log; `validate --schema required` with the original as baseline; the optional Word-rules conformance check when `REDLINE_OPENXML_VALIDATE` is set; `render` every page into `final.docx.pages/` (or `--pages DIR`). It writes a manifest `final.docx.finalize.json` binding the result to hashes of the original, the draft, the logs, and every page image. Prints the status: `inspect` when every automatic check passed, followed by the page image paths to open; `failed` with the failures when any check failed, in which case the send file is deleted and only the manifest and images remain. Fails closed on its required dependencies: a missing `lxml`, LibreOffice or Poppler is a failure of kind `dependency_missing`. The optional Word-rules layer is different — when it is off, finalize reports `not checked: ...` and still produces the send file. A failure prints one line per failure (`kind @ location: message`) and a `next:` block with the step for each kind; with `--json` the same data comes as the report. Run `finalize` again after fixing the draft: when the send path holds a file this command wrote for it that was never attested and has not changed since, the file and its resolution log are removed and the checks run on the new draft, which then needs a new inspection. Refusals (exit 2): the send path is an input; the send path holds a file that was attested `ready` (it may already have been sent: finalize to a new path such as `final-2.docx`), a file that changed after finalize wrote it, or a file finalize did not write; the send path has a resolution log that no finalize run wrote; an input is missing; the candidate changed while checks ran. `--author` (repeatable) and `--resolved` are only for files written under another name, or two of our names, or with logs elsewhere; `--prior-round` is for round two, when the original is the counterparty's return of our earlier draft. A draft that arrives without its `.resolved.json` gets an empty log bound to the original and the status line says so (`note: ...`); a counterparty revision accepted or rejected in such a draft then fails `verify` as `untracked_resolution`, so restore the sidecar instead.

## attest

`attest final.docx --pages all|1,3-5 [--by NAME]`

Records that every page image was opened and read, in the markup and final views. Only a file whose manifest says `inspect` can be attested, and only for the complete page list: a shorter list is refused with `Inspect all page numbers [...]`. On success the manifest moves to `ready` with the pages, the name, and the time, and the command prints `ready`. Exit 0 or 1.

## status

`status final.docx`

Prints `ready` (exit 0) only when the manifest says ready, every page was attested, and the file on disk still has the attested hash. Otherwise it prints why (exit 1): `awaiting inspection of pages ...`, `file changed since finalize`, `status is failed`, or `No readable finalization manifest`. Send only a file that prints `ready`, and send that exact file.
