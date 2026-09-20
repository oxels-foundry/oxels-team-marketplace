"""Create Word property revisions, retaining an explicit previous-state snapshot."""

from copy import deepcopy
import re
from xml.etree import ElementTree as ET

from redline_guard.ooxml import FORMAT_CHANGE_TAGS, final_char_map, q, style_ids, w_attr
from redline_guard.spans import find_span, isolate_span

RUN_ORDER = "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange".split()
PARA_ORDER = "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange".split()
# ST_Underline (ECMA-376 17.18.99), the list Word's Underline style menu offers.
UNDERLINE_VALUES = ("single", "words", "double", "thick", "dotted", "dottedHeavy", "dash", "dashedHeavy", "dashLong", "dashLongHeavy", "dotDash", "dashDotHeavy", "dotDotDash", "dashDotDotHeavy", "wave", "wavyHeavy", "wavyDouble", "none")
# w:spacing before/after are unsigned; w:ind left/right are signed
# (ST_SignedTwipsMeasure) and firstLine/hanging unsigned but mutually exclusive.
_MEASURES = {"space_before": "before", "space_after": "after", "indent_left": "left", "indent_right": "right", "first_line": "firstLine", "hanging": "hanging"}
_UNSIGNED = {"space_before", "space_after"}
# Attributes that express the same dimension another way and would compete.
_ALIASES = {"before": ("beforeLines", "beforeAutospacing"), "after": ("afterLines", "afterAutospacing"), "left": ("leftChars", "start", "startChars"), "right": ("rightChars", "end", "endChars"), "firstLine": ("firstLineChars",), "hanging": ("hangingChars",)}
# The opposite indent, replaced only when a value is set, not when clearing.
_EXCLUSIVE = {"firstLine": ("hanging", "hangingChars"), "hanging": ("firstLine", "firstLineChars")}


def _value(name, value, mapping):
    if value not in mapping:
        raise ValueError(f"Invalid {name}: {value!r}; expected one of {', '.join(mapping)}.")
    return value


def _properties(properties, paragraph=False):
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object.")
    names = ({"style": "pStyle", "alignment": "jc", "keep_next": "keepNext", "keep_lines": "keepLines", "page_break_before": "pageBreakBefore", "space_before": "spacing", "space_after": "spacing", "indent_left": "ind", "indent_right": "ind", "first_line": "ind", "hanging": "ind"}
             if paragraph else {"bold": "b", "italic": "i", "strike": "strike", "underline": "u", "font": "rFonts", "size": "sz", "color": "color", "highlight": "highlight", "style": "rStyle", "superscript": "vertAlign"})
    unknown = set(properties) - names.keys()
    if unknown:
        raise ValueError(f"Unsupported formatting properties: {', '.join(sorted(unknown))}.")
    result = []
    for name, value in properties.items():
        attrs = {}
        partial = None
        if name in _MEASURES:
            partial = _MEASURES[name]
            if value is not None and type(value) is not int:
                raise ValueError(f"{name} must be an integer in twips or null.")
            if name in _UNSIGNED and value is not None and value < 0:
                raise ValueError(f"{name} must be a non-negative integer in twips or null.")
            if value is not None and value < 0 and partial in _EXCLUSIVE:
                # Word stores a negative first-line indent as a hanging indent,
                # and the reverse; CT_Ind has no signed form of either.
                partial = "hanging" if partial == "firstLine" else "firstLine"
                value = -value
            attrs = {partial: str(value)}
        elif value is not None:
            if name in {"bold", "italic", "strike", "keep_next", "keep_lines", "page_break_before", "superscript"}:
                if type(value) is not bool:
                    raise ValueError(f"{name} must be true, false, or null.")
                attrs = {"val": ("superscript" if value else "baseline") if name == "superscript" else ("1" if value else "0")}
            elif name == "size":
                if type(value) not in (int, float) or not 1 <= value <= 1638 or value * 2 != int(value * 2):
                    raise ValueError("size must be points in half-point increments from 1 to 1638.")
                attrs = {"val": str(int(value * 2))}
            elif name == "color":
                if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{6}|auto", value):
                    raise ValueError("color must be six hex digits or 'auto'.")
                attrs = {"val": value}
            elif name == "underline":
                if type(value) is bool:
                    value = "single" if value else "none"
                attrs = {"val": _value(name, value, UNDERLINE_VALUES)}
            elif name == "alignment":
                attrs = {"val": _value(name, value, ("left", "right", "center", "both", "distribute", "start", "end"))}
            elif name == "highlight":
                attrs = {"val": _value(name, value, ("black", "blue", "cyan", "green", "magenta", "red", "yellow", "white", "darkBlue", "darkCyan", "darkGreen", "darkMagenta", "darkRed", "darkYellow", "darkGray", "lightGray", "none"))}
            else:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be a non-empty string or null.")
                attrs = {"ascii": value, "hAnsi": value, "eastAsia": value, "cs": value} if name == "font" else {"val": value}
        result.append((names[name], None if value is None else attrs, partial))
    return result


def _check_style(para, style, kind):
    """A style id must exist in word/styles.xml with the right type.

    Word cannot pick a style the document does not define, and ignores a
    dangling id on open, so the tracked change would show a revision that
    changes nothing. Only checked when the paragraph knows its package.
    """
    package = getattr(para, "package", None)
    if style is None or package is None:
        return
    if style not in style_ids(package, kind):
        raise ValueError(f"No {kind} style {style!r} in word/styles.xml; use a {kind} style id the document defines.")


def _change(element, props_tag, changes, author, date, allocator):
    pr = element.find(q(props_tag))
    if pr is None:
        pr = ET.Element(q(props_tag))
        element.insert(0, pr)
    marker = pr.find(q(props_tag + "Change"))
    if marker is None and any(node.tag in FORMAT_CHANGE_TAGS for node in pr.iter()):
        raise ValueError("Accept or reject the existing formatting change before changing these properties again.")
    if marker is not None and marker.get(w_attr("author"), "") != author:
        raise ValueError(
            f"Accept or reject the pending formatting change by {marker.get(w_attr('author'), '')!r} before changing these properties."
        )
    if marker is not None:
        # A second change of ours on the same run or paragraph folds into the
        # first: Word records one revision per author whose snapshot is the
        # state before any of our changes.
        pr.remove(marker)
        old = deepcopy(marker[0]) if len(marker) else ET.Element(q(props_tag))
        old.tag = q(props_tag)
    else:
        old = deepcopy(pr)
    # Paragraph mark/section properties have independent histories and are not
    # allowed inside the CT_PPrBase snapshot of pPrChange.
    if props_tag == "pPr":
        for child in list(old):
            if child.tag in {q("rPr"), q("sectPr")}:
                old.remove(child)
    for name, attrs, partial in changes:
        node = pr.find(q(name))
        if partial:
            if node is None and attrs is not None:
                node = ET.SubElement(pr, q(name))
            if node is not None:
                # Explicit dimensions must override competing automatic/theme
                # values. The opposite indent (firstLine vs hanging) goes only
                # when a value replaces it; clearing one leaves the other.
                for key in (partial, *_ALIASES[partial]):
                    node.attrib.pop(w_attr(key), None)
                if attrs is not None:
                    for key in _EXCLUSIVE.get(partial, ()):
                        node.attrib.pop(w_attr(key), None)
                    node.set(w_attr(partial), attrs[partial])
                if not node.attrib and not len(node):
                    pr.remove(node)
            continue
        if node is not None:
            pr.remove(node)
        if attrs is not None:
            ET.SubElement(pr, q(name), {w_attr(k): v for k, v in attrs.items()})
    snapshot = deepcopy(pr)
    for child in list(snapshot):
        if props_tag == "pPr" and child.tag in {q("rPr"), q("sectPr")}:
            snapshot.remove(child)
    from redline_guard.formatting import _normalize
    if _normalize(snapshot) == _normalize(old):
        # Back to the original properties: nothing left to track.
        return
    rev_id = marker.get(w_attr("id")) if marker is not None else allocator.allocate()
    marker = ET.SubElement(pr, q(props_tag + "Change"), {w_attr("id"): rev_id, w_attr("author"): author, w_attr("date"): date})
    marker.append(old)
    order = RUN_ORDER if props_tag == "rPr" else PARA_ORDER
    rank = {q(name): i for i, name in enumerate(order)}
    pr[:] = sorted(pr, key=lambda node: rank.get(node.tag, len(rank)))


def apply_format(para, edit, author, date, allocator):
    paragraph = edit.type == "format_paragraph"
    changes = _properties(edit.properties, paragraph)
    _check_style(para, edit.properties.get("style"), "paragraph" if paragraph else "character")
    if paragraph:
        if edit.find:
            raise ValueError("format_paragraph applies to the whole paragraph; omit find.")
        _change(para.element, "pPr", changes, author, date, allocator)
        return
    start, end = find_span(para.element, edit.find, edit.occurrence)
    for ref in final_char_map(para.element)[start:end]:
        pending = ref.run.find(f"{q('rPr')}/{q('rPrChange')}")
        if pending is not None and pending.get(w_attr("author"), "") != author:
            raise ValueError(
                f"Accept or reject the pending formatting change by {pending.get(w_attr('author'), '')!r} before formatting this span."
            )
    for run in isolate_span(para.element, start, end, author, allocator):
        _change(run, "rPr", changes, author, date, allocator)
