"""New paragraphs for insert-paragraphs: read from a file, placed beside a paragraph, and the one
change that puts them there. Pure: the document is as the Docs API describes it.

The file is in read-doc's markup: # to ###### for a heading, - for a bulleted list item, plain
paragraphs, **bold**, *italic* and [links](https://…), a blank line between paragraphs. A heading
is one line; a list item or a plain paragraph goes on over the lines after it until a blank line,
a heading or another item.
"""
import re
from collections import namedtuple

from googledocstools.document import CLEARED as LOOK
from googledocstools.document import find, paragraphs, units
from googledocstools.editing import stretches, under_a_suggestion
from googledocstools.markup import MarkupError, inline

# Taken off new text, so it has the look its paragraph's kind gives: all but a link are what
# Google's own text style holds, the font and its size included.
CLEARED = LOOK + ",fontSize,weightedFontFamily"
# Set on each new paragraph: its kind, and the rest left to what its kind gives.
KINDS = ("namedStyleType,alignment,lineSpacing,spaceAbove,spaceBelow,indentFirstLine,indentStart,"
         "indentEnd")
BULLETS = "BULLET_DISC_CIRCLE_SQUARE"  # Google's preset for a plain bulleted list

New = namedtuple("New", "kind item spans")
# Where the new paragraphs go: the paragraph holding the words, from start to end, whether it is a
# list item, its text, and whether the paragraph right after it is a list item (None when nothing
# new can go in before what follows: the end of the body, a table).
Anchor = namedtuple("Anchor", "start end bullet text following")

HEADING = re.compile(r"(#+)(?:\s+(.*))?$")
ITEM = re.compile(r"-(?:\s+(.*))?$")
NUMBERED = re.compile(r"\d+\.\s")
DROPPED = re.compile("[\x00-\x08\x0b-\x1f\ue000-\uf8ff]")  # what Google strips from text put in


class ContentError(Exception):
    """The file of new paragraphs cannot be used; problems names every fault."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


class AnchorProblem(Exception):
    """The words do not say one paragraph the new ones can go beside. Worded for the person."""


def anchor(described, words):
    """The paragraph holding the words, once, outside tables and suggestions."""
    touches = '"%s" touches text in a pending suggestion; accept or reject it first.' % words
    places = find(described, words)
    if not places and under_a_suggestion(stretches(described), words):
        raise AnchorProblem(touches)
    if not places:
        raise AnchorProblem('"%s" is not in the document. Copy the words exactly, from within '
                            "one paragraph." % words)
    if len(places) > 1:
        raise AnchorProblem('"%s" is in the document %d times, and must be there exactly once: '
                            "give more of the words." % (words, len(places)))
    start, end = places[0]
    content = described["body"]["content"]
    for number, structural in enumerate(content):
        if "paragraph" in structural and structural["startIndex"] <= start < structural["endIndex"]:
            break
    else:
        raise AnchorProblem('"%s" is in a table; new paragraphs go only beside a paragraph '
                            "outside tables." % words)
    elements = structural["paragraph"]["elements"]
    for element in elements:
        run = element.get("textRun", {})
        if (element["startIndex"] < end and element["endIndex"] > start
                and (run.get("suggestedInsertionIds") or run.get("suggestedDeletionIds"))):
            raise AnchorProblem(touches)
    text = "".join(element.get("textRun", {}).get("content", "") for element in elements)
    return Anchor(structural["startIndex"], structural["endIndex"],
                  "bullet" in structural["paragraph"], text.rstrip("\n"),
                  "bullet" in content[number + 1]["paragraph"]
                  if number + 1 < len(content) and "paragraph" in content[number + 1] else None)


def requests_for(place, new, before):
    """The requests that put the new paragraphs beside the place, before or after it.

    Every character put in is new: before, at the place's start; after, at the start of the
    paragraph that follows, so the place keeps its own line break (and with it what Google ties to
    the paragraph, like a heading's link from a table of contents). Only after the last paragraph
    of the body do they go in before its line break. Google gives new paragraphs the paragraph
    style, bullet included, of the paragraph where they go in, and new text the look of the text
    before it: both are taken off again, and each new paragraph is given its own kind.
    """
    body = "\n".join("".join(span.text for span in paragraph.spans) for paragraph in new)
    if before:
        at, text, first, copied = place.start, body + "\n", place.start, place.bullet
    elif place.following is not None:
        at, text, first, copied = place.end, body + "\n", place.end, place.following
    else:
        at, text, first, copied = place.end - 1, "\n" + body, place.end, place.bullet
    last = first + units(body) + 1  # the end of the last new paragraph
    made = [
        {"insertText": {"location": {"index": at}, "text": text}},
        {"updateTextStyle": {"range": _between(first, last - 1), "textStyle": {},
                             "fields": CLEARED}},
    ]
    marked, items, position = [], [], first
    for paragraph in new:
        start = position
        for span in paragraph.spans:
            style = {}
            if span.bold:
                style["bold"] = True
            if span.italic:
                style["italic"] = True
            if span.link:
                style["link"] = {"url": span.link}
            if style:
                marked.append({"updateTextStyle": {
                    "range": _between(position, position + units(span.text)),
                    "textStyle": style, "fields": ",".join(style)}})
            position += units(span.text)
        position += 1  # the line break
        made.append({"updateParagraphStyle": {
            "range": _between(start, position), "paragraphStyle": {"namedStyleType": paragraph.kind},
            "fields": KINDS}})
        if paragraph.item and items and items[-1][1] == start:
            items[-1][1] = position
        elif paragraph.item:
            items.append([start, position])
    if copied:
        made.append({"deleteParagraphBullets": {"range": _between(first, last)}})
    return made + marked + [
        {"createParagraphBullets": {"range": _between(start, end), "bulletPreset": BULLETS}}
        for start, end in items]


def _between(start, end):
    return {"startIndex": start, "endIndex": end}


def not_there(described, words, new, before):
    """The numbers (from 1) of the new paragraphs not standing beside the words as written: each
    must have its kind, be a list item or not, and have its words with their bold, italic and
    links. All of them when the words are not in the document once."""
    found = paragraphs(described)
    holding = [number for number, paragraph in enumerate(found)
               if words in "".join(span.text for span in paragraph.spans)]
    if len(holding) != 1:
        return list(range(1, len(new) + 1))
    at = holding[0]
    beside = found[max(at - len(new), 0):at] if before else found[at + 1:at + 1 + len(new)]
    if before:
        beside = [None] * (len(new) - len(beside)) + beside
    return [number for number, (wanted, there) in enumerate(zip(new, beside + [None] * len(new)),
                                                            start=1)
            if there is None or (there.kind, bool(there.mark), _letters(there.spans))
            != (wanted.kind, wanted.item, _letters(wanted.spans))]


def _letters(spans):
    """Text as its characters, each with how it looks: so pieces split differently compare."""
    return [(character, span.bold, span.italic, span.link)
            for span in spans for character in span.text]


def parse_content(text):
    """The new paragraphs written in the file, in order; or ContentError naming every fault."""
    problems = []  # (line number, what is wrong, with its line)

    def fault(number, said):
        problems.append((number, "line %d: %s" % (number, said)))

    blocks = []  # [kind, item, [(line number, words)], open to more lines]
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        for character in DROPPED.findall(line):
            fault(number, "a character Google would drop (U+%04X)" % ord(character))
        words = line.strip()
        heading, item = HEADING.match(words), ITEM.match(words)
        if not words:
            if blocks:
                blocks[-1][3] = False
        elif heading:
            if len(heading.group(1)) > 6:
                fault(number, "a heading has one to six #, not %d" % len(heading.group(1)))
            elif not (heading.group(2) or "").strip():
                fault(number, "a heading with no words")
            else:
                blocks.append(["HEADING_%d" % len(heading.group(1)), False,
                               [(number, heading.group(2).strip())], False])
        elif item and line[:1].isspace():
            fault(number, "a list item inside another (indented) cannot be put in yet")
        elif item:
            if not (item.group(1) or "").strip():
                fault(number, "a list item with no words")
            else:
                blocks.append(["NORMAL_TEXT", True, [(number, item.group(1).strip())], True])
        elif NUMBERED.match(words):
            fault(number, "a numbered list item cannot be put in yet; only - for a bulleted one")
        elif blocks and blocks[-1][3]:
            blocks[-1][2].append((number, words))
        else:
            blocks.append(["NORMAL_TEXT", False, [(number, words)], True])
    found = []
    for kind, item, lines, _ in blocks:
        try:
            found.append(New(kind, item, inline(lines)))
        except MarkupError as error:  # its message starts with the line it is about
            problems.append((lines[0][0], str(error)))
    if problems:
        raise ContentError([said for _, said in sorted(problems)])
    if not found:
        raise ContentError(["there are no paragraphs in it"])
    return found
