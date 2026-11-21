"""Finding a list of edits in a document and building the one change that makes them, for edit-doc.
Pure: the document is as the Docs API describes it, read with its suggestions inline.

An edit's words are found within one stretch of a paragraph's text: a picture, a chip or a
footnote mark breaks the text, as a paragraph's end does. Only the words that change are changed:
the words find and replace share at the start and the end are left alone.
"""
import re
from collections import namedtuple

from googledocstools.document import units

AROUND_WORDS = 3  # words shown on each side of an edit in its report
AROUND_CHECK = 15  # characters on each side looked for with an edit's new words afterwards
TOKEN = re.compile(r"\s+|\S+")

Character = namedtuple("Character", "index text suggested inserted", defaults=(False,))
Located = namedtuple("Located", "edit start old new found_start found_end shown_before "
                     "shown_after check_before check_after")


class EditProblems(Exception):
    """Edits that cannot be made; problems names each."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def narrowed(find, replace):
    """Where in find the change starts, and what is taken out and put in there, once the whole
    words the two share at their start and end are left alone: (offset, old, new)."""
    old, new = TOKEN.findall(find), TOKEN.findall(replace)
    first = 0
    while first < min(len(old), len(new)) and old[first] == new[first]:
        first += 1
    last = 0
    while last < min(len(old), len(new)) - first and old[-1 - last] == new[-1 - last]:
        last += 1
    offset = len("".join(old[:first]))
    return (offset, "".join(old[first:len(old) - last]), "".join(new[first:len(new) - last]))


def stretches(described):
    """Every stretch of text in the body, in order: a list of Characters each, without the
    paragraph's line break. Tables are read in their place."""
    found = []

    def walk(content):
        for structural in content:
            for row in structural.get("table", {}).get("tableRows", []):
                for cell in row.get("tableCells", []):
                    walk(cell.get("content", []))
            stretch = []
            for element in structural.get("paragraph", {}).get("elements", []):
                run = element.get("textRun")
                if run is None:
                    found.append(stretch)
                    stretch = []
                    continue
                inserted = bool(run.get("suggestedInsertionIds"))
                suggested = inserted or bool(run.get("suggestedDeletionIds"))
                at = element["startIndex"]
                for character in run.get("content", ""):
                    if character != "\n":
                        stretch.append(Character(at, character, suggested, inserted))
                    at += units(character)
            found.append(stretch)

    walk(described["body"]["content"])
    return [stretch for stretch in found if stretch]


def _words_before(text):
    """The last few words of the text before an edit, a word it starts inside counted as one."""
    words = re.findall(r"\S+\s*", text)
    return ("…" if len(words) > AROUND_WORDS else "") + "".join(words[-AROUND_WORDS:])


def _words_after(text):
    """The first few words of the text after an edit, a word it ends inside counted as one."""
    words = re.findall(r"\s*\S+", text)
    return "".join(words[:AROUND_WORDS]) + ("…" if len(words) > AROUND_WORDS else "")


def _plain_edge(characters, backwards):
    """Up to AROUND_CHECK characters next to an edit, stopping at text in a suggestion."""
    taken = []
    for character in (reversed(characters) if backwards else characters):
        if character.suggested or len(taken) == AROUND_CHECK:
            break
        taken.append(character.text)
    return "".join(reversed(taken) if backwards else taken)


def _place(stretch, at, edit):
    """The Located edit whose find starts at position at of the stretch."""
    offset, old, new = narrowed(edit.find, edit.replace)
    text = "".join(character.text for character in stretch)
    first, last = at + offset, at + offset + len(old)
    end = at + len(edit.find)
    return Located(
        edit, stretch[first].index if first < len(stretch) else stretch[-1].index + units(
            stretch[-1].text),
        old, new, stretch[at].index, stretch[end - 1].index + units(stretch[end - 1].text),
        _words_before(text[:first]), _words_after(text[last:]),
        _plain_edge(stretch[:first], True), _plain_edge(stretch[last:], False))


def under_a_suggestion(texts, find):
    """Whether the words are in the document as it would read with its suggestions accepted, or
    with them rejected: they are there, but a suggestion runs through them."""
    for stretch in texts:
        if not any(character.suggested for character in stretch):
            continue
        accepted = "".join(character.text for character in stretch
                           if character.inserted or not character.suggested)
        rejected = "".join(character.text for character in stretch if not character.inserted)
        if find in accepted or find in rejected:
            return True
    return False


def locate(described, edits):
    """Each edit placed in the document, in the order given; EditProblems naming every edit that
    is not there, there more than once without an occurrence, beyond its occurrence, touching a
    pending suggestion, or overlapping another."""
    texts = stretches(described)
    placed, problems = [], []
    for edit in edits:
        matches = []
        for stretch in texts:
            text = "".join(character.text for character in stretch)
            at = text.find(edit.find)
            while at >= 0:
                matches.append((stretch, at))
                at = text.find(edit.find, at + len(edit.find))
        if not matches and under_a_suggestion(texts, edit.find):
            problems.append('%s: "%s" touches text in a pending suggestion; accept or reject it '
                            "first" % (edit.name, edit.find))
            continue
        if not matches:
            problems.append('%s: "%s" is not in the document (an edit cannot run across a '
                            "paragraph break, a footnote mark, a chip or a picture)"
                            % (edit.name, edit.find))
            continue
        if edit.occurrence is None and len(matches) > 1:
            problems.append('%s: "%s" is in the document %d times; say which with "occurrence"'
                            % (edit.name, edit.find, len(matches)))
            continue
        if edit.occurrence is not None and edit.occurrence > len(matches):
            problems.append('%s: "%s" is in the document %d time%s, so there is no occurrence %d'
                            % (edit.name, edit.find, len(matches),
                               "" if len(matches) == 1 else "s", edit.occurrence))
            continue
        stretch, at = matches[(edit.occurrence or 1) - 1]
        if any(character.suggested for character in stretch[at:at + len(edit.find)]):
            problems.append('%s: "%s" touches text in a pending suggestion; accept or reject it '
                            "first" % (edit.name, edit.find))
            continue
        placed.append(_place(stretch, at, edit))
    ordered = sorted(placed, key=lambda located: located.found_start)
    for one, other in zip(ordered, ordered[1:]):
        if other.found_start < one.found_end:
            problems.append('%s and %s overlap: "%s" and "%s"' % (
                one.edit.name, other.edit.name, one.edit.find, other.edit.find))
    if problems:
        raise EditProblems(problems)
    return placed


def requests(located):
    """The requests that make every edit, from the end of the document backwards so that no
    edit moves another: for each, the old words taken out, then the new put in where they were."""
    made = []
    for edit in sorted(located, key=lambda located: located.start, reverse=True):
        if edit.old:
            made.append({"deleteContentRange": {"range": {
                "startIndex": edit.start, "endIndex": edit.start + units(edit.old)}}})
        if edit.new:
            made.append({"insertText": {"location": {"index": edit.start}, "text": edit.new}})
    return made


def report(located):
    """An edit's line, all but how it went: 'E3 | …words before[old → new]words after… |'."""
    return "%s | %s[%s → %s]%s |" % (located.edit.name, located.shown_before, located.old,
                                     located.new, located.shown_after)


def check_after(described, located):
    """The edits whose new words, with what stood next to them, are not in the document now."""
    text = "\n".join("".join(character.text for character in stretch)
                     for stretch in stretches(described))
    return [edit for edit in located
            if edit.check_before + edit.new + edit.check_after not in text]
