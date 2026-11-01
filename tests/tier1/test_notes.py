"""Notes and placeholders in a document's paragraphs."""
import pytest

from googledocstools.document import Paragraph
from googledocstools.markup import Span
from googledocstools.notes import Markers, beginning, notes, placeholders


def _paragraphs(*texts):
    return [Paragraph("NORMAL_TEXT", [Span(text)]) for text in texts]


def test_the_beginning_of_a_text_is_its_first_words_with_a_mark_if_there_are_more():
    assert beginning("one two three four five six seven eight nine") == (
        "one two three four five six seven eight…")
    assert beginning("one two") == "one two"
    assert beginning("") == ""


def test_a_note_is_given_with_a_few_words_around_it():
    text = "one two three four five six [check this] seven eight nine ten eleven twelve"
    assert notes(_paragraphs(text)) == [
        ("[check this]", "…three four five six [check this] seven eight nine ten…")]


def test_a_note_near_the_edges_of_its_paragraph_has_no_mark_for_more():
    assert notes(_paragraphs("[first] and then [second]")) == [
        ("[first]", "[first] and then [second]"), ("[second]", "[first] and then [second]")]


def test_a_note_against_a_word_stays_against_it():
    assert notes(_paragraphs("word[note]s here")) == [("[note]", "word[note]s here")]


def test_notes_are_found_across_the_pieces_of_a_paragraph_in_order():
    paragraph = Paragraph("NORMAL_TEXT", [Span("a [no"), Span("te] b", bold=True)])
    assert notes([paragraph] + _paragraphs("[another]")) == [
        ("[note]", "a [note] b"), ("[another]", "[another]")]


def test_a_note_does_not_run_across_paragraphs():
    assert notes(_paragraphs("an open [ here", "and a close ] here")) == []


def test_text_in_double_brackets_is_a_merge_tag_not_a_note():
    assert notes(_paragraphs("Hi [[contact.first_name]], [a note]")) == [
        ("[a note]", "Hi [[contact.first_name]], [a note]")]


def test_with_doubled_markers_counted_the_inner_pair_is_a_note():
    found = notes(_paragraphs("Hi [[name]]"), Markers(doubled=False))
    assert found == [("[name]", "Hi [[name]]")]


def test_brackets_in_a_link_that_shows_its_own_address_are_not_a_note():
    address = "https://example.org/a[1]"
    paragraph = Paragraph("NORMAL_TEXT", [Span("See "), Span(address, link=address)])
    assert notes([paragraph]) == []


def test_brackets_in_a_link_with_words_are_a_note():
    paragraph = Paragraph("NORMAL_TEXT", [Span("[this]", link="https://example.org/a")])
    assert notes([paragraph]) == [("[this]", "[this]")]


def test_other_note_markers_are_taken_literally_and_may_be_longer_than_one_character():
    markers = Markers(note_open="<<.", note_close=".*>")
    text = "not [this] but <<.that.*> and not <<x>>"
    assert [note for note, _ in notes(_paragraphs(text), markers)] == ["<<.that.*>"]


def test_a_note_holds_no_marker_inside_it():
    assert [note for note, _ in notes(_paragraphs("[one [two] three]"))] == ["[two]"]


def test_placeholders_are_counted():
    assert placeholders(_paragraphs("{one} and {two}", "no more", "{three}")) == 3
    assert placeholders(_paragraphs("none")) == 0


def test_a_doubled_placeholder_counts_once():
    assert placeholders(_paragraphs("{{name}}")) == 1


def test_other_placeholder_markers_are_taken_literally():
    markers = Markers(placeholder_open="$(", placeholder_close=")")
    assert placeholders(_paragraphs("$(one) (two) {three}"), markers) == 1


@pytest.mark.parametrize("paragraph", [Paragraph("RULE", []), Paragraph("NORMAL_TEXT", [])])
def test_a_paragraph_with_no_text_has_neither(paragraph):
    assert notes([paragraph]) == [] and placeholders([paragraph]) == 0
