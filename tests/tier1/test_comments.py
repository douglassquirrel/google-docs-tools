"""Comments on a week's document: whom one may be addressed to, and how the list is printed."""
import pytest

from googledocstools import comments


def test_the_allowed_addresses_are_read_from_the_setting_with_commas_between_in_small_letters():
    assert comments.recipients(" Laura@Example.org, squirrel@example.net ,") == [
        "laura@example.org", "squirrel@example.net"]


def test_no_setting_means_no_one_may_be_addressed():
    assert comments.recipients(None) == []
    assert comments.recipients("") == []


def test_the_addresses_in_a_text_are_found_wherever_they_are_and_however_they_are_written():
    text = ("@laura@example.org please ask +Someone.Else@Example.co.uk (or <third@x.io>), "
            "not the price @ £5 or an @handle.")
    assert comments.addresses_in(text) == [
        "laura@example.org", "someone.else@example.co.uk", "third@x.io"]


def test_a_text_with_no_address_has_none():
    assert comments.addresses_in("Please put up the 18 March 2024 email and link to it here.") == []


def _comment(cid, when, text, resolved=False, **more):
    found = {"id": cid, "createdTime": when, "content": text, "resolved": resolved,
             "author": {"displayName": "Laura Example"}}
    found.update(more)
    return found


def test_no_comments_says_so():
    assert comments.listing([], open_only=False) == ["No comments."]


def test_each_comment_is_a_block_oldest_first_with_its_author_time_words_and_replies():
    later = _comment("c2", "2026-10-19T13:00:00.000Z", "Second.", resolved=True)
    first = _comment(
        "c1", "2026-10-19T12:00:05.120Z", "@laura@example.org please put this up\nand link it",
        assigneeEmailAddress="laura@example.org", mentionedEmailAddresses=["laura@example.org"],
        quotedFileContent={"mimeType": "text/html", "value": "too cheap to meter"},
        replies=[
            {"author": {"displayName": "Squirrel Example"}, "createdTime": "2026-10-19T12:30:00Z",
             "content": "Done, thanks."},
            {"author": {"displayName": "Gone"}, "createdTime": "2026-10-19T12:31:00Z",
             "deleted": True},
            {"author": {"displayName": "Laura Example"}, "createdTime": "2026-10-19T12:40:00Z",
             "content": "", "action": "resolve"},
            {"author": {"displayName": "Laura Example"}, "createdTime": "2026-10-19T12:50:00Z",
             "content": "One more thing", "action": "reopen"},
        ])
    assert comments.listing([later, first], open_only=False) == [
        "2 comments: 1 open, 1 resolved",
        "",
        "== Comment c1: open ==",
        "By Laura Example, 2026-10-19 12:00 UTC",
        "Assigned to laura@example.org",
        "Mentions: laura@example.org",
        'On: "too cheap to meter"',
        "@laura@example.org please put this up",
        "and link it",
        "  Reply by Squirrel Example, 2026-10-19 12:30 UTC: Done, thanks.",
        "  Reply by Laura Example, 2026-10-19 12:40 UTC: (resolved)",
        "  Reply by Laura Example, 2026-10-19 12:50 UTC: One more thing (reopened)",
        "",
        "== Comment c2: resolved ==",
        "By Laura Example, 2026-10-19 13:00 UTC",
        "Second.",
    ]


def test_a_reply_over_several_lines_is_indented_to_match():
    one = _comment("c1", "2026-10-19T12:00:00Z", "Hi", replies=[
        {"author": {"displayName": "S"}, "createdTime": "2026-10-19T12:30:00Z",
         "content": "Line one\nline two"}])
    assert comments.listing([one], open_only=False)[-2:] == [
        "  Reply by S, 2026-10-19 12:30 UTC: Line one",
        "    line two"]


def test_open_only_leaves_out_the_resolved_ones_and_says_how_many():
    found = [_comment("c1", "2026-10-19T12:00:00Z", "Open one."),
             _comment("c2", "2026-10-19T12:01:00Z", "Shut.", resolved=True),
             _comment("c3", "2026-10-19T12:02:00Z", "Shut too.", resolved=True)]
    assert comments.listing(found, open_only=True) == [
        "1 open comment (2 resolved left out)",
        "",
        "== Comment c1: open ==",
        "By Laura Example, 2026-10-19 12:00 UTC",
        "Open one.",
    ]


def test_one_comment_is_counted_in_the_singular_and_none_open_says_so():
    shut = [_comment("c1", "2026-10-19T12:00:00Z", "Shut.", resolved=True)]
    assert comments.listing(shut, open_only=False)[0] == "1 comment: 0 open, 1 resolved"
    assert comments.listing(shut, open_only=True) == ["0 open comments (1 resolved left out)"]


def test_a_deleted_comment_is_never_shown_and_missing_pieces_do_not_stop_the_list():
    gone = {"id": "c0", "deleted": True, "createdTime": "2026-10-19T11:00:00Z"}
    bare = {"id": "c1"}
    assert comments.listing([gone, bare], open_only=False) == [
        "1 comment: 1 open, 0 resolved",
        "",
        "== Comment c1: open ==",
        "By someone unnamed, at a time not given",
    ]


@pytest.mark.parametrize("text,words", [
    ('On "too cheap to meter": please put this up', "too cheap to meter"),
    ('@laura@example.org On "say "hi" now": and this', 'say "hi" now'),
    ('@laura@example.org @squirrel@example.net On "a word": both', "a word"),
    ('On "first": then "second": more', "first"),
])
def test_with_no_quote_the_words_are_read_from_on_at_the_start_after_any_mentions(text, words):
    block = comments.listing([_comment("c1", "2026-10-19T12:00:00Z", text)], open_only=False)
    assert block[4:] == ['On: "%s"' % words, text]


@pytest.mark.parametrize("text", [
    'Please see On "this": later', 'On "unfinished', 'On "": empty', 'on "small": letters',
    '@laura@example.org  On "two spaces": no'])
def test_a_text_not_starting_with_on_and_its_words_gives_no_on_line(text):
    block = comments.listing([_comment("c1", "2026-10-19T12:00:00Z", text)], open_only=False)
    assert block[4:] == [text]


def test_a_quote_wins_over_on_in_the_text():
    one = _comment("c1", "2026-10-19T12:00:00Z", 'On "these": words',
                   quotedFileContent={"value": "quoted ones"})
    assert comments.listing([one], open_only=False)[4:] == [
        'On: "quoted ones"', 'On "these": words']
