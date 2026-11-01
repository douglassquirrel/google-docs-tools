"""A document as text: each paragraph in markup, a blank line between (from online-publishing-tools'
check.py, 1 November 2026)."""
from googledocstools.markup import render


def _hashes(kind):
    """The marks before a heading's text: one # per level, a title counting as level 1."""
    if kind == "TITLE":
        return "# "
    if kind.startswith("HEADING_"):
        return "#" * int(kind[len("HEADING_"):]) + " "
    return ""


def _block(paragraph, highlights):
    """One paragraph as a block of the document's text, or None if it has no text."""
    if paragraph.kind == "RULE":
        return "---"
    if paragraph.kind == "UNWRITTEN":
        return "<!-- not written: %s -->" % paragraph.spans[0].text
    text = render(paragraph.spans, highlights).strip()
    return paragraph.mark + _hashes(paragraph.kind) + text if text else None


def as_text(paragraphs, highlights=False):
    """The document as text: each paragraph in markup, a blank line between."""
    blocks = [block for block in (_block(paragraph, highlights) for paragraph in paragraphs)
              if block is not None]
    return "\n\n".join(blocks) + "\n"
