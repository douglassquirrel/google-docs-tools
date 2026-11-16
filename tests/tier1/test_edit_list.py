"""Reading an edits file for edit-doc: the shape of word-tools' propose-edits list."""
import json

import pytest

from googledocstools.edit_list import Edit, EditsError, parse_edits


def test_a_list_of_edits_is_read_with_its_optional_keys():
    edits = parse_edits(json.dumps([
        {"find": "teh", "replace": "the"},
        {"id": "E2", "find": "one", "replace": "", "occurrence": 2, "why": "repeated",
         "where": "body"},
    ]))
    assert edits == [Edit(1, "", "teh", "the", None, ""), Edit(2, "E2", "one", "", 2, "repeated")]
    assert [edit.name for edit in edits] == ["edit 1", "E2"]


def test_an_empty_list_is_refused():
    with pytest.raises(EditsError) as raised:
        parse_edits("[]")
    assert raised.value.problems == ["the list has no edits in it"]


@pytest.mark.parametrize("text,problem", [
    ("{", "not JSON: "),
    ('{"find": "a"}', "a JSON list of edits"),
    ('["a"]', 'edit 1: must be an object with "find" and "replace"'),
])
def test_a_file_that_is_not_a_list_of_objects_is_refused(text, problem):
    with pytest.raises(EditsError) as raised:
        parse_edits(text)
    assert raised.value.problems[0].startswith(problem) or problem in raised.value.problems[0]


@pytest.mark.parametrize("edit,problem", [
    ({"find": "", "replace": "x"}, '"find" must be text and not empty'),
    ({"find": 3, "replace": "x"}, '"find" must be text and not empty'),
    ({"find": "a"}, '"replace" must be text (empty to delete)'),
    ({"find": "a", "replace": "a"}, "would change nothing"),
    ({"find": "a\nb", "replace": "a"}, '"find" holds a line break'),
    ({"find": "a", "replace": "b\rc"}, '"replace" holds a line break'),
    ({"find": "a", "replace": "b\tc"}, '"replace" holds a tab'),
    ({"find": "a", "replace": "b", "occurrence": 0}, '"occurrence" must be a whole number'),
    ({"find": "a", "replace": "b", "occurrence": True}, '"occurrence" must be a whole number'),
    ({"find": "a", "replace": "b", "occurrence": "2"}, '"occurrence" must be a whole number'),
    ({"find": "a", "replace": "b", "id": 4}, '"id" must be text'),
    ({"find": "a", "replace": "b", "why": ["x"]}, '"why" must be text'),
    ({"find": "a", "replace": "b", "where": "footnote:1"}, '"where" may only be body here'),
    ({"find": "a", "replace": "b", "colour": "red"}, 'unknown key "colour"'),
])
def test_each_fault_in_an_edit_is_named(edit, problem):
    with pytest.raises(EditsError) as raised:
        parse_edits(json.dumps([edit]))
    assert any(problem in found for found in raised.value.problems), raised.value.problems


def test_every_fault_in_every_edit_is_named_at_once():
    with pytest.raises(EditsError) as raised:
        parse_edits(json.dumps([{"id": "A", "find": ""}, {"find": "x", "replace": "y"},
                                {"find": "a", "replace": "a", "why": 1}]))
    assert raised.value.problems == [
        'A: "find" must be text and not empty',
        'A: "replace" must be text (empty to delete)',
        'edit 3: "why" must be text',
        'edit 3: "replace" is the same as "find", so the edit would change nothing',
    ]


def test_find_and_replace_the_same_but_for_the_unicode_form_change_nothing():
    with pytest.raises(EditsError):
        parse_edits(json.dumps([{"find": "café", "replace": "café"}]))
