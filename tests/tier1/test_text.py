"""The document as text: headings, rules, what cannot be written, highlights. Pure."""
from googledocstools.document import Paragraph
from googledocstools.markup import Span
from googledocstools.text import as_text


def test_the_document_as_text_is_its_paragraphs_in_markup_with_a_blank_line_between():
    paragraphs = [Paragraph("NORMAL_TEXT", [Span("Plain, "), Span("bold", bold=True)]),
                  Paragraph("NORMAL_TEXT", [Span("A link", link="https://example.org/x")])]
    assert as_text(paragraphs) == "Plain, **bold**\n\n[A link](https://example.org/x)\n"


def test_empty_paragraphs_are_left_out_rules_and_unwritten_things_are_marked():
    paragraphs = [Paragraph("NORMAL_TEXT", []), Paragraph("RULE", []),
                  Paragraph("UNWRITTEN", [Span("a footnote reference")]),
                  Paragraph("NORMAL_TEXT", [Span("   ")])]
    assert as_text(paragraphs) == "---\n\n<!-- not written: a footnote reference -->\n"


def test_a_heading_gets_one_hash_per_level_and_a_title_one():
    paragraphs = [Paragraph("TITLE", [Span("T")]), Paragraph("HEADING_1", [Span("One")]),
                  Paragraph("HEADING_3", [Span("Three")])]
    assert as_text(paragraphs) == "# T\n\n# One\n\n### Three\n"


def test_highlights_are_marked_only_when_asked():
    paragraphs = [Paragraph("NORMAL_TEXT", [Span("plain "), Span("marked", highlight=True)])]
    assert as_text(paragraphs) == "plain marked\n"
    assert as_text(paragraphs, highlights=True) == "plain {==marked==}\n"


def test_a_list_items_mark_goes_before_its_text_with_a_blank_line_between_items():
    paragraphs = [Paragraph("NORMAL_TEXT", [Span("One")], mark="- "),
                  Paragraph("NORMAL_TEXT", [Span("Under it")], mark="  - "),
                  Paragraph("NORMAL_TEXT", [Span("Two", bold=True)], mark="2. "),
                  Paragraph("NORMAL_TEXT", [Span("After")])]
    assert as_text(paragraphs) == "- One\n\n  - Under it\n\n2. **Two**\n\nAfter\n"


def test_an_empty_list_item_is_left_out_as_any_empty_paragraph_is():
    assert as_text([Paragraph("NORMAL_TEXT", [], mark="- "),
                    Paragraph("NORMAL_TEXT", [Span("x")])]) == "x\n"


def test_a_heading_in_a_list_has_the_mark_first():
    assert as_text([Paragraph("HEADING_2", [Span("One")], mark="1. ")]) == "1. ## One\n"
