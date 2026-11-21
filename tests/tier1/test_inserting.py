"""Reading the new paragraphs, finding where they go and building the change, for
insert-paragraphs. Invented text only."""
import pytest

from googledocstools.inserting import (
    Anchor,
    AnchorProblem,
    ContentError,
    New,
    anchor,
    not_there,
    parse_content,
    requests_for,
)
from googledocstools.markup import Span
from tests.conftest import DELETED, INSERTED, Listed, Styled, described


def test_plain_paragraphs_headings_and_list_items_are_read_in_order():
    text = ("## A heading two\n\n### A heading *three*\n\nA plain paragraph with an *italic* "
            "word\nthat goes on over a second line.\n\n{A placeholder in braces}\n\n"
            "- one\n- **two**\n- three\n")
    assert parse_content(text) == [
        New("HEADING_2", False, [Span("A heading two")]),
        New("HEADING_3", False, [Span("A heading "), Span("three", italic=True)]),
        New("NORMAL_TEXT", False, [Span("A plain paragraph with an "), Span("italic", italic=True),
                                   Span(" word that goes on over a second line.")]),
        New("NORMAL_TEXT", False, [Span("{A placeholder in braces}")]),
        New("NORMAL_TEXT", True, [Span("one")]),
        New("NORMAL_TEXT", True, [Span("two", bold=True)]),
        New("NORMAL_TEXT", True, [Span("three")]),
    ]


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_every_heading_level_from_one_to_six(level):
    assert parse_content("#" * level + " Words") == [
        New("HEADING_%d" % level, False, [Span("Words")])]


def test_a_heading_line_ends_its_paragraph_and_a_list_item_takes_its_following_lines():
    text = "Before\n# Heading\nAfter it\n- an item\n  that goes on\n- next\nA line\n"
    assert parse_content(text) == [
        New("NORMAL_TEXT", False, [Span("Before")]),
        New("HEADING_1", False, [Span("Heading")]),
        New("NORMAL_TEXT", False, [Span("After it")]),
        New("NORMAL_TEXT", True, [Span("an item that goes on")]),
        New("NORMAL_TEXT", True, [Span("next A line")]),
    ]


def test_list_items_with_blank_lines_between_them_as_read_doc_writes_them():
    assert parse_content("- one\n\n- two\n\nAfter.\r\n") == [
        New("NORMAL_TEXT", True, [Span("one")]),
        New("NORMAL_TEXT", True, [Span("two")]),
        New("NORMAL_TEXT", False, [Span("After.")]),
    ]


def test_a_tab_within_the_words_is_kept():
    assert parse_content("A\ttab") == [New("NORMAL_TEXT", False, [Span("A\ttab")])]


def test_words_that_only_look_like_marks_are_plain_text():
    assert parse_content("#hashtag and -dash\n\n1984 was a year\n\n-not an item") == [
        New("NORMAL_TEXT", False, [Span("#hashtag and -dash")]),
        New("NORMAL_TEXT", False, [Span("1984 was a year")]),
        New("NORMAL_TEXT", False, [Span("-not an item")]),
    ]


def test_every_fault_in_the_file_is_named_with_its_line():
    text = ("Fine.\n\n####### Seven\n\n  - nested\n\n1. numbered\n\n#\n\n- \n\n"
            "an *unclosed mark\n\nbad\x01here and \ue000\n\nA\ttab is kept.\n")
    with pytest.raises(ContentError) as raised:
        parse_content(text)
    assert raised.value.problems == [
        "line 3: a heading has one to six #, not 7",
        "line 5: a list item inside another (indented) cannot be put in yet",
        "line 7: a numbered list item cannot be put in yet; only - for a bulleted one",
        "line 9: a heading with no words",
        "line 11: a list item with no words",
        "line 13: '*' is opened here and never closed before the end of its paragraph",
        "line 15: a character Google would drop (U+0001)",
        "line 15: a character Google would drop (U+E000)",
    ]


@pytest.mark.parametrize("text", ["", "\n\n", "   \n"])
def test_a_file_with_no_paragraphs_is_refused(text):
    with pytest.raises(ContentError) as raised:
        parse_content(text)
    assert raised.value.problems == ["there are no paragraphs in it"]


def test_the_paragraph_holding_the_words_once_is_where_the_new_ones_go():
    document = described([Styled("HEADING_2", "A heading"),
                          [("The first ", {}), ("paragraph", {"bold": True}), (" under it.", {})],
                          "The last."])
    # Index 1: "A heading\n" is 10 long, so the paragraph (29 and its line break) runs from 11 to 41.
    assert anchor(document, "first paragraph") == Anchor(11, 41, False,
                                                          "The first paragraph under it.", False)


def test_a_list_item_is_said_to_be_one():
    document = described(["Before.", Listed("An item"), "After."])
    assert anchor(document, "An item") == Anchor(9, 17, True, "An item", False)


def test_what_follows_is_said_a_list_item_or_nothing_that_new_paragraphs_can_go_before():
    assert anchor(described(["One.", Listed("Two.")]), "One").following is True
    assert anchor(described(["One.", Listed("Two.")]), "Two").following is None
    document = described(["Before."])
    document["body"]["content"].append({"startIndex": 9, "endIndex": 12, "table": {}})
    assert anchor(document, "Before").following is None


@pytest.mark.parametrize("paragraphs,words,said", [
    (["One.", "Two."], "Three", ('"Three" is not in the document. Copy the words exactly, '
                                 "from within one paragraph.")),
    (["The same.", "The same."], "same", ('"same" is in the document 2 times, and must be '
                                          "there exactly once: give more of the words.")),
    ([[("Old ", {}), ("new", {INSERTED: ["s1"]}), (" words.", {})]], "Old new",
     '"Old new" touches text in a pending suggestion; accept or reject it first.'),
    ([[("Old ", {}), ("new", {INSERTED: ["s1"]}), (" words.", {})]], "new words",
     '"new words" touches text in a pending suggestion; accept or reject it first.'),
    ([[("Old ", {}), ("bad ", {DELETED: ["s1"]}), ("words.", {})]], "Old words",
     '"Old words" touches text in a pending suggestion; accept or reject it first.'),
])
def test_words_not_there_once_or_in_a_suggestion_are_refused(paragraphs, words, said):
    with pytest.raises(AnchorProblem) as raised:
        anchor(described(paragraphs), words)
    assert str(raised.value) == said


def test_words_in_a_table_are_refused():
    document = described(["Before."])  # 1 to 9; the table starts at 9, its one cell's text at 11
    cell = {"startIndex": 11, "endIndex": 22, "paragraph": {"elements": [
        {"startIndex": 11, "endIndex": 22, "textRun": {"content": "In a cell.\n"}}]}}
    document["body"]["content"].append({"startIndex": 9, "endIndex": 23, "table": {
        "tableRows": [{"tableCells": [{"content": [cell]}]}]}})
    with pytest.raises(AnchorProblem) as raised:
        anchor(document, "a cell")
    assert str(raised.value) == ('"a cell" is in a table; new paragraphs go only beside a '
                                 "paragraph outside tables.")


CLEARED = ("bold,italic,underline,strikethrough,smallCaps,backgroundColor,foregroundColor,"
           "baselineOffset,link,fontSize,weightedFontFamily")
KINDS = ("namedStyleType,alignment,lineSpacing,spaceAbove,spaceBelow,indentFirstLine,indentStart,"
         "indentEnd")


def between(start, end):
    return {"startIndex": start, "endIndex": end}


def kind(start, end, named="NORMAL_TEXT"):
    return {"updateParagraphStyle": {"range": between(start, end),
                                     "paragraphStyle": {"namedStyleType": named}, "fields": KINDS}}


def test_after_a_paragraph_the_new_ones_go_in_at_the_start_of_the_next():
    document = described(["Intro.", "Last."])  # Intro. 1 to 8, Last. 8 to 14
    new = parse_content("### Head\n\nA *word*\n\n- one\n- two")
    # Head 8 to 13, "A word" 13 to 20, one 20 to 24, two 24 to 28.
    assert requests_for(anchor(document, "Intro"), new, before=False) == [
        {"insertText": {"location": {"index": 8}, "text": "Head\nA word\none\ntwo\n"}},
        {"updateTextStyle": {"range": between(8, 27), "textStyle": {}, "fields": CLEARED}},
        kind(8, 13, "HEADING_3"), kind(13, 20), kind(20, 24), kind(24, 28),
        {"updateTextStyle": {"range": between(15, 19), "textStyle": {"italic": True},
                             "fields": "italic"}},
        {"createParagraphBullets": {"range": between(20, 28),
                                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
    ]


def test_before_a_paragraph_the_new_ones_go_in_at_its_start():
    document = described(["Intro.", "Last."])
    assert requests_for(anchor(document, "Last"), parse_content("Para"), before=True) == [
        {"insertText": {"location": {"index": 8}, "text": "Para\n"}},
        {"updateTextStyle": {"range": between(8, 12), "textStyle": {}, "fields": CLEARED}},
        kind(8, 13),
    ]


def test_after_the_last_paragraph_they_go_in_before_its_line_break():
    document = described(["Intro.", "Last."])
    assert requests_for(anchor(document, "Last"), parse_content("Para"), before=False) == [
        {"insertText": {"location": {"index": 13}, "text": "\nPara"}},
        {"updateTextStyle": {"range": between(14, 18), "textStyle": {}, "fields": CLEARED}},
        kind(14, 19),
    ]


@pytest.mark.parametrize("paragraphs,words,before,expected", [
    (["Intro.", Listed("Item")], "Intro", False, [  # after: they copy the item that follows
        {"insertText": {"location": {"index": 8}, "text": "Para\n"}},
        {"updateTextStyle": {"range": between(8, 12), "textStyle": {}, "fields": CLEARED}},
        kind(8, 13), {"deleteParagraphBullets": {"range": between(8, 13)}}]),
    (["Intro.", Listed("Item")], "Item", True, [  # before: they copy the item itself
        {"insertText": {"location": {"index": 8}, "text": "Para\n"}},
        {"updateTextStyle": {"range": between(8, 12), "textStyle": {}, "fields": CLEARED}},
        kind(8, 13), {"deleteParagraphBullets": {"range": between(8, 13)}}]),
    (["Intro.", Listed("Item")], "Item", False, [  # after the last: they copy it too
        {"insertText": {"location": {"index": 12}, "text": "\nPara"}},
        {"updateTextStyle": {"range": between(13, 17), "textStyle": {}, "fields": CLEARED}},
        kind(13, 18), {"deleteParagraphBullets": {"range": between(13, 18)}}]),
    ([Listed("Item"), "After."], "Item", False, [  # after an item, before plain text: no bullet
        {"insertText": {"location": {"index": 6}, "text": "Para\n"}},
        {"updateTextStyle": {"range": between(6, 10), "textStyle": {}, "fields": CLEARED}},
        kind(6, 11)]),
])
def test_bullets_copied_from_a_list_item_beside_them_are_taken_off(paragraphs, words, before,
                                                                    expected):
    assert requests_for(anchor(described(paragraphs), words), parse_content("Para"),
                        before=before) == expected


def test_positions_count_as_google_does_and_bold_italic_and_links_are_set():
    document = described(["Intro.", "Last."])
    new = parse_content("\U0001f600 **b** [*c*](https://example.org/c)")
    # The emoji counts two, so b is at 11 and c at 13.
    assert requests_for(anchor(document, "Last"), new, before=True) == [
        {"insertText": {"location": {"index": 8}, "text": "\U0001f600 b c\n"}},
        {"updateTextStyle": {"range": between(8, 14), "textStyle": {}, "fields": CLEARED}},
        kind(8, 15),
        {"updateTextStyle": {"range": between(11, 12), "textStyle": {"bold": True},
                             "fields": "bold"}},
        {"updateTextStyle": {"range": between(13, 14), "textStyle": {
            "italic": True, "link": {"url": "https://example.org/c"}}, "fields": "italic,link"}},
    ]


def test_each_run_of_list_items_is_a_list_of_its_own():
    document = described(["Intro.", "Last."])
    new = parse_content("- a\n- b\n\nBetween\n\n- c")
    # a 8 to 10, b 10 to 12, Between 12 to 20, c 20 to 22.
    made = requests_for(anchor(document, "Last"), new, before=True)
    assert [request for request in made if "createParagraphBullets" in request] == [
        {"createParagraphBullets": {"range": between(8, 12),
                                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
        {"createParagraphBullets": {"range": between(20, 22),
                                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
    ]


NEW = "### Head\n\nA *word*\n\n- one"
AFTER = ["Intro.", Styled("HEADING_3", "Head"), [("A ", {}), ("word", {"italic": True})],
         Listed("one"), "Last."]


def test_new_paragraphs_standing_as_written_beside_the_place_are_all_there():
    assert not_there(described(AFTER), "Intro", parse_content(NEW), before=False) == []
    assert not_there(described(AFTER), "Last", parse_content(NEW), before=True) == []


@pytest.mark.parametrize("changed,missing", [
    ({1: Styled("HEADING_2", "Head")}, [1]),  # the wrong kind
    ({2: "A word"}, [2]),  # not italic
    ({3: "one"}, [3]),  # not a list item
    ({1: Styled("HEADING_3", "Heads")}, [1]),  # other words
    ({3: "Last.", 4: "More."}, [3]),  # one short
])
def test_a_new_paragraph_not_as_written_is_named_by_its_number(changed, missing):
    paragraphs = [changed.get(number, paragraph) for number, paragraph in enumerate(AFTER)]
    assert not_there(described(paragraphs), "Intro", parse_content(NEW), before=False) == missing


def test_new_paragraphs_at_the_very_end_or_start_count_as_missing_when_cut_short():
    assert not_there(described(["Intro.", Styled("HEADING_3", "Head")]), "Intro",
                     parse_content(NEW), before=False) == [2, 3]
    assert not_there(described(AFTER[3:]), "Last", parse_content(NEW), before=True) == [1, 2]


@pytest.mark.parametrize("paragraphs", [["Nothing here."], ["Intro.", "Intro."]])
def test_all_count_as_missing_when_the_place_is_not_there_once(paragraphs):
    assert not_there(described(paragraphs), "Intro", parse_content(NEW), before=False) == [1, 2, 3]
