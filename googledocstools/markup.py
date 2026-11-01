"""The markup of a text file for fill-weekly-email: paragraphs, bold, italic, links."""
import bisect
import itertools
import re
from collections import namedtuple

Span = namedtuple("Span", "text bold italic link highlight", defaults=(False, False, None, False))


class MarkupError(Exception):
    """The text file cannot be read as text with this markup. Worded for the person."""


def parse(text):
    """The paragraphs of the text, each a list of Spans."""
    paragraphs = []
    lines = []  # the paragraph being gathered: (line number, the line without its edges)
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n") + [""], start=1):
        if line.strip():
            lines.append((number, line.strip()))
        elif lines:
            paragraphs.append(_inline(lines))
            lines = []
    if not paragraphs:
        raise MarkupError("there is no text in it")
    return paragraphs


_TOKEN = re.compile(r"\*+|\[([^\[\]]*)\]\(")


def _address(text, begin):
    """A link's address starting at text[begin]: (the address, where the text goes on), or None.

    It ends at the ) that balances the ( before it, so an address may hold brackets of its own.
    """
    depth = 0
    for index in range(begin, len(text)):
        if text[index].isspace():
            return None
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            if depth == 0:
                return text[begin:index], index + 1
            depth -= 1
    return None


def _inline(lines):
    """The pieces of one paragraph, with their marks. Its lines are joined with one space."""
    text = " ".join(line for _, line in lines)

    starts = [0]  # where each line begins in the joined text
    for _, line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)

    def line_of(offset):
        return lines[bisect.bisect_right(starts, offset) - 1][0]

    spans = []

    def scan(begin, end, link, outer):
        """Read text[begin:end]: a whole paragraph, or (with link set) one link's text."""
        opened = {}  # "**" or "*" -> where it was opened, within this stretch
        start = position = begin

        def piece(upto):
            if upto > start:
                marks = set(opened) | outer
                spans.append(Span(text[start:upto], "**" in marks, "*" in marks, link))

        while True:
            found = _TOKEN.search(text, position, end)
            if not found:
                break
            mark = found.group()
            position = found.end()
            if mark.startswith("["):
                if not found.group(1).strip():
                    raise MarkupError("line %d: a link here has no text between its square "
                                      "brackets" % line_of(found.start()))
                address = _address(text, found.end())
                if not address:
                    raise MarkupError("line %d: the link %r has no closing ) after its address"
                                      % (line_of(found.end() - 1), found.group(1)))
                if not re.fullmatch(r"https?://\S+", address[0]):
                    raise MarkupError("line %d: the link %r goes to %r, which does not start "
                                      "http:// or https://" % (line_of(found.end() - 1),
                                                               found.group(1), address[0]))
                piece(found.start())
                scan(found.start(1), found.end(1), address[0], set(opened) | outer)
                start = position = address[1]
                continue
            before = text[found.start() - 1] if found.start() > begin else " "
            after = text[found.end()] if found.end() < end else " "
            can_open = not after.isspace() and not before.isalnum()
            can_close = not before.isspace() and not after.isalnum()
            if not (can_close if mark in opened else can_open):
                continue  # not at the edge of a word: ordinary characters
            if len(mark) > 2:
                raise MarkupError("line %d: three or more asterisks together (%r) could mean "
                                  "several things; use ** for bold and * for italic, one inside "
                                  "the other" % (line_of(found.start()), mark))
            piece(found.start())
            if mark in opened:
                del opened[mark]
            else:
                opened[mark] = found.start()
            start = found.end()
        for mark, offset in opened.items():
            where = "inside the link's text" if link else "before the end of its paragraph"
            raise MarkupError("line %d: %r is opened here and never closed %s"
                              % (line_of(offset), mark, where))
        piece(end)

    scan(0, len(text), None, set())
    return spans


def _edges(text):
    """Text as (the spaces before it, itself, the spaces after it)."""
    inside = text.strip()
    if not inside:
        return text, "", ""
    start = text.index(inside)
    return text[:start], inside, text[start + len(inside):]


def render(spans, highlights=False):
    """One paragraph's pieces written back in the markup parse() reads.

    Spaces at the edge of a marked or linked piece go outside its marks, where parse() wants
    them.
    """
    written = []
    for link, pieces in itertools.groupby(spans, key=lambda span: span.link):
        text = ""
        for span in pieces:
            marks = ("**" if span.bold else "") + ("*" if span.italic else "")
            before, inside, after = _edges(span.text)
            if highlights and span.highlight and inside:
                inside = "{==" + inside + "==}"
            text += before + (marks + inside + marks if inside else "") + after
        if link is not None:
            before, inside, after = _edges(text)
            text = before + "[%s](%s)" % (inside, link) + after
        written.append(text)
    return "".join(written)
