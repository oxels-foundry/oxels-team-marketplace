"""Tracked row operations with stable, inspectable table/row coordinates."""

from xml.etree import ElementTree as ET

from redline_guard.ooxml import (
    INS_TAGS, DEL_TAGS, load_docx, make_tracked_insert,
    paragraph_texts, q, sanitize_copied_properties, w_attr,
)


def list_tables(path, story=None):
    package = load_docx(path)
    result = []
    for st in ([package.story(story)] if story else package.stories):
        for index, table in enumerate(st.root.iter(q("tbl")), 1):
            rows = []
            for number, row in enumerate(table.findall(q("tr")), 1):
                pr = row.find(q("trPr"))
                markers = [] if pr is None else [node for node in pr if node.tag in INS_TAGS | DEL_TAGS]
                deleted = any(node.tag in DEL_TAGS for node in markers)
                rows.append({"row": number, "cells": ["\n".join(_cell_paragraph_text(p, deleted) for p in cell.findall(q("p"))) for cell in row.findall(q("tc"))], "revisions": [{"id": n.get(w_attr("id")), "kind": n.tag.rsplit("}", 1)[-1]} for n in markers]})
            result.append({"story": st.name, "table": index, "rows": rows})
    return result


def _cell_paragraph_text(paragraph, row_deleted):
    """Cell text as the row reads with everything but a row deletion accepted.

    Word strikes the cell runs of a deleted row as well (``w:delText``); listing
    the accept view alone would show such a row as blank cells.
    """
    reject, accept, _revisions = paragraph_texts(paragraph)
    return accept or (reject if row_deleted else "")


def vertical_merge_spans(table):
    """Rows joined by ``w:vMerge``, as 0-based ``(first, last)`` pairs.

    Only the table's own rows count: a merge inside a nested table does not
    join the rows of the table around it. Cells are placed on the grid through
    ``w:gridSpan`` and ``w:gridBefore``, since a continuation must sit in the
    column of its restart. A continuation with nothing to continue is kept as
    a span of its own, so it still refuses edits.
    """
    spans = []  # [column, first, last]
    open_span = {}
    for index, row in enumerate(table.findall(q("tr"))):
        column = 0
        pr = row.find(q("trPr"))
        before = pr.find(q("gridBefore")) if pr is not None else None
        if before is not None and before.get(w_attr("val"), "").isdigit():
            column = int(before.get(w_attr("val")))
        for cell in row.findall(q("tc")):
            tcpr = cell.find(q("tcPr"))
            width = 1
            merge = None
            if tcpr is not None:
                grid = tcpr.find(q("gridSpan"))
                if grid is not None and grid.get(w_attr("val"), "").isdigit():
                    width = max(1, int(grid.get(w_attr("val"))))
                merge = tcpr.find(q("vMerge"))
            if merge is not None:
                current = open_span.get(column)
                continues = merge.get(w_attr("val"), "continue") != "restart"
                if continues and current is not None and spans[current][2] == index - 1:
                    spans[current][2] = index
                else:
                    open_span[column] = len(spans)
                    spans.append([column, index, index])
            column += width
    return [(first, last) for _column, first, last in spans]


def apply_row(table, row, edit, author, date, allocator):
    if row not in list(table):
        raise ValueError("The row is no longer in its original table.")
    rows = table.findall(q("tr"))
    index = rows.index(row)
    # Word's row operations work anywhere except through a vertical merge:
    # inserting between two rows one cell spans, or deleting a row inside the
    # span, would change the merge. Horizontal merges (gridSpan, legacy hMerge)
    # live within a row and are copied with the template's layout.
    spans = vertical_merge_spans(table)
    pr = row.find(q("trPr"))
    row_marks = [] if pr is None else [node for node in pr if node.tag in INS_TAGS | DEL_TAGS]
    if edit.type == "delete_row":
        # A row revision affects the row independently of its contents. Keeping
        # cell XML intact preserves comments and permits a lossless rejection.
        # Revisions inside the cells stay as they are, like text inside a
        # struck paragraph: they resolve with the row.
        if any(node.tag in DEL_TAGS for node in row_marks):
            raise ValueError("This row is already a tracked deletion; accept or reject that revision instead.")
        span = next((s for s in spans if s[0] <= index <= s[1]), None)
        if span is not None:
            if span[0] == span[1]:
                raise ValueError(f"Row {index + 1} of table {edit.table} carries a vertical merge (vMerge); split the merge in Word first.")
            raise ValueError(
                f"Row {index + 1} of table {edit.table} is inside a vertical merge spanning rows {span[0] + 1} to {span[1] + 1}; split the merge in Word first."
            )
        own = [node for node in row_marks if node.get(w_attr("author"), "") == author]
        if own:
            # Striking a row this author inserted withdraws the insertion.
            table.remove(row)
            return
        if pr is None:
            pr = ET.Element(q("trPr"))
            row.insert(0, pr)
        marker = ET.Element(q("del"), {w_attr("id"): allocator.allocate(), w_attr("author"): author, w_attr("date"): date})
        # CT_TrPr orders the counterparty's w:ins before our w:del (as with
        # paragraph marks), and both before any trPrChange.
        change = pr.find(q("trPrChange"))
        pr.insert(list(pr).index(change) if change is not None else len(pr), marker)
        return
    # insert_row copies properties, not content or history: a template row
    # with pending revisions is fine because the copies are sanitized.
    cells = row.findall(q("tc"))
    if not isinstance(edit.cells, list) or len(edit.cells) != len(cells) or not all(isinstance(s, str) for s in edit.cells):
        raise ValueError(f"insert_row needs cells: a list of {len(cells)} strings matching the template row.")
    if edit.position not in {"before", "after"}:
        raise ValueError("Row position must be 'before' or 'after'.")
    neighbour = index - 1 if edit.position == "before" else index + 1
    span = next((s for s in spans if s[0] <= min(index, neighbour) and max(index, neighbour) <= s[1]), None)
    if span is not None:
        raise ValueError(
            f"Rows {span[0] + 1} to {span[1] + 1} of table {edit.table} are joined by a vertical merge; insert before row {span[0] + 1} or after row {span[1] + 1} instead."
        )
    new = ET.Element(q("tr"))
    pr = sanitize_copied_properties(pr) if pr is not None else ET.Element(q("trPr"))
    new.append(pr)
    ET.SubElement(pr, q("ins"), {w_attr("id"): allocator.allocate(), w_attr("author"): author, w_attr("date"): date})
    for template, text in zip(cells, edit.cells):
        cell = ET.SubElement(new, q("tc"))
        tcpr = template.find(q("tcPr"))
        if tcpr is not None:
            copied = sanitize_copied_properties(tcpr)
            # The new row keeps the template's grid layout (gridSpan) but must
            # not join a vertical merge the template row belongs to.
            for merge in copied.findall(q("vMerge")):
                copied.remove(merge)
            cell.append(copied)
        p = ET.SubElement(cell, q("p"))
        sample_p = template.find(q("p"))
        ppr = sample_p.find(q("pPr")) if sample_p is not None else None
        if ppr is not None:
            p.append(sanitize_copied_properties(ppr))
        sample_run = next(template.iter(q("r")), None)
        if text:
            p.append(make_tracked_insert(text, author, date, allocator.allocate(), sample_run))
    index = list(table).index(row) + (edit.position == "after")
    # Successive inserts after one frozen row keep input order.
    if edit.position == "after":
        siblings = list(table)
        while index < len(siblings) and getattr(edit, "_inserted_rows", None) is not None and siblings[index] in edit._inserted_rows:
            index += 1
    table.insert(index, new)
    return new
