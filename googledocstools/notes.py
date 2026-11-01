"""Notes and placeholders in a document's paragraphs, between markers that are data. Pure.

From online-publishing-tools' check.py (1 November 2026), its markers made settings."""
import re
from collections import namedtuple

# doubled: whether text in doubled note markers, such as a merge tag, is left out.
Markers = namedtuple("Markers", "note_open note_close placeholder_open placeholder_close doubled",
                     defaults=("[", "]", "{", "}", True))
USUAL = Markers()

AROUND = 4  # words shown on each side of a note


def _between(opening, closing, doubled=False):
    """What finds text between two markers, with neither marker in it; never doubled ones if
    doubled. The markers are data: they are escaped, whatever they hold."""
    first, last = re.escape(opening), re.escape(closing)
    inside = "(?:(?!%s|%s).)*" % (first, last)
    if doubled:
        return re.compile("(?<!%s)%s%s%s(?!%s)" % (first, first, inside, last, last), re.DOTALL)
    return re.compile(first + inside + last, re.DOTALL)


def _text(paragraph):
    return "".join(span.text for span in paragraph.spans)


def beginning(text, words=8):
    """The first few words of some text, with a mark if there are more."""
    parts = text.split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def _around(text, start, end):
    """The text from start to end with a few words on each side, marked where there are more."""
    before = re.search(r"(?:\S+\s+){0,%d}\S*$" % AROUND, text[:start]).start()
    after = end + re.match(r"\S*(?:\s+\S+){0,%d}" % AROUND, text[end:]).end()
    return "%s%s%s" % ("…" if text[:before].strip() else "", " ".join(text[before:after].split()),
                       "…" if text[after:].strip() else "")


def notes(paragraphs, markers=USUAL):
    """Every note, in order: (the note, a few words around it)."""
    finding = _between(markers.note_open, markers.note_close, markers.doubled)
    found = []
    for paragraph in paragraphs:
        text = _text(paragraph)
        shown = ""  # the paragraph's text with links that show their own address blanked out
        for span in paragraph.spans:
            is_address = span.link and re.match(r"https?://", span.text.strip())
            shown += " " * len(span.text) if is_address else span.text
        found += [(match.group(), _around(text, match.start(), match.end()))
                  for match in finding.finditer(shown)]
    return found


def placeholders(paragraphs, markers=USUAL):
    """How many placeholders there are."""
    finding = _between(markers.placeholder_open, markers.placeholder_close)
    return sum(len(finding.findall(_text(paragraph))) for paragraph in paragraphs)
