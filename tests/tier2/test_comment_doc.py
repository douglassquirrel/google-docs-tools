"""comment-doc against the stand-in: adding a comment, listing them, and every refusal. From
online-publishing-tools' comment-doc tests (1 November 2026)."""
import json

import pytest

from tests.tier2.conftest import DOC_ID, DOC_NAME, doc_paragraphs

LINK = "https://docs.example.org/document/d/%s/edit" % DOC_ID
HOSTILE = "it's a \\ \"test\" $HOME </script> é 🐿️"


def posts(fake):
    return [c for c in fake.calls if c["method"] == "POST" and c["path"].endswith("/comments")]


def test_help_lists_every_flag_and_contacts_nothing(comment, fake):
    result = comment("--help", defaults=False)
    assert result.code == 0
    for flag in ("DOC", "--add", "--on", "--to", "--quote", "--dry-run", "--list", "--open-only",
                 "--settings", "--timeout"):
        assert flag in result.out
    assert "COMMENT_RECIPIENTS" in result.out
    assert fake.calls == []


# --- adding -----------------------------------------------------------------------------------

def test_add_puts_one_comment_on_words_found_once_even_across_styles_and_prints_its_address(
        comment, fake, tmp_path):
    result = comment("--add", "Please check this.", "--on", "with a bold word")
    assert result.code == 0 and result.err == ""
    assert result.out == ('Added comment comment-1 on "with a bold word"\n'
                          "%s?disco=comment-1\n" % LINK)
    assert [json.loads(c["body"].decode("utf-8")) for c in posts(fake)] == [
        {"content": 'On "with a bold word": Please check this.'}]
    assert fake.writes() == [("POST", "/drive/v3/files/%s/comments" % DOC_ID)]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["home"]


def test_to_an_allowed_address_starts_the_text_with_the_mention_whatever_its_capitals(
        comment, fake):
    result = comment("--add", "Please put it up.", "--on", "the test squad",
                     "--to", "SQUIRREL@example.NET")
    assert result.code == 0
    assert [c["content"] for c in comment.added()] == [
        '@squirrel@example.net On "the test squad": Please put it up.']


def test_quote_gives_the_words_to_google_as_a_quote_and_the_text_as_it_is(comment, fake):
    result = comment("--add", "Please put it up.", "--on", "the test squad", "--quote",
                     "--to", "laura@example.org")
    assert result.code == 0 and result.err == ""
    assert result.out.startswith('Added comment comment-1 on "the test squad"\n')
    assert [json.loads(c["body"].decode("utf-8")) for c in posts(fake)] == [
        {"content": "@laura@example.org Please put it up.",
         "quotedFileContent": {"mimeType": "text/plain", "value": "the test squad"}}]


def test_words_holding_quote_colon_space_are_refused_without_quote_and_added_with_it(
        comment, fake):
    comment.document(doc_paragraphs() + ['He said "no": then left'])
    result = comment("--add", "Hi", "--on", 'said "no": then')
    assert result.code == 2 and result.out == ""
    assert result.err == (
        'comment-doc: --on holds ": (a quotation mark, a colon and a space), which '
        'would make the words hard to read back from the comment\'s text, where they go as '
        'On "<words>": . Give fewer of the words, or add --quote to give them to Google as a '
        'quote instead. Nothing was added.\n')
    assert fake.calls == []
    result = comment("--add", "Hi", "--on", 'said "no": then', "--quote")
    assert result.code == 0, result.err
    assert [c["quotedFileContent"]["value"] for c in comment.added()] == ['said "no": then']


def test_to_an_address_not_allowed_is_refused_before_anything_is_contacted(comment, fake):
    result = comment("--add", "Hi", "--on", "the test squad", "--to", "someone@example.com")
    assert result.code == 2 and result.out == ""
    assert result.err == (
        "comment-doc: --to someone@example.com is not one of the addresses in the "
        "setting COMMENT_RECIPIENTS, the only people a comment may be addressed to (Google "
        "emails them). Nothing was added.\n")
    assert fake.calls == []


def test_to_with_no_recipients_setting_is_refused_and_says_where_they_go(comment, fake):
    comment.settings.write_text("# nobody\n", encoding="utf-8")
    result = comment("--add", "Hi", "--on", "the test squad", "--to", "laura@example.org")
    assert result.code == 2 and "COMMENT_RECIPIENTS" in result.err and "settings" in result.err
    assert fake.calls == []


@pytest.mark.parametrize("text", [
    "Ask +someone@example.com about it", "cc other.person@example.co.uk", "@x@y.io see"])
def test_a_text_naming_an_address_not_allowed_is_refused_with_or_without_to(
        comment, fake, text):
    for extra in ((), ("--to", "laura@example.org")):
        result = comment("--add", text, "--on", "the test squad", *extra)
        assert result.code == 2 and result.out == ""
        assert "COMMENT_RECIPIENTS" in result.err and "Nothing was added" in result.err
    assert fake.calls == []


def test_words_naming_an_address_not_allowed_are_refused_since_they_go_in_the_text(
        comment, fake):
    result = comment("--add", "Who is this?", "--on", "write to someone@example.com today")
    assert result.code == 2 and result.out == ""
    assert result.err == (
        "comment-doc: The words of --on name someone@example.com, which is not one of "
        "the addresses in the setting COMMENT_RECIPIENTS; they go in the comment's text, where "
        "Google would take it for a mention and email them. Give other words, or add --quote. "
        "Nothing was added.\n")
    assert fake.calls == []


def test_words_naming_an_address_are_allowed_with_quote_which_keeps_them_out_of_the_text(
        comment, fake):
    comment.document(doc_paragraphs() + ["write to someone@example.com today"])
    result = comment("--add", "Who is this?", "--on", "someone@example.com", "--quote")
    assert result.code == 0, result.err
    assert [c["content"] for c in comment.added()] == ["Who is this?"]


def test_words_naming_an_allowed_address_go_in_the_text(comment, fake):
    comment.document(doc_paragraphs() + ["ask Laura@Example.org first"])
    result = comment("--add", "Done?", "--on", "ask Laura@Example.org first")
    assert result.code == 0, result.err
    assert [c["content"] for c in comment.added()] == ['On "ask Laura@Example.org first": Done?']


def test_a_text_naming_an_allowed_address_is_added(comment):
    result = comment("--add", "Ask Laura@Example.org about it", "--on", "the test squad")
    assert result.code == 0 and len(comment.added()) == 1


def test_words_not_in_the_document_are_exit_5_and_nothing_is_added(comment, fake):
    result = comment("--add", "Hi", "--on", "words that are nowhere")
    assert result.code == 5 and result.out == ""
    assert result.err == (
        "comment-doc: \"words that are nowhere\" is not in the document "
        "%r (%s), so there is nothing to put the comment on. Copy the "
        "words exactly, within one paragraph. Nothing was added.\n" % (DOC_NAME, LINK))
    assert fake.writes() == []


def test_words_in_the_document_more_than_once_are_exit_5_and_nothing_is_added(comment, fake):
    result = comment("--add", "Hi", "--on", "e")
    assert result.code == 5 and result.out == ""
    assert "is in the document" in result.err and "times" in result.err
    assert "Give more of the words" in result.err and "Nothing was added" in result.err
    assert fake.writes() == []


def test_words_across_two_paragraphs_are_not_found(comment, fake):
    result = comment("--add", "Hi", "--on", "test squad\nHi")
    assert result.code == 5 and fake.writes() == []


def test_dry_run_checks_everything_and_says_what_it_would_add_but_adds_nothing(comment, fake):
    result = comment("--add", "Put it up", "--on", "the test squad", "--to",
                     "laura@example.org", "--dry-run")
    assert result.code == 0 and result.err == ""
    assert result.out == ('Would add a comment on "the test squad": @laura@example.org On '
                          '"the test squad": Put it up\n')
    assert fake.writes() == [] and comment.added() == []
    assert any(c["path"] == "/v1/documents/%s" % DOC_ID for c in fake.calls)


def test_dry_run_still_refuses_words_not_found(comment, fake):
    result = comment("--add", "Hi", "--on", "nowhere at all", "--dry-run")
    assert result.code == 5 and result.out == "" and fake.writes() == []


def test_text_and_words_with_quotes_backslashes_newlines_dollars_and_script_are_data(
        comment, fake):
    comment.document(doc_paragraphs() + ["Before " + HOSTILE + " after"])
    text = HOSTILE + "\nsecond line"
    result = comment("--add", text, "--on", HOSTILE)
    assert result.code == 0, result.err
    assert json.loads(posts(fake)[0]["body"].decode("utf-8")) == {
        "content": 'On "%s": %s' % (HOSTILE, text)}


@pytest.mark.parametrize("argv,told", [
    (("--add", "Hi"), "--on"),
    (("--add", "", "--on", "the test squad"), "--add"),
    (("--add", "Hi", "--on", ""), "--on"),
    (("--add", "   ", "--on", "the test squad"), "--add"),
    (("--list", "--on", "the test squad"), "--on"),
    (("--list", "--to", "laura@example.org"), "--to"),
    (("--list", "--dry-run"), "--dry-run"),
    (("--list", "--quote"), "--quote does not go with --list"),
    (("--add", "Hi", "--on", "the test squad", "--open-only"), "--open-only"),
])
def test_flags_that_do_not_go_together_are_refused_before_anything_is_contacted(
        comment, fake, argv, told):
    result = comment(*argv)
    assert result.code == 2 and told in result.err and result.out == ""
    assert fake.calls == []


@pytest.mark.parametrize("argv", [(), ("--add", "Hi", "--on", "x", "--list")])
def test_exactly_one_of_add_and_list_is_needed(comment, fake, argv):
    result = comment(*argv)
    assert result.code == 2 and "--add" in result.err and "--list" in result.err
    assert fake.calls == []


# --- listing ----------------------------------------------------------------------------------

def _held(cid, when, text, resolved=False):
    return {"id": cid, "createdTime": when, "content": text, "resolved": resolved,
            "author": {"displayName": "Laura Example"}}


def test_list_prints_every_comment_oldest_first_and_changes_nothing(comment, fake):
    fake.files[DOC_ID]["comments"] = [
        _held("c2", "2026-10-19T13:00:00Z", "Second.", resolved=True),
        _held("c1", "2026-10-19T12:00:00Z", "First."),
        dict(_held("c0", "2026-10-19T11:00:00Z", ""), deleted=True)]
    result = comment("--list")
    assert result.code == 0 and result.err == ""
    assert result.out == (
        "2 comments: 1 open, 1 resolved\n\n"
        "== Comment c1: open ==\nBy Laura Example, 2026-10-19 12:00 UTC\nFirst.\n\n"
        "== Comment c2: resolved ==\nBy Laura Example, 2026-10-19 13:00 UTC\nSecond.\n")
    assert fake.writes() == []
    assert not any(c["path"] == "/v1/documents/%s" % DOC_ID for c in fake.calls)


def test_list_open_only_leaves_out_the_resolved(comment, fake):
    fake.files[DOC_ID]["comments"] = [
        _held("c1", "2026-10-19T12:00:00Z", "First."),
        _held("c2", "2026-10-19T13:00:00Z", "Second.", resolved=True)]
    result = comment("--list", "--open-only")
    assert result.code == 0
    assert result.out == ("1 open comment (1 resolved left out)\n\n"
                          "== Comment c1: open ==\nBy Laura Example, 2026-10-19 12:00 UTC\n"
                          "First.\n")


def test_list_with_no_comments_says_so(comment):
    result = comment("--list")
    assert (result.code, result.out) == (0, "No comments.\n")


@pytest.mark.parametrize("kind,text", [
    ((), 'On "the test squad": Look'), (("--quote",), "Look")])
def test_a_comment_added_is_then_listed_with_its_words_either_way(comment, kind, text):
    assert comment("--add", "Look", "--on", "the test squad", *kind).code == 0
    result = comment("--list")
    assert '\nOn: "the test squad"\n%s\n' % text in result.out


# --- the refusals it shares with the other document commands --------------------------------

@pytest.mark.parametrize("argv,code,told", [
    (("not an id",), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
    (("https://docs.google.com/document/d/no-such-document-at-all/edit",), 5, "no-such-document-at-all"),
])
@pytest.mark.parametrize("mode", [("--list",), ("--add", "Hi", "--on", "the test squad")])
def test_it_refuses_what_the_other_document_commands_refuse_and_adds_nothing(
        comment, fake, argv, code, told, mode):
    result = comment(*(argv + mode), defaults=False)
    assert result.code == code
    assert told in result.err and result.out == ""
    assert fake.writes() == []


def test_a_document_in_the_bin_or_not_a_google_doc_is_exit_5(comment, fake):
    fake.files[DOC_ID]["trashed"] = True
    result = comment("--list")
    assert result.code == 5 and "in the bin" in result.err and fake.writes() == []
    fake.files[DOC_ID]["trashed"] = False
    fake.files[DOC_ID]["mimeType"] = "application/pdf"
    result = comment("--list")
    assert result.code == 5 and "not a Google Doc" in result.err


def test_the_document_may_be_given_by_its_whole_address(comment, fake):
    result = comment("https://docs.google.com/document/d/%s/edit?usp=sharing" % DOC_ID, "--list",
                     defaults=False)
    assert (result.code, result.out) == (0, "No comments.\n")


def test_an_unreadable_settings_file_is_exit_2(comment, fake, tmp_path):
    result = comment("--list", "--settings", str(tmp_path / "missing.conf"))
    assert result.code == 2 and "missing.conf" in result.err and fake.calls == []


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(comment, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_CLIENT_SECRET"]
    result = comment("--list", environment=environment)
    assert result.code == 3 and "GOOGLE_OAUTH_CLIENT_SECRET" in result.err
    assert fake.calls == []


def test_a_refused_sign_in_is_exit_3(comment, fake, env):
    result = comment("--list", environment=dict(env, GOOGLE_OAUTH_REFRESH_TOKEN="old"))
    assert result.code == 3 and "google-sign-in" in result.err and fake.writes() == []


# --- failures at Google -----------------------------------------------------------------------

@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document")])
def test_google_out_of_reach_before_adding_is_exit_4_and_says_nothing_was_added(
        comment, fake, after, step):
    fake.unreachable_after = after
    result = comment("--add", "Hi", "--on", "the test squad")
    assert result.code == 4 and result.out == ""
    assert "could not be reached" in result.err and step in result.err
    assert "Nothing was added" in result.err and posts(fake) == []


def test_google_out_of_reach_while_adding_is_tried_once_and_says_to_list_before_trying_again(
        comment, fake):
    fake.unreachable_after = 3
    result = comment("--add", "Hi", "--on", "the test squad")
    assert result.code == 4 and result.out == ""
    assert result.err == (
        "comment-doc: Google could not be reached while adding the comment: the "
        "stand-in is unplugged. The comment may or may not have been added: run "
        "comment-doc %s --list to see before trying again.\n" % DOC_ID)
    assert len(fake.calls) == 3 and fake.refused == 1  # the add was asked for once, not again


def test_an_error_from_google_when_adding_is_exit_4_with_its_words_and_is_not_retried(
        comment, fake):
    fake.answers[("POST", "/drive/v3/files/%s/comments" % DOC_ID)] = (
        403, {"error": {"code": 403, "message": "The user does not have sufficient permissions."}})
    result = comment("--add", "Hi", "--on", "the test squad")
    assert result.code == 4 and result.out == ""
    assert "403" in result.err and "sufficient permissions" in result.err
    assert "adding the comment" in result.err and "Nothing was added" in result.err
    assert len(posts(fake)) == 1


def test_google_out_of_reach_while_listing_is_exit_4(comment, fake):
    fake.unreachable_after = 2
    result = comment("--list")
    assert result.code == 4 and "reading the comments" in result.err and result.out == ""


def test_an_error_from_google_when_listing_is_exit_4_with_its_words(comment, fake):
    fake.answers[("GET", "/drive/v3/files/%s/comments" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = comment("--list")
    assert result.code == 4 and "500" in result.err and "Backend Error" in result.err
    assert "reading the comments" in result.err


# --- running it -------------------------------------------------------------------------------

def test_help_says_whom_it_may_address_and_what_the_exit_codes_mean(comment):
    out = " ".join(comment("--help", defaults=False).out.split())
    assert "0 done" in out and "5 there is no such document" in out
    assert "never changes the document" in out


def test_the_command_runs_from_any_folder(tmp_path):
    import os
    import subprocess
    import sys

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "comment-doc"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0
    assert "--add" in done.stdout and done.stderr == ""


def test_with_nothing_given_it_uses_the_environment_home_settings_and_google(
        fake, env, tmp_path, monkeypatch, capsys):
    from googledocstools import comment_doc, google

    fake.add_described(DOC_ID, DOC_NAME, ["root"], doc_paragraphs())
    home = tmp_path / "home"
    home.mkdir()
    (home / ".google-docs-tools.conf").write_text("COMMENT_RECIPIENTS=laura@example.org\n",
                                                  encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(google, "https_send", fake)
    assert comment_doc.main([DOC_ID, "--list"]) == 0
    assert capsys.readouterr().out == "No comments.\n"
    assert comment_doc.main([DOC_ID, "--add", "Hi", "--on", "the test squad", "--to",
                             "laura@example.org", "--dry-run"]) == 0
    assert capsys.readouterr().out.startswith("Would add a comment on")
