"""List items, read back from a document's description with the mark that goes before each."""
from googledocstools import document
from tests.conftest import Listed, RuleThen, described


def _marks(paragraphs):
    return [paragraph.mark for paragraph in document.paragraphs(described(paragraphs))]


def test_a_bullet_is_marked_with_a_dash_and_two_more_spaces_for_each_level():
    assert _marks(["Before", Listed("One"), Listed("Under it", level=1),
                   Listed("Under that", level=2), Listed("Two"), "After"]) == [
        "", "- ", "  - ", "    - ", "- ", ""]


def test_a_numbered_list_counts_each_level_from_1():
    assert _marks([Listed("One", numbered=True), Listed("Two", numbered=True),
                   Listed("Three", numbered=True)]) == ["1. ", "2. ", "3. "]


def test_a_nested_level_starts_again_under_each_item_above_it():
    assert _marks([Listed("One", numbered=True),
                   Listed("Under one", level=1, numbered=True),
                   Listed("Under one too", level=1, numbered=True),
                   Listed("Two", numbered=True),
                   Listed("Under two", level=1, numbered=True)]) == [
        "1. ", "  1. ", "  2. ", "2. ", "  1. "]


def test_a_list_goes_on_counting_across_a_paragraph_between_its_items():
    assert _marks([Listed("One", numbered=True), "An aside", Listed("Two", numbered=True)]) == [
        "1. ", "", "2. "]


def test_two_lists_count_apart():
    assert _marks([Listed("A", "list-a", numbered=True), Listed("B", "list-b", numbered=True),
                   Listed("A again", "list-a", numbered=True)]) == ["1. ", "1. ", "2. "]


def test_a_level_may_start_at_another_number():
    assert _marks([Listed("Five", numbered=True, start=5),
                   Listed("Six", numbered=True, start=5)]) == ["5. ", "6. "]


def test_an_empty_item_takes_its_number_though_it_is_not_written():
    assert _marks([Listed("One", numbered=True), Listed("", numbered=True),
                   Listed("Three", numbered=True)]) == ["1. ", "2. ", "3. "]


def test_a_bullet_under_a_number_is_a_bullet_and_the_number_goes_on():
    assert _marks([Listed("One", numbered=True), Listed("A bullet", level=1),
                   Listed("Two", numbered=True)]) == ["1. ", "  - ", "2. "]


def test_any_ordered_kind_of_glyph_is_counted_in_figures():
    doc = described([Listed("a", numbered=True), Listed("b", numbered=True)])
    doc["lists"]["list-1"]["listProperties"]["nestingLevels"][0]["glyphType"] = "ALPHA"
    assert [paragraph.mark for paragraph in document.paragraphs(doc)] == ["1. ", "2. "]


def test_a_list_the_document_does_not_describe_is_taken_for_bullets():
    doc = described([Listed("An item", numbered=True)])
    del doc["lists"]
    assert [paragraph.mark for paragraph in document.paragraphs(doc)] == ["- "]


def test_a_level_the_list_does_not_describe_is_taken_for_bullets():
    doc = described([Listed("An item", level=3, numbered=True)])
    doc["lists"]["list-1"]["listProperties"]["nestingLevels"] = []
    assert [paragraph.mark for paragraph in document.paragraphs(doc)] == ["      - "]


def test_a_rule_before_a_list_items_text_leaves_the_mark_on_the_text():
    doc = described([Listed(RuleThen("After the rule"))])
    assert [paragraph.mark for paragraph in document.paragraphs(doc)] == ["", "- "]


def test_a_list_item_in_a_table_is_marked_and_counted_in_its_place():
    doc = described([Listed("One", numbered=True), Listed("Two", numbered=True)])
    cell = doc["body"]["content"].pop()
    doc["body"]["content"].append({"table": {"tableRows": [{"tableCells": [
        {"content": [cell]}]}]}})
    assert [paragraph.mark for paragraph in document.paragraphs(doc)] == ["1. ", "2. "]


def test_a_rule_inside_a_list_item_leaves_the_mark_on_the_text_before_it_alone():
    doc = described([Listed("Words")])
    paragraph = doc["body"]["content"][1]["paragraph"]
    run = paragraph["elements"][0]
    paragraph["elements"] = [dict(run), {"horizontalRule": {}}, dict(run)]
    assert [paragraph.mark for paragraph in document.paragraphs(doc)] == ["- ", "", ""]
