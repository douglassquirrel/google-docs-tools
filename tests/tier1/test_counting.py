"""Counting the words of a document's parts, as count-doc does. Invented text only."""
from googledocstools.counting import Part, count_parts, is_lorem, without_braces, words
from googledocstools.document import Paragraph
from googledocstools.markup import Span


def p(text, kind="NORMAL_TEXT"):
    return Paragraph(kind, [Span(text)] if text else [])


def test_words_are_what_lies_between_spaces_as_check_manuscript_counts_them():
    assert words("") == 0
    assert words("   ") == 0
    assert words("One two  three") == 3
    assert words("well-known — it’s fine, isn't it?") == 6
    assert words("tabs\tand no-break spaces") == 4


def test_braces_are_taken_out_with_the_words_they_held():
    assert without_braces("Keep {put an introduction here} this") == ("Keep  this", 4)
    assert without_braces("{one}{two three}") == ("", 3)
    assert without_braces("no braces") == ("no braces", 0)


def test_a_brace_never_closed_or_never_opened_is_left_as_text():
    assert without_braces("an open { brace") == ("an open { brace", 0)
    assert without_braces("a close } brace") == ("a close } brace", 0)


def test_lorem_ipsum_is_known_by_its_start_or_by_most_of_its_words():
    assert is_lorem("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
    assert is_lorem("Duis aute irure dolor in reprehenderit in voluptate velit esse.")
    assert is_lorem("Sed ut perspiciatis, ut labore et dolore magna aliqua enim minim veniam.")
    assert not is_lorem("The author writes about lorem ipsum and other filler text here.")
    assert not is_lorem("")


def test_each_heading_at_the_level_or_above_starts_a_part_and_its_own_words_count_in_it():
    found = count_parts([
        p("Before anything, two."),
        p("The Book", "TITLE"),
        p("Chapter 1: The start", "HEADING_2"),
        p("One two three."),
        p("A section", "HEADING_3"),
        p("Four five."),
        p("Chapter 2", "HEADING_2"),
        p("Part Two", "HEADING_1"),
        p("Six."),
    ], level=2)
    assert found.parts == [
        Part(None, 3),
        Part("The Book", 2),
        Part("Chapter 1: The start", 4 + 3 + 2 + 2),
        Part("Chapter 2", 2),
        Part("Part Two", 3),
    ]
    assert found.total == 3 + 2 + 11 + 2 + 3
    assert (found.braces, found.lorem) == (0, 0)


def test_level_one_makes_parts_only_of_the_title_and_first_level_headings():
    found = count_parts([p("Part", "HEADING_1"), p("Chapter", "HEADING_2"), p("Text here.")],
                        level=1)
    assert found.parts == [Part("Part", 4)]


def test_no_text_before_the_first_heading_means_no_line_for_it_and_an_empty_part_is_zero():
    found = count_parts([p("", "NORMAL_TEXT"), p("Chapter", "HEADING_2"),
                         p("Next", "HEADING_2"), p("Word.")], level=2)
    assert found.parts == [Part("Chapter", 1), Part("Next", 2)]


def test_rules_and_things_that_are_not_text_are_not_words():
    found = count_parts([p("Chapter", "HEADING_2"), Paragraph("RULE", []),
                         Paragraph("UNWRITTEN", [Span("a footnote reference")]), p("Two words.")],
                        level=2)
    assert found.parts == [Part("Chapter", 3)]


def test_braces_and_lorem_are_left_out_only_when_asked_and_counted():
    paragraphs = [p("Chapter", "HEADING_2"), p("Real words {a direction here} stay."),
                  p("Lorem ipsum dolor sit amet."), p("Duis aute irure dolor.")]
    plain = count_parts(paragraphs, level=2)
    assert plain.total == 1 + 6 + 5 + 4 and (plain.braces, plain.lorem) == (0, 0)
    left = count_parts(paragraphs, level=2, braces=True, lorem=True)
    assert left.parts == [Part("Chapter", 1 + 3)]
    assert (left.braces, left.lorem) == (3, 9)


def test_a_heading_with_formatting_is_named_by_its_words_alone():
    found = count_parts([Paragraph("HEADING_2", [Span("Chapter "), Span("One", bold=True)])],
                        level=2)
    assert found.parts == [Part("Chapter One", 2)]
