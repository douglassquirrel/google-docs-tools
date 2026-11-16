"""Straight quotes and odd dashes in a document's paragraphs, as check-typography finds them.
Invented text only."""
import pytest

from googledocstools.document import Paragraph
from googledocstools.markup import Span
from googledocstools.typography import Finding, chosen, findings


def p(text, kind="NORMAL_TEXT", link=None):
    return Paragraph(kind, [Span(text, link=link)])


def fixes(text, kinds=("quotes", "dashes")):
    found = findings([p(text)], kinds)
    return found[0].fixes if found else []


def test_straight_quotes_are_flagged_with_their_curly_form_chosen_by_position():
    assert fixes('We don\'t want "this" here.') == [
        ("We don't want", "We don’t want"), ('want "this" here.', "want “this” here.")]


def test_a_quote_at_the_start_or_after_a_bracket_or_dash_opens():
    assert fixes('"Start," she said') == [('"Start," she', "“Start,” she")]
    assert fixes("('quoted')") == [("('quoted')", "(‘quoted’)")]
    assert fixes("a –'b' c") == [("a –'b' c", "a –‘b’ c")]


def test_curly_quotes_are_not_flagged_and_a_clean_paragraph_is_not_listed():
    assert findings([p("We don’t want “this” here – fine.")], ("quotes", "dashes")) == []


def test_double_hyphens_and_spaced_hyphens_become_en_dashes_and_other_hyphens_stay():
    assert fixes("a -- b and c - d") == [("a -- b", "a – b"), ("c - d", "c – d")]
    assert fixes("well-known and x--y") == [("and x--y", "and x–y")]
    assert fixes("a – b and well-known") == []


def test_words_side_by_side_that_both_need_fixing_are_one_line():
    assert fixes("say \"it's\" -- now") == [('say "it\'s" -- now', "say “it’s” – now")]


def test_only_the_kinds_asked_for_are_looked_for():
    assert fixes('it\'s a -- b', ("dashes",)) == [("a -- b", "a – b")]
    assert fixes('it\'s a -- b', ("quotes",)) == [("it's a", "it’s a")]


def test_link_text_that_is_a_web_address_and_merge_tags_are_left_out():
    paragraph = Paragraph("NORMAL_TEXT", [
        Span("See "), Span("https://example.org/it's--here", link="https://example.org/it's--here"),
        Span(" and [[contact.first_name's]] tag")])
    assert findings([paragraph], ("quotes", "dashes")) == []


def test_link_text_that_is_words_is_looked_at():
    paragraph = Paragraph("NORMAL_TEXT", [Span("the "), Span("author's site",
                                                              link="https://example.org/")])
    assert findings([paragraph], ("quotes",))[0].fixes == [("the author's site",
                                                             "the author’s site")]


def test_each_finding_says_where_its_paragraph_is_and_how_it_begins():
    found = findings([
        p("Fine."),
        p("Don't start here"),
        p("A Heading", "HEADING_2"),
        p("one two three four five six seven eight nine don't"),
        Paragraph("RULE", []),
        p("Title's Fine", "TITLE"),
    ], ("quotes",))
    assert [(f.place, f.beginning) for f in found] == [
        ('after "Fine."', "Don't start here"),
        ('under "## A Heading"', "one two three four five six seven eight…"),
        ('under "## A Heading"', "Title's Fine"),
    ]
    assert isinstance(found[0], Finding)


def test_a_heading_with_a_straight_quote_is_found_too():
    found = findings([p("The Author's Book", "TITLE")], ("quotes",))
    assert (found[0].place, found[0].fixes) == ("at the start", [
        ("The Author's Book", "The Author’s Book")])


@pytest.mark.parametrize("text,kinds", [
    ("quotes,dashes", ("quotes", "dashes")),
    (" dashes , quotes ", ("dashes", "quotes")),
    ("quotes", ("quotes",)),
])
def test_the_checks_are_read_from_a_comma_list(text, kinds):
    assert chosen(text) == kinds


@pytest.mark.parametrize("text", ["", " , ", "quotes,spaces", "QUOTES", "quotes,quotes"])
def test_an_empty_or_unknown_or_doubled_check_is_refused(text):
    with pytest.raises(ValueError):
        chosen(text)


def test_an_empty_paragraph_is_passed_over_in_saying_where_the_next_one_is():
    found = findings([p("Fine."), p(""), p("  "), p("it's")], ("quotes",))
    assert found[0].place == 'after "Fine."'
