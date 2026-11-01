"""Snapshots of a document, and what changed since one."""
import json

import pytest

from googledocstools import snapshot


def test_one_word_changed_is_shown_with_three_words_of_what_is_the_same_before_it():
    assert snapshot.word_diff("Hi there, here is this week’s news.",
                              "Hi there, here is this week’s headlines.") == (
        "…is this week’s {-news.-}{+headlines.+}")


def test_a_word_added_at_the_start_and_one_removed_at_the_end_are_each_shown_where_they_are():
    assert snapshot.word_diff("a b c", "x a b") == "{+x+} a b {-c-}"


def test_a_word_added_or_taken_out_is_shown_alone():
    assert snapshot.word_diff("One two three.", "One two new three.") == "One two {+new+} three."
    assert snapshot.word_diff("One two old three.", "One two three.") == "One two {-old-} three."


def test_a_short_paragraph_is_shown_whole_with_no_ellipsis():
    assert snapshot.word_diff("Hello there world", "Hello big world") == (
        "Hello {-there-}{+big+} world")


def test_a_long_unchanged_stretch_between_two_changes_is_shortened_in_the_middle():
    old = "one two three four five six seven eight nine ten eleven twelve"
    new = "ONE two three four five six seven eight nine ten eleven TWELVE"
    assert snapshot.word_diff(old, new) == (
        "{-one-}{+ONE+} two three four … nine ten eleven {-twelve-}{+TWELVE+}")


def test_a_stretch_of_six_words_between_changes_is_shown_whole():
    assert snapshot.word_diff("a b c d e f g h", "A b c d e f g H") == (
        "{-a-}{+A+} b c d e f g {-h-}{+H+}")


TEXT = "# A title\n\nHi there, here is this week’s news.\n\nStay warm!\n"


def test_a_document_that_is_the_same_has_no_changes():
    assert snapshot.changes(TEXT, TEXT) == []


def test_a_paragraph_changed_is_shown_under_its_nearest_heading_with_the_difference():
    assert snapshot.changes(TEXT, TEXT.replace("news", "headlines")) == [
        'changed, under "# A title": …is this week’s {-news.-}{+headlines.+}']


def test_the_nearest_heading_is_the_last_one_above_past_any_paragraphs():
    old = "# One\n\n## Two\n\nFirst words here.\n\nThese words stay the same now.\n"
    new = old.replace("same now", "same today")
    assert snapshot.changes(old, new) == [
        'changed, under "## Two": …stay the same {-now.-}{+today.+}']


def test_with_no_heading_above_the_place_is_after_the_paragraph_before():
    old = "The first paragraph of this long document runs on and on.\n\nThe cat sat still.\n"
    new = old.replace("still", "down")
    assert snapshot.changes(old, new) == [
        ('changed, after "The first paragraph of this long document runs…": '
         "The cat sat {-still.-}{+down.+}")]


def test_with_nothing_above_the_place_is_the_start():
    assert snapshot.changes("One two three.\n", "One two four.\n") == [
        "changed, at the start: One two {-three.-}{+four.+}"]


def test_a_heading_in_a_list_counts_as_a_heading():
    old = "1. ## One\n\nA body of text here.\n"
    assert snapshot.changes(old, old.replace("here", "there")) == [
        'changed, under "1. ## One": …body of text {-here.-}{+there.+}']


def test_a_paragraph_added_is_shown_whole():
    assert snapshot.changes("One.\n\nThree.\n", "One.\n\nA **new** one.\n\nThree.\n") == [
        'added, after "One.": A **new** one.']


def test_a_paragraph_added_at_the_start_is_at_the_start():
    assert snapshot.changes("One.\n", "Before.\n\nOne.\n") == ["added, at the start: Before."]


def test_a_paragraph_removed_is_shown_whole():
    assert snapshot.changes("One.\n\nTwo, gone.\n\nThree.\n", "One.\n\nThree.\n") == [
        'removed, after "One.": Two, gone.']


def test_a_paragraph_replaced_by_one_that_shares_few_words_is_removed_and_added_not_changed():
    assert snapshot.changes("# H\n\nThe cat sat on the mat today.\n\nThree.\n",
                            "# H\n\nQuarterly revenue exceeded every forecast.\n\nThree.\n") == [
        'removed, under "# H": The cat sat on the mat today.',
        'added, under "# H": Quarterly revenue exceeded every forecast.']


def test_two_neighbouring_paragraphs_both_changed_are_both_reported():
    old = "# H\n\nThe quick brown fox jumps.\n\nA lazy dog sleeps all day.\n\nEnd.\n"
    new = "# H\n\nThe quick brown cat jumps.\n\nA lazy dog sleeps all night.\n\nEnd.\n"
    assert snapshot.changes(old, new) == [
        'changed, under "# H": The quick brown {-fox-}{+cat+} jumps.',
        'changed, under "# H": …dog sleeps all {-day.-}{+night.+}']


def test_a_new_paragraph_put_before_an_edited_one_is_added_and_the_edit_still_found():
    old = "# H\n\nThe quick brown fox jumps over.\n\nEnd.\n"
    new = ("# H\n\nA brand new paragraph about budgets.\n\n"
           "The quick brown cat jumps over.\n\nEnd.\n")
    assert snapshot.changes(old, new) == [
        'added, under "# H": A brand new paragraph about budgets.',
        'changed, under "# H": The quick brown {-fox-}{+cat+} jumps over.']


def test_a_paragraph_taken_out_before_an_edited_one_is_removed_and_the_edit_still_found():
    old = ("# H\n\nA dull paragraph about weather.\n\n"
           "The quick brown fox jumps over.\n\nEnd.\n")
    new = "# H\n\nThe quick brown cat jumps over.\n\nEnd.\n"
    assert snapshot.changes(old, new) == [
        'removed, under "# H": A dull paragraph about weather.',
        'changed, under "# H": The quick brown {-fox-}{+cat+} jumps over.']


def test_several_new_paragraphs_after_an_edited_one_are_all_added():
    old = "# H\n\nThe quick brown fox jumps over.\n\nEnd.\n"
    new = "# H\n\nThe quick brown cat jumps over.\n\nOne more.\n\nAnd another.\n\nEnd.\n"
    assert snapshot.changes(old, new) == [
        'changed, under "# H": The quick brown {-fox-}{+cat+} jumps over.',
        'added, under "# H": One more.', 'added, under "# H": And another.']


def test_a_stretch_that_ends_with_paragraphs_gone_reports_them_removed():
    old = "# H\n\nThe quick brown fox jumps over.\n\nGone one.\n\nGone two.\n\nEnd.\n"
    new = "# H\n\nThe quick brown cat jumps over.\n\nEnd.\n"
    assert snapshot.changes(old, new) == [
        'changed, under "# H": The quick brown {-fox-}{+cat+} jumps over.',
        'removed, under "# H": Gone one.', 'removed, under "# H": Gone two.']


def test_a_bold_word_made_plain_is_a_change_even_alone_in_its_paragraph():
    assert snapshot.changes("A **bold** word.\n", "A bold word.\n") == [
        "changed, at the start: A {-**bold**-}{+bold+} word."]
    assert snapshot.changes("One.\n\n**Alone**\n", "One.\n\nAlone\n") == [
        'changed, after "One.": {-**Alone**-}{+Alone+}']


def test_a_links_address_changed_under_the_same_text_is_reported():
    old = "Please [tell us](https://example.org/old) what you think.\n"
    new = "Please [tell us](https://example.org/new) what you think.\n"
    assert snapshot.changes(old, new) == [
        ("changed, at the start: Please [tell {-us](https://example.org/old)-}"
         "{+us](https://example.org/new)+} what you think.")]


def test_an_item_that_was_there_before_is_not_new_wherever_it_is_now():
    now = [("[check date]", "Paragraph two"), ("[make it shorter]", "Paragraph five")]
    assert snapshot.newly(["[check date]"], now) == [("[make it shorter]", "Paragraph five")]
    assert snapshot.newly(["[make it shorter]", "[check date]"], now) == []
    assert snapshot.newly([], []) == []


def test_repeats_are_counted_so_a_second_copy_of_an_old_item_is_new():
    now = [("[again]", "One"), ("[again]", "Two"), ("[other]", "Three")]
    assert snapshot.newly(["[again]"], now) == [("[again]", "Two"), ("[other]", "Three")]


NOTES = [("[check this]", "…around [check this] it…")]
COMMENTS = {"c1": {"resolved": False, "replies": ["r1"]}}


def _made(text="# Title\n\nThe text.\n", notes=NOTES, comments=COMMENTS):
    return snapshot.make(snapshot.Snapshot(
        "a-document", "2026-11-01 19:40 UTC", notes, comments, text))


def test_a_snapshot_is_a_first_line_one_line_of_what_was_seen_and_the_text():
    lines = _made().split("\n", 2)
    assert lines[0] == "google-docs-tools snapshot 1"
    assert json.loads(lines[1]) == {
        "document": "a-document", "taken": "2026-11-01 19:40 UTC",
        "notes": [["[check this]", "…around [check this] it…"]], "comments": COMMENTS}
    assert lines[2] == "# Title\n\nThe text.\n"


def test_a_snapshot_read_back_gives_what_was_put_in():
    assert snapshot.read(_made()) == snapshot.Snapshot(
        "a-document", "2026-11-01 19:40 UTC", NOTES, COMMENTS, "# Title\n\nThe text.\n")


def test_text_and_notes_holding_lines_like_the_files_own_are_just_data():
    text = "google-docs-tools snapshot 1\n\n{\"document\": 1}\n\né 🐿️ \\ \" $HOME </script>\n"
    notes = [("[line\none]", "a \"quoted\" one \\")]
    assert snapshot.read(_made(text, notes)) == snapshot.Snapshot(
        "a-document", "2026-11-01 19:40 UTC", notes, COMMENTS, text)


@pytest.mark.parametrize("text", [
    "",
    "A shopping list\n\nEggs.\n",
    "google-docs-tools snapshot 1",
    "google-docs-tools snapshot 2\n{}\n",
    "online-publishing-tools snapshot 1\nDocument: x\n",
    "google-docs-tools snapshot 1\nnot json\n",
    "google-docs-tools snapshot 1\n[]\n",
    "google-docs-tools snapshot 1\n{}\n",
    'google-docs-tools snapshot 1\n{"document": 1, "taken": "t", "notes": [], "comments": {}}\n',
    'google-docs-tools snapshot 1\n{"document": "d", "taken": 1, "notes": [], "comments": {}}\n',
    'google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": 1, "comments": {}}\n',
    'google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": [1], "comments": {}}\n',
    ('google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": [["a"]], '
     '"comments": {}}\n'),
    'google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": [], "comments": 1}\n',
    ('google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": [], '
     '"comments": {"c": 1}}\n'),
    ('google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": [], '
     '"comments": {"c": {"resolved": 1, "replies": []}}}\n'),
    ('google-docs-tools snapshot 1\n{"document": "d", "taken": "t", "notes": [], '
     '"comments": {"c": {"resolved": true, "replies": 1}}}\n'),
])
def test_text_that_is_not_a_snapshot_of_this_command_is_refused(text):
    with pytest.raises(ValueError):
        snapshot.read(text)


def _comment(cid, when="2026-11-01T19:38:05.000Z", text="Some words here", resolved=False,
             replies=(), **more):
    return dict({"id": cid, "createdTime": when, "content": text, "resolved": resolved,
                 "author": {"displayName": "Ann Example"}, "replies": list(replies)}, **more)


def _reply(rid, text="A reply", when="2026-11-01T19:39:05.000Z", **more):
    return dict({"id": rid, "createdTime": when, "content": text,
                 "author": {"displayName": "Bo Example"}}, **more)


def test_what_a_snapshot_keeps_of_comments_is_whether_each_is_resolved_and_its_replies():
    found = [_comment("c1", replies=[_reply("r1"), _reply("r2", deleted=True)]),
             _comment("c2", resolved=True), _comment("c3", deleted=True)]
    assert snapshot.comment_state(found) == {
        "c1": {"resolved": False, "replies": ["r1"]},
        "c2": {"resolved": True, "replies": []}}


def _compared(before, found):
    return snapshot.comment_changes(snapshot.comment_state(before), found)


def test_comments_with_nothing_new_have_no_lines():
    same = [_comment("c1", replies=[_reply("r1")])]
    assert _compared(same, same) == snapshot.Compared([], 0, 0, 0, 0)


def test_a_new_comment_says_who_when_on_what_and_its_text():
    found = [_comment("c1", quotedFileContent={"value": "the words"})]
    assert _compared([], found) == snapshot.Compared(
        ['new comment by Ann Example, 2026-11-01 19:38 UTC on "the words": Some words here'],
        1, 0, 0, 0)


def test_a_new_comment_with_no_words_given_leaves_them_out_and_is_on_one_line():
    assert _compared([], [_comment("c1", text="two\nlines")]).lines == [
        "new comment by Ann Example, 2026-11-01 19:38 UTC: two lines"]


def test_a_new_reply_says_who_when_and_to_which_comment():
    before = [_comment("c1")]
    found = [_comment("c1", replies=[_reply("r1")])]
    assert _compared(before, found) == snapshot.Compared(
        ["new reply by Bo Example, 2026-11-01 19:39 UTC to comment c1: A reply"], 0, 1, 0, 0)


def test_the_replies_on_a_new_comment_are_new_too():
    found = [_comment("c1", replies=[_reply("r1")])]
    assert _compared([], found) == snapshot.Compared(
        ["new comment by Ann Example, 2026-11-01 19:38 UTC: Some words here",
         "new reply by Bo Example, 2026-11-01 19:39 UTC to comment c1: A reply"], 1, 1, 0, 0)


def test_a_comment_resolved_or_reopened_is_a_line_with_its_first_words():
    before = [_comment("c1"), _comment("c2", resolved=True)]
    found = [_comment("c1", resolved=True), _comment("c2")]
    assert _compared(before, found) == snapshot.Compared(
        ["comment c1 resolved: Some words here", "comment c2 reopened: Some words here"],
        0, 0, 1, 1)


def test_a_reply_that_only_resolves_has_no_line_of_its_own():
    before = [_comment("c1")]
    found = [_comment("c1", resolved=True, replies=[_reply("r1", text="", action="resolve")])]
    assert _compared(before, found) == snapshot.Compared(
        ["comment c1 resolved: Some words here"], 0, 0, 1, 0)


def test_a_reply_with_words_that_resolves_is_a_reply_and_a_resolving():
    before = [_comment("c1")]
    found = [_comment("c1", resolved=True, replies=[_reply("r1", text="Done", action="resolve")])]
    assert _compared(before, found) == snapshot.Compared(
        ["new reply by Bo Example, 2026-11-01 19:39 UTC to comment c1: Done",
         "comment c1 resolved: Some words here"], 0, 1, 1, 0)


def test_a_deleted_comment_or_reply_is_not_new_and_comments_go_oldest_first():
    found = [_comment("c2", when="2026-11-01T20:00:00.000Z", text="Later"),
             _comment("c1", when="2026-11-01T19:00:00.000Z", text="Sooner"),
             _comment("c3", deleted=True),
             _comment("c4", replies=[_reply("r1", deleted=True)])]
    lines = _compared([], found).lines
    assert [line.rsplit(": ", 1)[1] for line in lines] == ["Sooner", "Some words here", "Later"]


def test_the_summary_line_says_nothing_new():
    assert snapshot.summary("2026-11-01 19:45 UTC", 0, 0, 0, snapshot.Compared([], 0, 0, 0, 0)) == (
        "2026-11-01 19:45 UTC: nothing new")


def test_the_summary_line_counts_each_kind_that_is_not_none_in_order():
    compared = snapshot.Compared(["a line"], 1, 0, 0, 0)
    assert snapshot.summary("2026-11-01 19:40 UTC", 2, 1, 0, compared) == (
        "2026-11-01 19:40 UTC: 2 paragraphs changed, 1 new note, 1 new comment")
    assert snapshot.summary("T", 1, 2, 3, snapshot.Compared([], 2, 2, 2, 2)) == (
        "T: 1 paragraph changed, 2 new notes, 3 notes gone, 2 new comments, 2 new replies, "
        "2 comments resolved, 2 comments reopened")
    assert snapshot.summary("T", 0, 0, 1, snapshot.Compared([], 0, 1, 1, 1)) == (
        "T: 1 note gone, 1 new reply, 1 comment resolved, 1 comment reopened")
