"""Counting the words in each part of a document, for count-doc.

A word is what lies between spaces, as word-tools' check-manuscript counts it (each paragraph's
text split at white space), so the two agree on the same text.
"""
import re
from collections import namedtuple

Part = namedtuple("Part", "heading words")  # heading None: the text before the first heading
Counted = namedtuple("Counted", "parts total braces lorem")

BRACED = re.compile(r"\{[^{}]*\}")
LOREM_STARTS = ("lorem ipsum", "duis aute")
_LOREM_WORDS = """
lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore
et dolore magna aliqua enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip
ex ea commodo consequat duis aute irure in reprehenderit voluptate velit esse cillum eu fugiat
nulla pariatur excepteur sint occaecat cupidatat non proident sunt culpa qui officia deserunt
mollit anim id est laborum perspiciatis unde omnis iste natus error voluptatem accusantium
doloremque laudantium totam rem aperiam eaque ipsa quae ab illo inventore veritatis quasi
architecto beatae vitae dicta explicabo nemo ipsam quia voluptas aspernatur aut odit fugit
"""
LOREM = frozenset(_LOREM_WORDS.split())


def words(text):
    """How many words: what lies between white space."""
    return len(text.split())


def without_braces(text):
    """The text with each {…} taken out, and how many words were in what was taken out. A brace
    with no partner is left as text."""
    taken = sum(words(found.group(0)[1:-1]) for found in BRACED.finditer(text))
    return BRACED.sub("", text), taken


def is_lorem(text):
    """Whether a paragraph is lorem ipsum filler: it starts as the usual filler does, or more than
    half of its words are the filler's words."""
    plain = [re.sub(r"[^\w]", "", word).lower() for word in text.split()]
    plain = [word for word in plain if word]
    if not plain:
        return False
    if " ".join(plain[:2]) in LOREM_STARTS:
        return True
    return sum(word in LOREM for word in plain) * 2 > len(plain)


def _level(kind):
    """A heading's level: 0 for the title, 1 to 6 for headings, None for anything else."""
    if kind == "TITLE":
        return 0
    if kind.startswith("HEADING_"):
        return int(kind[len("HEADING_"):])
    return None


def count_parts(paragraphs, level, braces=False, lorem=False):
    """The words in each part of a document: a part starts at the title or a heading at this level
    or above and runs to the next. With braces, text in {…} is left out; with lorem, lorem ipsum
    paragraphs are; each says how many words it left out."""
    parts, left_braces, left_lorem = [Part(None, 0)], 0, 0
    for paragraph in paragraphs:
        if paragraph.kind in ("RULE", "UNWRITTEN"):
            continue
        text = "".join(span.text for span in paragraph.spans)
        heading = _level(paragraph.kind)
        if heading is not None and heading <= level:
            parts.append(Part(" ".join(text.split()), 0))
        if lorem and is_lorem(text):
            left_lorem += words(text)
            continue
        if braces:
            text, taken = without_braces(text)
            left_braces += taken
        parts[-1] = parts[-1]._replace(words=parts[-1].words + words(text))
    if not parts[0].words:
        parts.pop(0)
    return Counted(parts, sum(part.words for part in parts), left_braces, left_lorem)
