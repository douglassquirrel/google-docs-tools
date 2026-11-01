"""Snapshots of a document, and what changed since one. Pure: no files, no clock.

The comparison is from online-publishing-tools' snapshot.py (1 November 2026)."""
import difflib
import json
import re
from collections import namedtuple

from googledocstools.comments import alive, by, words_on
from googledocstools.notes import beginning

CONTEXT = 3  # words of what is the same shown on each side of a change
ALIKE = 0.5  # at least this much the same, word by word, and a paragraph is "changed"
_HEADING = re.compile(r"\s*(?:(?:-|[0-9]+\.) )?#+ ")


def _alike(one, other):
    """How much the words of two paragraphs are the same, the marks of bold and italic not
    counted, so that a word made plain is a change to its paragraph."""
    one, other = (text.replace("*", "") for text in (one, other))
    return difflib.SequenceMatcher(None, one.split(), other.split(), autojunk=False).ratio()


def word_diff(old, new):
    """The difference between two paragraphs word by word, with a little of what is the same."""
    before, after = old.split(), new.split()
    pieces = []
    for kind, a_from, a_to, b_from, b_to in difflib.SequenceMatcher(
            None, before, after, autojunk=False).get_opcodes():
        if kind == "equal":
            pieces.append(("same", before[a_from:a_to]))
            continue
        if a_to > a_from:
            pieces.append(("gone", before[a_from:a_to]))
        if b_to > b_from:
            pieces.append(("new", after[b_from:b_to]))
    shown = []
    for number, (kind, words) in enumerate(pieces):
        if kind == "gone":
            shown.append("{-%s-}" % " ".join(words))
        elif kind == "new" and number and pieces[number - 1][0] == "gone":
            shown[-1] += "{+%s+}" % " ".join(words)  # a replacement: the two together
        elif kind == "new":
            shown.append("{+%s+}" % " ".join(words))
        else:
            first = number == 0
            last = number == len(pieces) - 1
            if not first and not last:
                kept = words if len(words) <= 2 * CONTEXT else (
                    words[:CONTEXT] + ["…"] + words[-CONTEXT:])
            else:
                kept = words[-CONTEXT:] if first else words[:CONTEXT]
            shown.append(("…" if first and len(words) > CONTEXT else "") + " ".join(kept)
                         + ("…" if last and len(words) > CONTEXT else ""))
    return " ".join(shown)


def _blocks(text):
    """The paragraphs of a document's text: blocks separated by a blank line."""
    return [block for block in text.strip("\n").split("\n\n") if block]


def _place(blocks, number):
    """Where the paragraph at this position among blocks is: under the nearest heading above it,
    or after the paragraph before it, or at the start."""
    for block in reversed(blocks[:number]):
        if _HEADING.match(block):
            return 'under "%s"' % block
    return 'after "%s"' % beginning(blocks[number - 1]) if number else "at the start"


def changes(old_text, new_text):
    """What changed between two texts of a document, one line for each, in document order."""
    before, after = _blocks(old_text), _blocks(new_text)
    lines = []
    for kind, a_from, a_to, b_from, b_to in difflib.SequenceMatcher(
            None, before, after, autojunk=False).get_opcodes():
        if kind != "equal":
            lines += _replaced(before[a_from:a_to], after, b_from, b_to)
    return lines


def _replaced(old_blocks, after, first, last):
    """The lines for a stretch of paragraphs that is different: old_blocks are now after[first:
    last]. Paragraphs are paired in order where they are alike; one that has no partner is added
    or removed, so a new paragraph beside an edited one does not hide the edit.
    """
    lines = []
    old_at, new_at = 0, first

    def line(what, text):
        return "%s, %s: %s" % (what, _place(after, new_at), text)

    while old_at < len(old_blocks) or new_at < last:
        old = old_blocks[old_at] if old_at < len(old_blocks) else None
        new = after[new_at] if new_at < last else None
        if old is None:
            lines.append(line("added", new))
            new_at += 1
        elif new is None:
            lines.append(line("removed", old))
            old_at += 1
        elif _alike(old, new) >= ALIKE:
            lines.append(line("changed", word_diff(old, new)))
            old_at += 1
            new_at += 1
        elif new_at + 1 < last and _alike(old, after[new_at + 1]) >= ALIKE:
            lines.append(line("added", new))
            new_at += 1
        elif old_at + 1 < len(old_blocks) and _alike(old_blocks[old_at + 1], new) >= ALIKE:
            lines.append(line("removed", old))
            old_at += 1
        else:
            lines.append(line("removed", old))
            lines.append(line("added", new))
            old_at += 1
            new_at += 1
    return lines


def newly(before, now):
    """The items in now, (text, where it is), that were not in before (a list of texts).

    Each text in before accounts for one item of the same text in now, the first, so a second
    copy of an old item is new.
    """
    unaccounted = list(before)
    fresh = []
    for item in now:
        if item[0] in unaccounted:
            unaccounted.remove(item[0])
        else:
            fresh.append(item)
    return fresh


FIRST_LINE = "google-docs-tools snapshot 1"
Snapshot = namedtuple("Snapshot", "document taken notes comments text")


def make(taken):
    """The text of a snapshot file: its first line, what was seen as a line of JSON, the text."""
    seen = {"document": taken.document, "taken": taken.taken,
            "notes": [list(note) for note in taken.notes], "comments": taken.comments}
    return "%s\n%s\n%s" % (FIRST_LINE, json.dumps(seen, ensure_ascii=False), taken.text)


def _is_state(state):
    return isinstance(state, dict) and isinstance(state.get("resolved"), bool) and isinstance(
        state.get("replies"), list)


def _is_note(note):
    return isinstance(note, list) and len(note) == 2 and all(
        isinstance(part, str) for part in note)


def read(file_text):
    """A Snapshot from the text of a snapshot file; ValueError if it is not one."""
    first, _, rest = file_text.partition("\n")
    line, _, text = rest.partition("\n")
    seen = json.loads(line) if first == FIRST_LINE else None  # a ValueError if it is not JSON
    if not (isinstance(seen, dict) and isinstance(seen.get("document"), str)
            and isinstance(seen.get("taken"), str) and isinstance(seen.get("notes"), list)
            and all(_is_note(note) for note in seen["notes"])
            and isinstance(seen.get("comments"), dict)
            and all(_is_state(state) for state in seen["comments"].values())):
        raise ValueError("it is not a snapshot made by this command")
    return Snapshot(seen["document"], seen["taken"], [tuple(note) for note in seen["notes"]],
                    seen["comments"], text)


def comment_state(found):
    """What a snapshot keeps of a document's comments: {id: whether resolved, its replies' ids}."""
    return {comment["id"]: {"resolved": bool(comment.get("resolved")),
                            "replies": [reply["id"] for reply in alive(comment.get("replies") or [])]}
            for comment in alive(found)}


Compared = namedtuple("Compared", "lines comments replies resolved reopened")


def _one_line(text):
    return " ".join((text or "").split("\n"))


def comment_changes(before, found):
    """What changed in a document's comments since comment_state() gave before: a Compared."""
    lines = []
    counts = {"comments": 0, "replies": 0, "resolved": 0, "reopened": 0}
    for comment in alive(found):
        then = before.get(comment["id"])
        if then is None:
            counts["comments"] += 1
            words = words_on(comment)
            lines.append("new comment by %s%s: %s" % (
                by(comment), ' on "%s"' % _one_line(words) if words else "",
                _one_line(comment.get("content"))))
        for reply in alive(comment.get("replies") or []):
            if reply["id"] not in (then or {"replies": []})["replies"] and reply.get("content"):
                counts["replies"] += 1
                lines.append("new reply by %s to comment %s: %s" % (
                    by(reply), comment["id"], _one_line(reply["content"])))
        if then is not None and then["resolved"] != bool(comment.get("resolved")):
            what = "resolved" if comment.get("resolved") else "reopened"
            counts[what] += 1
            lines.append("comment %s %s: %s" % (
                comment["id"], what, beginning(comment.get("content") or "")))
    return Compared(lines, **counts)


def _counted(count, one, several):
    return "%d %s" % (count, one if count == 1 else several)


def summary(now, changed, new_notes, notes_gone, compared):
    """The first line of a look: its time, and how much of each kind is new; or nothing new."""
    new = [_counted(count, one, several) for count, one, several in (
        (changed, "paragraph changed", "paragraphs changed"),
        (new_notes, "new note", "new notes"),
        (notes_gone, "note gone", "notes gone"),
        (compared.comments, "new comment", "new comments"),
        (compared.replies, "new reply", "new replies"),
        (compared.resolved, "comment resolved", "comments resolved"),
        (compared.reopened, "comment reopened", "comments reopened")) if count]
    return "%s: %s" % (now, ", ".join(new) or "nothing new")
