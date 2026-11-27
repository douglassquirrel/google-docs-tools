"""Footnotes: listing a document's, reading a footnote's text, finding where a new mark goes and
building the two changes, for insert-footnote and read-doc --footnotes. Invented text only."""
import pytest

from googledocstools.footnotes import (
    Mark,
    MarkProblem,
    TextError,
    check,
    listed,
    mark_requests,
    parse_text,
    place,
    text_requests,
)
from googledocstools.markup import Span
from tests.conftest import DELETED, FOOTNOTE, INSERTED, described

ITALIC = {"italic": True}


def note(note_id):
    return (FOOTNOTE, {"footnote": note_id})


def test_each_footnote_is_listed_in_the_order_of_its_mark_with_the_words_before_it():
    found = described([
        [("A first paragraph that runs on for a good many words before its mark", {}),
         note("n-b"), (" and after.", {})],
        [("Short", {}), note("n-a"), (".", {})],
    ], footnotes={"n-a": [[(" See ", {}), ("A Book", ITALIC), (", page 3.", {})]],
                  "n-b": [" A note in two paragraphs.", " The second."]})
    assert listed(found) == [
        "1 | …good many words before its mark | A note in two paragraphs. / The second.",
        "2 | Short | See *A Book*, page 3.",
    ]


def test_a_document_with_no_footnotes_lists_none():
    assert listed(described(["Nothing to see."])) == []


def test_a_mark_after_another_mark_or_a_suggested_mark_is_listed_all_the_same():
    found = described([[("One", {}), note("n-1"), note("n-2"),
                        (FOOTNOTE, {"footnote": "n-3", INSERTED: ["suggest.1"]})]],
                      footnotes={"n-1": [" First."], "n-2": [" Second."], "n-3": [" Third."]})
    assert listed(found) == ["1 | One | First.", "2 | One | Second.", "3 | One | Third."]


def test_the_text_is_read_in_the_markup_with_italic_bold_and_links():
    assert parse_text("See *A Book*, **p. 3**, [here](https://example.org/a) or "
                      "https://example.org/b") == [
        Span("See "), Span("A Book", italic=True), Span(", "), Span("p. 3", bold=True),
        Span(", "), Span("here", link="https://example.org/a"),
        Span(" or https://example.org/b")]


@pytest.mark.parametrize("text, told", [
    ("", "--text needs the footnote's words."),
    ("   ", "--text needs the footnote's words."),
    ("Two\nlines", "--text: a footnote here is one paragraph, with no line break."),
    ("An *open mark", ("--text: '*' is opened here and never closed before the end of its "
                      "paragraph.")),
    ("A bell\x07", "--text: it holds a character Google would drop (U+0007)."),
])
def test_text_that_cannot_be_a_footnote_is_refused_saying_why(text, told):
    with pytest.raises(TextError) as refused:
        parse_text(text)
    assert str(refused.value) == told


TWO = [[("The first paragraph, with a quoted line.", {})],
       [("The second has ", {}), ("a phrase", {"bold": True}), (" [source: an article] in it.", {})]]


def test_the_mark_goes_straight_after_the_words_found_once_across_styled_pieces():
    found = described(TWO)
    assert place(found, "has a phrase", None) == Mark(65, None, "The second has a phrase")


def test_remove_takes_out_the_words_straight_after_so_the_mark_is_where_they_were():
    found = described(TWO)
    mark = place(found, "a phrase", " [source: an article]")
    assert mark == Mark(65, (65, 86), "The second has a phrase")
    assert mark_requests(mark) == [
        {"deleteContentRange": {"range": {"startIndex": 65, "endIndex": 86}}},
        {"createFootnote": {"location": {"index": 65}}},
    ]
    assert mark_requests(place(found, "quoted line", None)) == [
        {"createFootnote": {"location": {"index": 40}}}]


@pytest.mark.parametrize("words, remove, told", [
    ("no such words", None, ('"no such words" is not in the document. Copy the words exactly, '
                            "from within one paragraph.")),
    ("The", None, ('"The" is in the document 2 times, and must be there exactly once: give more '
                  "of the words.")),
    ("a phrase", " in it", ('" in it" is not straight after "a phrase", so it cannot be removed '
                           "with the mark put in its place.")),
    ("a phrase", " [source: an article] in it.\n", None),
])
def test_words_not_there_once_or_removal_not_straight_after_are_refused(words, remove, told):
    with pytest.raises(MarkProblem) as refused:
        place(described(TWO), words, remove)
    if told is not None:
        assert str(refused.value) == told


def test_words_or_removal_touching_a_pending_suggestion_are_refused():
    found = described([[("Some ", {}), ("new ", {INSERTED: ["s.1"]}), ("words [note] here.", {})],
                       [("Other line", {}), (" [gone]", {DELETED: ["s.2"]})]])
    with pytest.raises(MarkProblem) as refused:
        place(found, "Some new words", None)
    assert str(refused.value) == ('"Some new words" touches text in a pending suggestion; accept '
                                  "or reject it first.")
    with pytest.raises(MarkProblem) as refused:
        place(found, "Other line", " [gone]")
    assert str(refused.value) == ('" [gone]" touches text in a pending suggestion; accept or '
                                  "reject it first.")
    assert place(found, "words", " [note]").removal == (15, 22)


def test_the_text_goes_in_after_googles_space_with_its_italic_bold_and_links():
    spans = parse_text("See *A Book*, [here](https://example.org/a).")
    assert text_requests("kix.n1", spans) == [
        {"insertText": {"location": {"segmentId": "kix.n1", "index": 1},
                        "text": "See A Book, here."}},
        {"updateTextStyle": {"range": {"segmentId": "kix.n1", "startIndex": 5, "endIndex": 11},
                             "textStyle": {"italic": True}, "fields": "italic"}},
        {"updateTextStyle": {"range": {"segmentId": "kix.n1", "startIndex": 13, "endIndex": 17},
                             "textStyle": {"link": {"url": "https://example.org/a"}},
                             "fields": "link"}},
    ]


def test_text_beyond_the_basic_plane_is_counted_as_google_counts_it():
    requests = text_requests("n", parse_text("\U0001F600 *x*"))
    assert requests[1]["updateTextStyle"]["range"] == {"segmentId": "n", "startIndex": 4,
                                                       "endIndex": 5}


def written(words_then, note_id="n-1", text=None, after=" in it."):
    return described([[(words_then, {}), (FOOTNOTE, {"footnote": note_id}), (after, {})]],
                     footnotes={note_id: text or [[(" See ", {}), ("A Book", ITALIC)]]})


def test_check_finds_the_mark_after_the_words_and_the_text_in_its_footnote():
    spans = parse_text("See *A Book*")
    assert check(written("The second has a phrase"), "a phrase", None, "n-1", spans) == ("1", [])
    assert check(written("The second has a phrase"), "a phrase", " [x]", "n-1", spans) == (
        "1", [])


def test_check_names_each_thing_missing():
    spans = parse_text("See *A Book*")
    assert check(written("A phrase"), "no phrase", None, "n-1", spans) == (
        None, ['"no phrase" is not in the document once'])
    assert check(written("A phrase"), "A phrase", None, "other", spans) == (
        None, ['the footnote\'s mark is not straight after "A phrase"'])
    assert check(written("A phrase", text=[" See A Book"]), "A phrase", None, "n-1", spans) == (
        "1", ["the footnote's text is not as written"])
    assert check(written("A phrase", after=" [x] in it."), "A phrase", " [x]", "n-1", spans) == (
        "1", ['" [x]" is still straight after the mark'])


def test_a_mark_in_a_table_is_listed_and_one_google_does_not_describe_has_no_text():
    found = described([[("In a cell", {}), note("n-1")], [("Loose", {}), note("n-2")]],
                      footnotes={"n-1": [" Cell note."]})
    cell = found["body"]["content"].pop(1)
    found["body"]["content"].insert(1, {"table": {"tableRows": [{"tableCells": [
        {"content": [cell]}]}]}})
    del found["footnotes"]["n-2"]
    assert listed(found) == ["1 | In a cell | Cell note.", "2 | Loose | "]


def test_words_there_only_with_a_suggestion_accepted_are_refused_as_touching_it():
    found = described([[("Some ", {}), ("old ", {DELETED: ["s.1"]}), ("new words.", {})]])
    with pytest.raises(MarkProblem) as refused:
        place(found, "Some new words", None)
    assert str(refused.value) == ('"Some new words" touches text in a pending suggestion; accept '
                                  "or reject it first.")


def test_bold_in_the_text_is_set_bold():
    assert text_requests("n", parse_text("**Bold** end"))[1] == {"updateTextStyle": {
        "range": {"segmentId": "n", "startIndex": 1, "endIndex": 5},
        "textStyle": {"bold": True}, "fields": "bold"}}
