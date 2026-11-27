"""Footnotes, for insert-footnote and read-doc --footnotes. Pure: the document is as the Docs API
describes it.

A footnote's mark is an element of its own in the body, one position wide; the footnote's text is
a segment of its own, whose positions count from 0, and which Google starts with a space (seen 27
November 2026). Text is read and written in read-doc's markup.
"""
import re
from collections import namedtuple

from googledocstools.document import find, paragraphs, units
from googledocstools.editing import stretches, under_a_suggestion
from googledocstools.inserting import DROPPED
from googledocstools.markup import MarkupError, inline, render

AROUND_LISTED = 6  # words shown before a footnote's mark when the footnotes are listed


# A new footnote's mark: where it goes, the (start, end) of the words taken out there (None for
# none), and the text of its stretch of the paragraph up to it.
Mark = namedtuple("Mark", "at removal before")
# A mark in the document: its reference, the text of its paragraph before it, its position, and
# the text straight after it, up to the next thing that is not text.
Found = namedtuple("Found", "reference before index after")


class TextError(Exception):
    """The footnote's text cannot be used. Worded for the person."""


class MarkProblem(Exception):
    """The words do not say one place for a mark. Worded for the person."""


def _marks(described):
    """Every footnote mark in the body, in order, as Found. Paragraphs in tables are read in
    their place."""
    found = []

    def walk(content):
        for structural in content:
            for row in structural.get("table", {}).get("tableRows", []):
                for cell in row.get("tableCells", []):
                    walk(cell.get("content", []))
            before, following = "", None  # following: the mark whose text after is gathered
            for element in structural.get("paragraph", {}).get("elements", []):
                if "textRun" in element:
                    text = element["textRun"].get("content", "").rstrip("\n")
                    before += text
                    if following is not None:
                        following[3] += text
                elif "footnoteReference" in element:
                    following = [element["footnoteReference"], before,
                                 element.get("startIndex", 0), ""]
                    found.append(following)
                else:
                    following = None

    walk(described["body"]["content"])
    return [Found(*mark) for mark in found]


def words_before(text, count):
    """The last count words of text, led by … when there are more."""
    words = re.findall(r"\S+\s*", text.rstrip())
    return ("…" if len(words) > count else "") + "".join(words[-count:])


def note_text(described, note_id):
    """A footnote's text in the markup, its paragraphs joined with " / ", Google's leading space
    left off; None when the document does not describe that footnote."""
    note = described.get("footnotes", {}).get(note_id)
    if note is None:
        return None
    found = paragraphs({"body": {"content": note.get("content", [])},
                        "lists": described.get("lists", {})})
    return " / ".join(render(paragraph.spans).strip() for paragraph in found
                      if paragraph.spans)


def listed(described):
    """A line for each footnote, in the order of the marks: 'N | …words before | its text'."""
    return ["%s | %s | %s" % (reference.get("footnoteNumber", ""),
                              words_before(before, AROUND_LISTED),
                              note_text(described, reference.get("footnoteId")) or "")
            for reference, before, _, _ in _marks(described)]



def parse_text(text):
    """The footnote's words as Spans, read in the markup; or TextError saying what is wrong."""
    if not text.strip():
        raise TextError("--text needs the footnote's words.")
    if "\n" in text or "\r" in text:
        raise TextError("--text: a footnote here is one paragraph, with no line break.")
    dropped = DROPPED.search(text)
    if dropped:
        raise TextError("--text: it holds a character Google would drop (U+%04X)."
                        % ord(dropped.group()))
    try:
        return inline([(1, text.strip())])
    except MarkupError as error:
        raise TextError("--text: %s." % re.sub(r"^line \d+: ", "", str(error)))


def place(described, words, remove):
    """Where the mark goes: straight after the words, found once within one stretch of a
    paragraph's text, with remove's words, if given, taken out from there; or MarkProblem."""
    touches = '"%s" touches text in a pending suggestion; accept or reject it first.'
    texts = stretches(described)
    matches = []
    for stretch in texts:
        text = "".join(character.text for character in stretch)
        at = text.find(words)
        while at >= 0:
            matches.append((stretch, text, at + len(words)))
            at = text.find(words, at + len(words))
    if not matches and under_a_suggestion(texts, words):
        raise MarkProblem(touches % words)
    if not matches:
        raise MarkProblem('"%s" is not in the document. Copy the words exactly, from within one '
                          "paragraph." % words)
    if len(matches) > 1:
        raise MarkProblem('"%s" is in the document %d times, and must be there exactly once: give '
                          "more of the words." % (words, len(matches)))
    stretch, text, end = matches[0]
    if any(character.suggested for character in stretch[end - len(words):end]):
        raise MarkProblem(touches % words)
    at = stretch[end - 1].index + units(stretch[end - 1].text)
    removal = None
    if remove is not None:
        if not text[end:].startswith(remove):
            raise MarkProblem('"%s" is not straight after "%s", so it cannot be removed with the '
                              "mark put in its place." % (remove, words))
        if any(character.suggested for character in stretch[end:end + len(remove)]):
            raise MarkProblem(touches % remove)
        removal = (at, at + units(remove))
    return Mark(at, removal, text[:end])


def mark_requests(mark):
    """The first change: the words taken out, if any, then the mark made where they began."""
    made = []
    if mark.removal:
        made.append({"deleteContentRange": {"range": {"startIndex": mark.removal[0],
                                                      "endIndex": mark.removal[1]}}})
    return made + [{"createFootnote": {"location": {"index": mark.at}}}]


def text_requests(note_id, spans):
    """The second change: the text put into the footnote after Google's space, then its italic,
    bold and links set."""
    made = [{"insertText": {"location": {"segmentId": note_id, "index": 1},
                            "text": "".join(span.text for span in spans)}}]
    position = 1
    for span in spans:
        style = {}
        if span.bold:
            style["bold"] = True
        if span.italic:
            style["italic"] = True
        if span.link:
            style["link"] = {"url": span.link}
        if style:
            made.append({"updateTextStyle": {
                "range": {"segmentId": note_id, "startIndex": position,
                          "endIndex": position + units(span.text)},
                "textStyle": style, "fields": ",".join(style)}})
        position += units(span.text)
    return made


def _letters(spans):
    return [(character, span.bold, span.italic, span.link)
            for span in spans for character in span.text]


def check(described, words, remove, note_id, spans):
    """Whether the new footnote stands as asked: (its number, or None if its mark is not found
    after the words; what is missing, [] for nothing)."""
    places = find(described, words)
    if len(places) != 1:
        return None, ['"%s" is not in the document once' % words]
    for mark in _marks(described):
        if mark.reference.get("footnoteId") == note_id and mark.index == places[0][1]:
            break
    else:
        return None, ['the footnote\'s mark is not straight after "%s"' % words]
    missing = []
    if remove and mark.after.startswith(remove):
        missing.append('"%s" is still straight after the mark' % remove)
    note = described.get("footnotes", {}).get(note_id, {})
    found = paragraphs({"body": {"content": note.get("content", [])}})
    there = _letters(found[0].spans)[1:] if len(found) == 1 else None
    if there != _letters(spans):
        missing.append("the footnote's text is not as written")
    return mark.reference.get("footnoteNumber"), missing
