"""The text file's markup: paragraphs, bold, italic and links, and nothing else."""
import pytest

from googledocstools import markup
from googledocstools.markup import Span, parse


def test_plain_text_is_one_paragraph_of_one_plain_piece():
    assert parse("Hello world.") == [[Span("Hello world.")]]


def test_a_blank_line_separates_paragraphs():
    assert parse("First.\n\nSecond.") == [[Span("First.")], [Span("Second.")]]


def test_several_blank_lines_or_lines_of_spaces_separate_just_the_same():
    assert parse("First.\n\n\n  \t \nSecond.") == [[Span("First.")], [Span("Second.")]]


def test_blank_lines_at_the_start_and_the_end_are_ignored():
    assert parse("\n  \nFirst.\n\nSecond.\n\n \n") == [[Span("First.")], [Span("Second.")]]


def test_lines_inside_a_paragraph_are_joined_with_one_space():
    assert parse("One\ntwo  \n   three") == [[Span("One two three")]]


def test_windows_line_endings_are_read_like_any_other():
    assert parse("First.\r\n\r\nSecond\r\nline.\r\n") == [[Span("First.")], [Span("Second line.")]]


@pytest.mark.parametrize("text", ["", "\n", "  \n\t\n  "])
def test_a_file_with_no_text_in_it_is_refused(text):
    with pytest.raises(markup.MarkupError) as error:
        parse(text)
    assert "no text" in str(error.value)


def test_two_asterisks_each_side_make_bold():
    assert parse("A **bold** word.") == [[Span("A "), Span("bold", bold=True), Span(" word.")]]


def test_one_asterisk_each_side_makes_italic():
    assert parse("An *italic* word.") == [
        [Span("An "), Span("italic", italic=True), Span(" word.")]]


@pytest.mark.parametrize("text", ["2*3*4", "a**b**c", "5 * 3 * 2", "a ** b ** c", "* item", "word* and"])
def test_asterisks_that_are_not_at_the_edge_of_a_word_are_ordinary_characters(text):
    assert parse(text) == [[Span(text)]]


@pytest.mark.parametrize("text,line,mark", [
    ("This **never closes.", 1, "**"),
    ("An *italic that stops.", 1, "*"),
    ("Fine.\n\nStill fine\nbut **this\nnever closes.", 4, "**"),
    ("\n\nOne **closed** and *one\nnot.\n\nNext paragraph.*", 3, "*"),
])
def test_a_mark_left_open_at_the_end_of_its_paragraph_is_refused_with_its_line(text, line, mark):
    with pytest.raises(markup.MarkupError) as error:
        parse(text)
    assert "line %d" % line in str(error.value)
    assert repr(mark) in str(error.value) and "never closed" in str(error.value)


@pytest.mark.parametrize("text,line", [("***both***", 1), ("Plain.\n\nThen ****four of them", 3)])
def test_three_or_more_asterisks_at_the_edge_of_a_word_are_refused_not_guessed_at(text, line):
    with pytest.raises(markup.MarkupError) as error:
        parse(text)
    assert "line %d" % line in str(error.value) and "three or more" in str(error.value)


def test_a_link_is_square_brackets_then_an_address_in_round_ones():
    assert parse("See [the site](https://example.org/a?b=1#c) now.") == [[
        Span("See "), Span("the site", link="https://example.org/a?b=1#c"), Span(" now.")]]


@pytest.mark.parametrize("text", [
    "[TITLE] stays", "Hi [[contact.first_name]], hello", "a [note] (aside) b", "[] and ]( and )",
    "[[x]](https://example.org) is not a link either",
])
def test_square_brackets_that_are_not_a_link_are_ordinary_characters(text):
    assert parse(text) == [[Span(text)]]


@pytest.mark.parametrize("text,line", [
    ("See [the site](https://example.org and more.", 1),
    ("First.\n\nSee [the\nsite](https://example.org", 4),
    ("See [the site]( and nothing", 1),
])
def test_a_link_whose_address_is_never_closed_is_refused_with_its_line(text, line):
    with pytest.raises(markup.MarkupError) as error:
        parse(text)
    assert "line %d" % line in str(error.value) and "closing )" in str(error.value)


@pytest.mark.parametrize("address", [
    "mailto:someone@example.org", "ftp://example.org/file", "example.org/page", "//example.org",
    "javascript:alert", "HTTPS://EXAMPLE.ORG", "", "https://", "http:/example.org",
])
def test_an_address_that_is_not_http_or_https_is_refused_with_its_line(address):
    with pytest.raises(markup.MarkupError) as error:
        parse("Fine.\n\nA [link](%s) here." % address)
    assert "line 3" in str(error.value) and "http:// or https://" in str(error.value)


def test_a_link_with_no_text_is_refused_with_its_line():
    with pytest.raises(markup.MarkupError) as error:
        parse("Fine.\n\nA [](https://example.org) here.")
    assert "line 3" in str(error.value) and "no text" in str(error.value)


def test_bold_and_italic_inside_a_links_text_are_kept_and_all_of_it_is_the_link():
    url = "https://example.org"
    assert parse("[**Bold** then *italic* then plain.](%s)" % url) == [[
        Span("Bold", bold=True, link=url), Span(" then ", link=url),
        Span("italic", italic=True, link=url), Span(" then plain.", link=url)]]


def test_a_mark_that_starts_inside_a_links_text_and_ends_outside_it_is_refused():
    with pytest.raises(markup.MarkupError) as error:
        parse("Fine.\n\n[a **b](https://example.org) c**")
    assert "line 3" in str(error.value) and "inside the link" in str(error.value)
    # And the other way round: the ** before the link is never closed, the one inside the
    # link's text being ordinary characters there.
    with pytest.raises(markup.MarkupError) as error:
        parse("**a [b** c](https://example.org) d")
    assert "line 1" in str(error.value)


def test_an_address_with_its_own_round_brackets_ends_at_the_bracket_that_balances_it():
    assert parse("[Foo](https://example.org/wiki/Foo_(bar)_(baz)) and (more).") == [[
        Span("Foo", link="https://example.org/wiki/Foo_(bar)_(baz)"), Span(" and (more).")]]


def test_everything_that_is_not_markup_goes_in_character_for_character():
    odd = "“Curly” it’s – a dash… 🐿️ $HOME \\ back\\slash </script> & <b> [[contact.first_name]] 100%"
    assert parse(odd + " **bold " + odd + "**") == [[
        Span(odd + " "), Span("bold " + odd, bold=True)]]


def test_bold_may_hold_italic_and_italic_may_hold_bold():
    assert parse("**b *both* b** and *i **both** i*") == [[
        Span("b ", bold=True), Span("both", bold=True, italic=True), Span(" b", bold=True),
        Span(" and "),
        Span("i ", italic=True), Span("both", bold=True, italic=True), Span(" i", italic=True)]]


def test_a_link_inside_bold_is_bold_and_a_link():
    assert parse("**see [this](https://example.org) now**") == [[
        Span("see ", bold=True), Span("this", bold=True, link="https://example.org"),
        Span(" now", bold=True)]]


# --- a paragraph's pieces written back as markup (check-weekly-email) ----------------------

def test_plain_pieces_are_written_back_as_their_text():
    assert markup.render([Span("Hello "), Span("world.")]) == "Hello world."


def test_bold_and_italic_pieces_are_written_back_with_their_asterisks():
    assert markup.render([Span("A "), Span("bold", bold=True), Span(" and "),
                          Span("italic", italic=True), Span(" word.")]) == (
        "A **bold** and *italic* word.")


def test_a_link_piece_is_written_back_with_its_address():
    assert markup.render([Span("See "), Span("the site", link="https://example.org/a_(b)"),
                          Span(".")]) == "See [the site](https://example.org/a_(b))."


def test_several_pieces_of_one_link_are_written_as_one_link():
    url = "https://example.org"
    assert markup.render([Span("Strong", bold=True, link=url), Span(" then plain", link=url),
                          Span(" and "), Span("another", link=url)]) == (
        "[**Strong** then plain](%s) and [another](%s)" % (url, url))


def test_spaces_at_the_edge_of_a_marked_piece_are_written_outside_its_marks():
    url = "https://example.org"
    assert markup.render([Span("A"), Span(" bold ", bold=True), Span("b")]) == "A **bold** b"
    assert markup.render([Span("it ", italic=True), Span("x")]) == "*it* x"
    assert markup.render([Span("a"), Span("   ", bold=True), Span("b")]) == "a   b"
    assert markup.render([Span("see"), Span(" this ", link=url), Span("now")]) == (
        "see [this](%s) now" % url)


def test_what_is_written_back_reads_as_the_same_pieces():
    url = "https://example.org/wiki/Foo_(bar)"
    paragraph = [
        Span("“Curly” – 🐿️ $HOME \\ </script> [[contact.first_name]] [TITLE] 2*3 "),
        Span("bold", bold=True), Span(" then "), Span("italic", italic=True), Span(" and "),
        Span("Strong", bold=True, link=url), Span(" link.", link=url), Span(" The end."),
    ]
    assert parse(markup.render(paragraph)) == [paragraph]


def test_highlighted_pieces_are_written_in_double_equals_only_when_asked():
    spans = [Span("See "), Span("Hammurabi", highlight=True), Span(" now.")]
    assert markup.render(spans) == "See Hammurabi now."
    assert markup.render(spans, highlights=True) == "See {==Hammurabi==} now."


def test_spaces_at_the_edge_of_a_highlighted_piece_stay_outside_and_the_mark_is_inside_bold():
    assert markup.render([Span("a"), Span(" Hammurabi ", highlight=True), Span("b")],
                         highlights=True) == "a {==Hammurabi==} b"
    assert markup.render([Span("x", bold=True, italic=True, highlight=True)],
                         highlights=True) == "***{==x==}***"
    assert markup.render([Span(" ", highlight=True)], highlights=True) == " "
