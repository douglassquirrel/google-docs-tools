"""Straight quotes and odd dashes in a document's paragraphs, for check-typography. Pure.

A quote at the start of a paragraph, or after a space, an opening bracket or a dash, opens (“ ‘);
any other closes (” ’, the apostrophe too). A double hyphen, and a hyphen with a space each side,
become an en dash. Link text that is itself a web address, and a merge tag in doubled brackets,
are left out. Every proposed form is only shown: nothing here changes a document.
"""
import re
from collections import namedtuple

from googledocstools.notes import beginning

KINDS = ("quotes", "dashes")
Finding = namedtuple("Finding", "place beginning fixes")  # fixes: [(as it is, as it would be)]

OPENS_AFTER = "([{“‘—–-/"
MERGE_TAG = re.compile(r"\[\[[^\[\]]*\]\]")
DOUBLE_HYPHEN = re.compile(r"-{2,}")
SPACED_HYPHEN = re.compile(r"(?<=\s)-(?=\s)")


def chosen(text):
    """The checks named in a comma list, in its order; ValueError if any is not known, one is
    named twice, or there are none."""
    kinds = tuple(part.strip() for part in text.split(",") if part.strip())
    if not kinds:
        raise ValueError("no check is named; name quotes, dashes or both")
    for kind in kinds:
        if kind not in KINDS:
            raise ValueError("%r is not a check; the checks are quotes and dashes" % kind)
    if len(set(kinds)) != len(kinds):
        raise ValueError("a check is named twice")
    return kinds


def _shown(paragraph):
    """The paragraph's text with what is not looked at blanked out, the same length."""
    shown = ""
    for span in paragraph.spans:
        is_address = span.link and re.match(r"https?://", span.text.strip())
        shown += " " * len(span.text) if is_address else span.text
    return MERGE_TAG.sub(lambda found: " " * len(found.group()), shown)


def _changes(shown, kinds):
    """What would change, by position: {position: what goes there instead ("" to drop it)}."""
    changes = {}
    if "quotes" in kinds:
        for position, character in enumerate(shown):
            if character in "\"'":
                opens = position == 0 or shown[position - 1].isspace() or (
                    shown[position - 1] in OPENS_AFTER)
                changes[position] = {('"', True): "“", ('"', False): "”",
                                     ("'", True): "‘", ("'", False): "’"}[character, opens]
    if "dashes" in kinds:
        for found in DOUBLE_HYPHEN.finditer(shown):
            changes[found.start()] = "–"
            changes.update((position, "") for position in range(found.start() + 1, found.end()))
        for found in SPACED_HYPHEN.finditer(shown):
            changes[found.start()] = "–"
    return changes


def _fixes(text, changes):
    """Each run of words side by side that would change, with the word before and after it: [(as
    it is, as it would be)]."""
    words = list(re.finditer(r"\S+", text))
    touched = [any(word.start() <= position < word.end() for position in changes)
               for word in words]
    fixes, number = [], 0
    while number < len(words):
        if not touched[number]:
            number += 1
            continue
        last = number
        while last + 1 < len(words) and touched[last + 1]:
            last += 1
        start = words[max(number - 1, 0)].start()
        end = words[min(last + 1, len(words) - 1)].end()
        before = text[start:end]
        after = "".join(changes.get(position, text[position]) for position in range(start, end))
        fixes.append((" ".join(before.split()), " ".join(after.split())))
        number = last + 1
    return fixes


def _as_heading(paragraph, text):
    """A heading as read-doc writes it ("## Text"), or None for a paragraph that is not one."""
    if paragraph.kind == "TITLE":
        return "# " + text
    if paragraph.kind.startswith("HEADING_"):
        return "#" * int(paragraph.kind[len("HEADING_"):]) + " " + text
    return None


def findings(paragraphs, kinds):
    """Each paragraph with something to fix, in order, as a Finding: where it is (under the nearest
    heading above, after the paragraph before, or at the start), its first words, and its fixes."""
    found, heading, before = [], None, None
    for paragraph in paragraphs:
        if paragraph.kind in ("RULE", "UNWRITTEN"):
            continue
        text = "".join(span.text for span in paragraph.spans)
        if not text.strip():
            continue
        changes = _changes(_shown(paragraph), kinds)
        if changes:
            place = ('under "%s"' % heading if heading else
                     'after "%s"' % beginning(before) if before else "at the start")
            found.append(Finding(place, beginning(text), _fixes(text, changes)))
        heading = _as_heading(paragraph, beginning(text)) or heading
        before = text
    return found
