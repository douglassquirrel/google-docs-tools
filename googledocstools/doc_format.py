"""A Google Doc checked against a house format, and the change that sets it right, for
check-doc-format. Pure: the document is as the Docs API describes it.

What a paragraph has is what it sets itself, else what its named style sets in the document, else
what normal text's named style sets, else Google's default; the same for each piece of its text.
A fix sets formatting only: never a character of text, never a heading's level, and never bold or
italic in body text, list items or footnotes, which are the author's emphasis.

A footnote's paragraphs are in a segment of their own, whose positions count from 0; they are
Normal text, with the size Google sets on the footnote's own text (seen 27 November 2026).
"""
import json
import re
from collections import namedtuple

from googledocstools.document import _paragraphs_in
from googledocstools.notes import beginning

Problem = namedtuple("Problem", "group place beginning paragraph")  # paragraph: its start, or None
Fix = namedtuple("Fix", "place beginning said requests")
# left_out: how many paragraphs before start_at were left out (None with no start_at, or when the
# document has no paragraph of that kind)
Checked = namedtuple("Checked", "problems fixes left_out start_at", defaults=(None, None))

HEADINGS = ("title",) + tuple("heading_%d" % level for level in range(1, 7))
TEXT_KEYS = ("font", "size", "line_spacing", "first_line_indent_inches", "left_indent_inches")
HEADING_KEYS = ("font", "size", "bold", "colour", "alignment", "page_break_before",
                "keep_with_next", "pattern")
PARTS = dict({"page": ("size", "margins_inches"), "body": TEXT_KEYS, "list": TEXT_KEYS,
              "footnote": TEXT_KEYS},
             **{name: HEADING_KEYS for name in HEADINGS})
ALIGNMENTS = {"left": "START", "centre": "CENTER", "right": "END", "justified": "JUSTIFIED"}
PAGES = {"letter": (612.0, 792.0), "a4": (595.276, 841.89)}  # points
MARGINS = ("marginTop", "marginBottom", "marginLeft", "marginRight")
SHOWN_PART = dict({"body": "body text", "list": "list items", "title": "title",
                   "footnote": "footnote"},
                  **{"heading_%d" % level: "heading %d" % level for level in range(1, 7)})
LOOKS_LIKE_A_HEADING_WORDS = 15
# A tab typed at a paragraph's start carries its first line on past the first-line indent, to the
# next tab stop (three paragraphs of a book, 27 November 2026), so the fix leaves such an indent.
TABBED = "starts with a tab: take it out, the first-line indent does that"


class FormatError(Exception):
    """The format file cannot be used: problems names every fault in it."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def _number(value, least=None, above=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return (least is None or value >= least) and (above is None or value > above)


def _fault(part, key, value):
    """What is wrong with one value in the format file, or None."""
    if part == "page" and key == "size":
        if (isinstance(value, str) and value in PAGES) or (isinstance(value, list) and len(value) == 2 and all(
                _number(side, above=0) for side in value)):
            return None
        return '"size" must be letter, a4 or [width, height] in inches'
    if key == "margins_inches":
        return None if _number(value, least=0) else (
            '"margins_inches" must be a number of inches, 0 or more')
    if key == "font":
        return None if isinstance(value, str) and value.strip() else (
            '"font" must be the name of a font')
    if key in ("size", "line_spacing"):
        return None if _number(value, above=0) else '"%s" must be a number above 0' % key
    if key in ("first_line_indent_inches", "left_indent_inches"):
        return None if _number(value, least=0) else (
            '"%s" must be a number of inches, 0 or more' % key)
    if key in ("bold", "page_break_before", "keep_with_next"):
        return None if isinstance(value, bool) else '"%s" must be true or false' % key
    if key == "colour":
        return None if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else (
            '"colour" must be #rrggbb, such as #000000 for black')
    if key == "alignment":
        return None if value in ALIGNMENTS else (
            '"alignment" must be one of %s' % ", ".join(ALIGNMENTS))
    try:  # the pattern
        re.compile(value if isinstance(value, str) else "(")
    except re.error as error:
        return '"pattern" is not a regular expression: %s' % error
    return None


def parse_format(text):
    """The house format in a format file's text, or FormatError naming every fault."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise FormatError(["not JSON: %s" % error])
    if not isinstance(data, dict):
        raise FormatError(["the file must hold a JSON object, {\"body\": {...}, ...}"])
    if not set(data) - {"start_at"}:
        raise FormatError(["the file names nothing to check"])
    problems = []
    if "start_at" in data and data["start_at"] not in HEADINGS:
        problems.append('"start_at" must be title or heading_1 to heading_6: the first paragraph '
                        "of that kind, before which nothing is checked")
    for part, wanted in data.items():
        if part == "start_at":
            continue
        if part not in PARTS:
            problems.append('unknown part "%s"; the parts are %s' % (part, ", ".join(PARTS)))
            continue
        if not isinstance(wanted, dict):
            problems.append("%s: must be an object of settings" % part)
            continue
        for key, value in wanted.items():
            if key not in PARTS[part]:
                problems.append('%s: unknown key "%s"' % (part, key))
                continue
            fault = _fault(part, key, value)
            if fault:
                problems.append("%s: %s" % (part, fault))
    if problems:
        raise FormatError(problems)
    return data


# What each setting is in Google's terms: how to read it from a style, Google's default, how to
# put it in a request, and how to say it.

def _font(style):
    return style.get("weightedFontFamily", {}).get("fontFamily")


def _size(style):
    return style.get("fontSize", {}).get("magnitude")


def _colour(style):
    if "foregroundColor" not in style:
        return None
    rgb = style["foregroundColor"].get("color", {}).get("rgbColor", {})
    return "#" + "".join("%02x" % round(rgb.get(part, 0.0) * 255)
                         for part in ("red", "green", "blue"))


def _rgb(colour):
    return {"color": {"rgbColor": {part: int(colour[1 + 2 * n:3 + 2 * n], 16) / 255
                                   for n, part in enumerate(("red", "green", "blue"))}}}


def _figure(number):
    return ("%g" % number) if isinstance(number, float) else str(number)


def _on(value):
    return "on" if value else "off"


# (format key, Google's field, read it from a style, Google's default, the value to send,
#  how the wanted value is said, whether a reading matches the wanted value)
TEXT_SETTINGS = (
    ("font", "weightedFontFamily", _font, "Arial", lambda v: {"fontFamily": v},
     lambda v: "font %s" % v, lambda have, want: have == want),
    ("size", "fontSize", _size, 11, lambda v: {"magnitude": v, "unit": "PT"},
     lambda v: "size %s pt" % _figure(v), lambda have, want: abs(have - want) < 0.01),
    ("bold", "bold", lambda style: style.get("bold"), False, lambda v: v,
     lambda v: "bold %s" % _on(v), lambda have, want: bool(have) == want),
    ("colour", "foregroundColor", _colour, "#000000", _rgb,
     lambda v: "colour %s" % v.lower(), lambda have, want: have.lower() == want.lower()),
)
PARAGRAPH_SETTINGS = (
    ("line_spacing", "lineSpacing", lambda style: style.get("lineSpacing"), 100,
     lambda v: round(v * 100, 2), lambda v: "line spacing %s" % _figure(v),
     lambda have, want: abs(have - want * 100) < 0.5),
    ("first_line_indent_inches", "indentFirstLine",
     lambda style: style.get("indentFirstLine", {}).get("magnitude"), 0,
     lambda v: {"magnitude": v * 72, "unit": "PT"},
     lambda v: "first-line indent %s in" % _figure(v),
     lambda have, want: abs(have - want * 72) < 0.5),
    # Measured from the margin, as the first-line indent is (seen 27 November 2026).
    ("left_indent_inches", "indentStart",
     lambda style: style.get("indentStart", {}).get("magnitude"), 0,
     lambda v: {"magnitude": v * 72, "unit": "PT"},
     lambda v: "left indent %s in" % _figure(v),
     lambda have, want: abs(have - want * 72) < 0.5),
    ("alignment", "alignment", lambda style: style.get("alignment"), "START",
     lambda v: ALIGNMENTS[v], lambda v: "alignment %s" % v,
     lambda have, want: have == ALIGNMENTS[want]),
    ("page_break_before", "pageBreakBefore", lambda style: style.get("pageBreakBefore"), False,
     lambda v: v, lambda v: "page break before %s" % _on(v),
     lambda have, want: bool(have) == want),
    ("keep_with_next", "keepWithNext", lambda style: style.get("keepWithNext"), False,
     lambda v: v, lambda v: "keep with next %s" % _on(v), lambda have, want: bool(have) == want),
)


SETTING_NAMES = ("first-line indent", "left indent", "line spacing", "page break before", "keep with next",
                 "font", "size", "bold", "colour", "alignment")


def _not(said):
    """'font Times New Roman' as a problem: 'font not Times New Roman'. Every setting's saying
    starts with one of SETTING_NAMES."""
    name = next(name for name in SETTING_NAMES if said.startswith(name + " "))
    return "%s not %s" % (name, said[len(name) + 1:])


class _Styles:
    """The document's named styles, and what a paragraph or a piece of text has, they included."""

    def __init__(self, described):
        self.named = {style.get("namedStyleType"): style
                      for style in described.get("namedStyles", {}).get("styles", [])}

    def _chain(self, kind, which, own):
        return [own, self.named.get(kind, {}).get(which, {}),
                self.named.get("NORMAL_TEXT", {}).get(which, {})]

    def value(self, kind, which, own, read, default):
        for style in self._chain(kind, which, own):
            found = read(style)
            if found is not None:
                return found
        return default


def _part(paragraph):
    kind = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
    if kind == "TITLE":
        return "title"
    if kind.startswith("HEADING_"):
        return "heading_" + kind[len("HEADING_"):]
    if kind == "NORMAL_TEXT":
        return "list" if paragraph.get("bullet") else "body"
    return None


def _page(described, wanted):
    """The page's problems and its fix, if any."""
    style = described.get("documentStyle", {})
    problems, said, document_style = [], [], {}
    if "size" in wanted:
        size = wanted["size"]
        named = isinstance(size, str)
        width, height = PAGES[size] if named else (size[0] * 72, size[1] * 72)
        shown = size if named else "%s × %s in" % (_figure(size[0]), _figure(size[1]))
        have = style.get("pageSize", {})
        have_width = have.get("width", {}).get("magnitude", 612.0)
        have_height = have.get("height", {}).get("magnitude", 792.0)
        if abs(have_width - width) >= 0.5 or abs(have_height - height) >= 0.5:
            problems.append(Problem("page: size not %s" % shown, None, "", None))
            said.append("size %s" % shown)
            document_style["pageSize"] = {"width": {"magnitude": width, "unit": "PT"},
                                          "height": {"magnitude": height, "unit": "PT"}}
    if "margins_inches" in wanted:
        points = wanted["margins_inches"] * 72
        if any(abs(style.get(name, {}).get("magnitude", 72.0) - points) >= 0.5
               for name in MARGINS):
            shown = "%s in" % _figure(wanted["margins_inches"])
            problems.append(Problem("page: margins not %s" % shown, None, "", None))
            said.append("margins %s" % shown)
            document_style.update((name, {"magnitude": points, "unit": "PT"}) for name in MARGINS)
    fixes = [Fix(None, "", said, [{"updateDocumentStyle": {
        "documentStyle": document_style, "fields": ",".join(document_style)}}])] if said else []
    return problems, fixes


def _paragraph(styles, structural, part, wanted, place, first_words, body_size, segment=None):
    """One paragraph's problems, and the fix for those that can be fixed. In a footnote, segment
    is its id, and the paragraph is known in a problem by (the id, its start)."""
    paragraph = structural["paragraph"]
    kind = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
    shown_part = SHOWN_PART[part]
    runs = [element["textRun"] for element in paragraph["elements"] if "textRun" in element
            and element["textRun"].get("content", "").strip("\n")]
    text = "".join(run["content"] for run in runs).rstrip("\n")
    problems, said, text_style, paragraph_style = [], [], {}, {}

    start, end = structural.get("startIndex", 0), structural["endIndex"]  # Google leaves out a 0

    def problem(what):
        problems.append(Problem("%s: %s" % (shown_part, what), place, first_words,
                                start if segment is None else (segment, start)))

    def between(first, last):
        found = {"startIndex": first, "endIndex": last}
        if segment is not None:
            found["segmentId"] = segment
        return found

    for key, field, read, default, sent, saying, matches in TEXT_SETTINGS:
        if key not in wanted:
            continue
        if not all(matches(styles.value(kind, "textStyle", run.get("textStyle", {}), read,
                                        default), wanted[key]) for run in runs):
            problem(_not(saying(wanted[key])))
            said.append(saying(wanted[key]))
            text_style[field] = sent(wanted[key])
    tabbed = part in ("body", "list", "footnote") and text.lstrip(" ").startswith("\t")
    for key, field, read, default, sent, saying, matches in PARAGRAPH_SETTINGS:
        if key in wanted and not matches(styles.value(
                kind, "paragraphStyle", paragraph.get("paragraphStyle", {}), read, default),
                wanted[key]):
            problem(_not(saying(wanted[key])))
            if not (tabbed and field == "indentFirstLine"):
                said.append(saying(wanted[key]))
                paragraph_style[field] = sent(wanted[key])
    if tabbed:
        problem(TABBED)
    if "pattern" in wanted and not re.search(wanted["pattern"], text):
        problem("does not match %s" % wanted["pattern"])
    if part == "body" and text.strip() and len(text.split()) <= LOOKS_LIKE_A_HEADING_WORDS:
        bold = all(styles.value(kind, "textStyle", run.get("textStyle", {}),
                                lambda style: style.get("bold"), False) for run in runs)
        large = body_size is not None and all(
            styles.value(kind, "textStyle", run.get("textStyle", {}), _size, 11) >= body_size + 2
            for run in runs)
        if bold or large:
            problem("looks like a heading")
    requests = []
    # Google drops a piece's own bold when its font is set (seen 22 November 2026): bold to be set
    # goes in after the font, and otherwise each piece that was bold of its own is made bold
    # again, in the same change.
    after_font = {}
    if "weightedFontFamily" in text_style and "bold" in text_style:
        after_font = {"bold": text_style.pop("bold")}
    for style in (text_style, after_font):
        if style:
            requests.append({"updateTextStyle": {
                "range": between(start, end - 1), "textStyle": style,
                "fields": ",".join(style)}})
    if "weightedFontFamily" in text_style and not after_font:
        for element in paragraph["elements"]:
            if element.get("textRun", {}).get("textStyle", {}).get("bold") and (
                    element["startIndex"] < end - 1):
                requests.append({"updateTextStyle": {
                    "range": between(element.get("startIndex", 0),
                                     min(element["endIndex"], end - 1)),
                    "textStyle": {"bold": True}, "fields": "bold"}})
    if paragraph_style:
        requests.append({"updateParagraphStyle": {
            "range": between(start, end), "paragraphStyle": paragraph_style,
            "fields": ",".join(paragraph_style)}})
    return problems, [Fix(place, first_words, said, requests)] if requests else []


def check(described, fmt):
    """Every way the document differs from the format, in order (the page first), and the fixes
    for those that can be fixed."""
    styles = _Styles(described)
    problems, fixes = _page(described, fmt.get("page", {}))
    names_headings = any(name in fmt for name in HEADINGS)
    body_size = fmt.get("body", {}).get("size")
    heading, before = None, None
    start_at = fmt.get("start_at")
    all_paragraphs = list(_paragraphs_in(described["body"]["content"]))
    first = next((number for number, structural in enumerate(all_paragraphs)
                  if _part(structural["paragraph"]) == start_at and _text(structural).strip()),
                 None) if start_at else None
    marks = []  # the footnotes whose marks are in paragraphs that are checked, in order
    for number, structural in enumerate(all_paragraphs):
        paragraph = structural["paragraph"]
        text = _text(structural)
        part = _part(paragraph)
        if first is None or number >= first:
            marks += [element["footnoteReference"] for element in paragraph["elements"]
                      if "footnoteReference" in element]
        place = ('under "%s"' % heading if heading else
                 'after "%s"' % beginning(before) if before else "at the start")
        if (first is not None and number < first) or not text.strip():
            pass  # the front matter, or a paragraph with nothing in it to format
        elif part in HEADINGS and part not in fmt and names_headings:
            problems.append(Problem("%s: a level the format does not name" % SHOWN_PART[part],
                                    place, beginning(text), structural["startIndex"]))
        elif part in fmt:
            found, fixed = _paragraph(styles, structural, part, fmt[part], place,
                                      beginning(text), body_size)
            problems += found
            fixes += fixed
        if text.strip():
            if part in HEADINGS:
                level = 1 if part == "title" else int(part[len("heading_"):])
                heading = "#" * level + " " + beginning(text)
            before = text
    for reference in marks if "footnote" in fmt else []:
        note_id = reference.get("footnoteId")
        place = "footnote %s" % reference.get("footnoteNumber", "")
        note = described.get("footnotes", {}).get(note_id, {})
        for structural in _paragraphs_in(note.get("content", [])):
            text = _text(structural)
            if text.strip():
                found, fixed = _paragraph(styles, structural, "footnote", fmt["footnote"], place,
                                          beginning(text), body_size, note_id)
                problems += found
                fixes += fixed
    return Checked(problems, fixes, first, start_at)


def _text(structural):
    """A paragraph's text, without its line break."""
    return "".join(element.get("textRun", {}).get("content", "")
                   for element in structural["paragraph"]["elements"]).rstrip("\n")


def _counted(number, noun):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


def report(checked, verbose=False, shown=3):
    """The problems grouped by what is wrong, then a result line."""
    groups = {}
    for found in checked.problems:
        groups.setdefault(found.group, []).append(found)
    lines = []
    for group, found in groups.items():
        if found[0].place is None:
            lines.append(group)
            continue
        lines.append("%s: %s" % (group, _counted(len(found), "paragraph")))
        listed = found if verbose else found[:shown]
        lines += ["  %s: %s" % (one.place, one.beginning) for one in listed]
        if len(found) > len(listed):
            lines.append("  … and %d more (-v shows them all)" % (len(found) - len(listed)))
    if checked.start_at:
        named = SHOWN_PART[checked.start_at]
        lines.append("Left out: %s before the first %s." % (
            _counted(checked.left_out, "paragraph"), named) if checked.left_out is not None else
            "Left out: nothing; the document has no %s." % named)
    if not checked.problems:
        lines.append("Format: everything matches.")
    else:
        paragraphs = {found.paragraph for found in checked.problems if found.paragraph is not None}
        page = any(found.paragraph is None for found in checked.problems)
        lines.append("Format: %s in %s%s." % (
            _counted(len(checked.problems), "problem"), _counted(len(paragraphs), "paragraph"),
            " and the page" if page else ""))
    return "\n".join(lines) + "\n"
