"""Finding edits in a document and building the change, for edit-doc. Invented text only."""
import pytest

from googledocstools.edit_list import Edit
from googledocstools.editing import EditProblems, check_after, locate, narrowed, report, requests
from tests.conftest import DELETED, INSERTED, PICTURE, described


def edit(find, replace, occurrence=None, number=1, id=""):
    return Edit(number, id, find, replace, occurrence, "")


@pytest.mark.parametrize("find,replace,expected", [
    ("the quick fox", "the slow fox", (4, "quick", "slow")),
    ("the cat sat", "the cat", (7, " sat", "")),
    ("a b", "a x b", (2, "", "x ")),
    ("teh", "the", (0, "teh", "the")),
    ("one two three", "one too three", (4, "two", "too")),
    ("dog.", "dogs.", (0, "dog.", "dogs.")),
    ("x y", "y", (0, "x ", "")),
])
def test_only_the_words_that_change_are_changed(find, replace, expected):
    assert narrowed(find, replace) == expected


def test_an_edit_is_found_within_a_paragraph_across_differently_styled_pieces():
    document = described([
        "First paragraph.",
        [("A ", {}), ("bold", {"bold": True}), (" word here.", {})],
    ])
    found = locate(document, [edit("bold word", "strong word")])
    assert [(f.start, f.old, f.new) for f in found] == [(20, "bold", "strong")]


def test_occurrence_picks_the_nth_in_document_order():
    document = described(["one and one", "and one"])
    found = locate(document, [edit("one", "two", occurrence=3)])
    assert found[0].start == 1 + 12 + 4  # the second paragraph starts at 13


def test_problems_are_all_found_before_anything_is_changed():
    document = described(["one and one", "only once", [("pending", {INSERTED: ["s1"]}),
                                                       (" text", {})]])
    with pytest.raises(EditProblems) as raised:
        locate(document, [
            edit("missing", "x", number=1),
            edit("one", "two", number=2, id="E2"),
            edit("one", "two", occurrence=3, number=3),
            edit("pending text", "x", number=4),
        ])
    assert raised.value.problems == [
        ('edit 1: "missing" is not in the document (an edit cannot run across a paragraph '
        "break, a footnote mark, a chip or a picture)"),
        'E2: "one" is in the document 2 times; say which with "occurrence"',
        'edit 3: "one" is in the document 2 times, so there is no occurrence 3',
        ('edit 4: "pending text" touches text in a pending suggestion; accept or reject it '
        "first"),
    ]


def test_text_struck_out_in_a_pending_suggestion_cannot_be_edited_either():
    document = described([[("keep ", {}), ("struck", {DELETED: ["s1"]})]])
    with pytest.raises(EditProblems):
        locate(document, [edit("struck", "x")])


def test_edits_that_overlap_are_refused():
    document = described(["alpha beta gamma"])
    with pytest.raises(EditProblems) as raised:
        locate(document, [edit("alpha beta", "a b", number=1), edit("beta gamma", "b g", number=2)])
    assert raised.value.problems == [("edit 1 and edit 2 overlap: \"alpha beta\" and "
                                     "\"beta gamma\"")]


def test_a_picture_breaks_the_text_so_nothing_is_found_across_it():
    document = described([[("before", {}), (PICTURE, {"source": "https://img.example/a.png"}),
                           ("after", {})]])
    with pytest.raises(EditProblems):
        locate(document, [edit("beforeafter", "x")])
    assert locate(document, [edit("after", "later")])[0].start == 8


def test_text_with_characters_outside_the_basic_plane_is_placed_in_utf16_units():
    document = described(["🐿️ squirrel here"])
    found = locate(document, [edit("squirrel", "rodent")])
    assert found[0].start == 1 + 3 + 1


def test_the_requests_go_from_the_end_backwards_each_a_delete_then_an_insert():
    document = described(["one two three", "four five"])
    found = locate(document, [edit("two", "2", number=1), edit("five", "5", number=2),
                              edit("three", "three and more", number=3)])
    assert requests(found) == [
        {"deleteContentRange": {"range": {"startIndex": 20, "endIndex": 24}}},
        {"insertText": {"location": {"index": 20}, "text": "5"}},
        {"insertText": {"location": {"index": 14}, "text": " and more"}},
        {"deleteContentRange": {"range": {"startIndex": 5, "endIndex": 8}}},
        {"insertText": {"location": {"index": 5}, "text": "2"}},
    ]


def test_each_edit_is_reported_with_three_words_either_side():
    document = described(["one two three four five six seven eight nine"])
    found = locate(document, [edit("five", "5", id="E3"), edit("one", "", number=2),
                              edit("nine", "nine, ten", number=3)])
    assert [report(f) for f in found] == [
        "E3 | …two three four [five → 5] six seven eight… |",
        "edit 2 | [one → ] two three four… |",
        "edit 3 | …six seven eight [nine → nine, ten] |",
    ]


def test_after_the_change_each_edit_is_looked_for_with_its_surroundings():
    before = described(["The quick fox jumps.", "Second one."])
    found = locate(before, [edit("quick", "slow", number=1), edit("Second", "Third", number=2)])
    after = described(["The slow fox jumps.", "Second one."])
    assert check_after(after, found) == [found[1]]
    assert check_after(described(["The slow fox jumps.", "Third one."]), found) == []


def test_the_words_either_side_are_shown_when_an_edit_starts_or_ends_inside_a_word():
    document = described(["one and one and one"])
    found = locate(document, [edit(" and one", "", occurrence=2)])
    assert report(found[0]) == "edit 1 | one and one[ and one → ] |"
    found = locate(described(["Keep this here."]), [edit("this here", "this right here")])
    assert report(found[0]) == "edit 1 | Keep this [ → right ]here. |"


def test_an_edit_is_found_in_a_table_cell_in_its_place():
    document = described(["Before the table."])
    cell = {"startIndex": 20, "endIndex": 30, "paragraph": {"elements": [
        {"startIndex": 20, "endIndex": 30, "textRun": {"content": "cell text\n"}}]}}
    document["body"]["content"].append({"startIndex": 19, "endIndex": 31, "table": {
        "tableRows": [{"tableCells": [{"content": [cell]}]}]}})
    found = locate(document, [edit("cell text", "cell words")])
    assert (found[0].start, found[0].old, found[0].new) == (25, "text", "words")
