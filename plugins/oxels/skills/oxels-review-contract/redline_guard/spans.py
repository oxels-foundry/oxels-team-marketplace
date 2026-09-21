"""Exact text boundaries without flattening runs, hyperlinks, or revision wrappers."""

from copy import deepcopy
from xml.etree import ElementTree as ET

from redline_guard.ooxml import final_char_map, parent_map_from, q, set_text_node, w_attr


def find_span(paragraph, find: str, occurrence: int = 1) -> tuple[int, int]:
    if not isinstance(find, str) or not find:
        raise ValueError("A non-empty find string is required.")
    if type(occurrence) is not int or occurrence < 1:
        raise ValueError("occurrence must be a positive integer.")
    text = "".join(ref.char for ref in final_char_map(paragraph))
    start = -1
    for _ in range(occurrence):
        start = text.find(find, start + 1)
        if start < 0:
            raise ValueError(f"Could not find {find!r} (occurrence {occurrence}).")
    return start, start + len(find)


def _pending_change(run):
    """The run's pending rPrChange, whoever made it."""
    return run.find(f"{q('rPr')}/{q('rPrChange')}")


def _split_at(paragraph, index, author=None, allocator=None):
    """Split the run holding character ``index`` so the character starts a run.

    A one-character node (tab, break, non-breaking or soft hyphen, ``w:sym``)
    is never split inside: it goes whole to the piece it belongs to, so a span
    boundary falls before or after it.
    """
    refs = final_char_map(paragraph)
    if index <= 0 or index >= len(refs) or refs[index - 1].run is not refs[index].run:
        return
    ref = refs[index]
    run = ref.run
    change = _pending_change(run)
    if change is not None and allocator is None:
        raise ValueError("Splitting a run with a pending formatting change needs an id allocator for the copy.")
    left, right = ET.Element(run.tag, run.attrib), ET.Element(run.tag, run.attrib)
    pr = run.find(q("rPr"))
    if pr is not None:
        left.append(deepcopy(pr))
        right.append(deepcopy(pr))
        if change is not None:
            # Word keeps the formatting revision on both pieces, whoever made
            # it: same author, date and old properties; the second piece
            # needs its own id.
            right.find(f"{q('rPr')}/{q('rPrChange')}").set(w_attr("id"), allocator.allocate())
    passed = False
    for child in run:
        if child.tag == q("rPr"):
            continue
        if child is ref.text_node:
            passed = True
            if child.tag in {q("t"), q("delText")}:
                for dest, text in ((left, (child.text or "")[:ref.offset]), (right, (child.text or "")[ref.offset:])):
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


def isolate_span(paragraph, start: int, end: int, author=None, allocator=None):
    """Return selected runs in document order. All non-text children survive.

    A run carrying a pending rPrChange (ours or the counterparty's) is split
    like any other when an allocator is given: each piece keeps the change,
    with a fresh id on the new piece, which is how Word writes it.
    """
    refs = final_char_map(paragraph)
    if not 0 <= start < end <= len(refs):
        raise ValueError("Text range is empty or out of bounds.")
    # Validate both boundaries before changing either of them.
    for index in (start, end):
        if 0 < index < len(refs) and refs[index - 1].run is refs[index].run:
            if _pending_change(refs[index].run) is not None and allocator is None:
                raise ValueError("Splitting a run with a pending formatting change needs an id allocator for the copy.")
    _split_at(paragraph, end, author, allocator)
    _split_at(paragraph, start, author, allocator)
    return list(dict.fromkeys(ref.run for ref in final_char_map(paragraph)[start:end]))
