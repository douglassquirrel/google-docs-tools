"""insert-footnote against the stand-in: a footnote put in after given words, as a suggestion or
outright, in two writes, and every refusal."""
import json
import os
import subprocess
import sys

import pytest

from googledocstools import insert_footnote
from tests.conftest import DELETED, FOOTNOTE, INSERTED
from tests.tier2.conftest import DOC_ID, SECRETS

CHANGE = ("POST", "/v1/documents/%s:batchUpdate" % DOC_ID)
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"
TEXT = "Jo Bloggs, *A Made-Up Book*, p. 3."
NOTE = [(" Jo Bloggs, ", {}), ("A Made-Up Book", {"italic": True}), (", p. 3.", {})]
LINES = ["Document: A draft for tests", "After: …has a phrase", "Text: " + TEXT]


def sent(fake):
    """The changes sent to Google, as JSON."""
    return [json.loads(c["body"].decode("utf-8")) for c in fake.calls
            if (c["method"], c["path"]) == CHANGE]


def body(fake, mode=ACCEPTED):
    """The second paragraph, as plain text with the mark shown as ^id, in a view mode."""
    return "".join("^" + style["footnote"] if text == FOOTNOTE else text
                   for text, style in fake.paragraphs(DOC_ID, mode)[1])


def the_note(fake):
    (note_id,) = fake.files[DOC_ID]["footnotes"]
    return note_id


def plain(runs):
    return [(text, {k: v for k, v in style.items() if k not in (INSERTED, DELETED)})
            for text, style in runs]


def test_help_names_the_flags_and_contacts_nothing(footnote, fake):
    result = footnote("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--after", "--text", "--remove", "--direct", "--dry-run", "--timeout",
                 "suggestion", "italic", "read-doc --footnotes"):
        assert word in result.out
    assert fake.calls == []


def test_a_footnote_is_suggested_after_the_words_in_two_writes(footnote, fake):
    result = footnote("--after", "has a phrase", "--text", TEXT)
    assert (result.code, result.err) == (0, "")
    assert result.out.splitlines() == LINES + [
        "Footnote 1 suggested; the mark and its text are in the document."]
    assert fake.writes() == [CHANGE, CHANGE]
    first, second = sent(fake)
    assert first["writeControl"] == {"requiredRevisionId": "revision-1", "writeMode": "SUGGEST"}
    assert second["writeControl"] == {"requiredRevisionId": "revision-2", "writeMode": "SUGGEST"}
    note_id = the_note(fake)
    assert body(fake) == "The second has a phrase^%s [source: an article] in it." % note_id
    assert plain(fake.footnote(DOC_ID, note_id)[0]) == NOTE
    assert all(style.get(INSERTED) for text, style in fake.footnote(DOC_ID, note_id)[0])
    assert [style.get(INSERTED) is not None for text, style in fake.paragraphs(DOC_ID)[1]
            if text == FOOTNOTE] == [True]
    assert [c["query"] for c in fake.calls if c["path"] == "/v1/documents/" + DOC_ID] == [
        {}, {"suggestionsViewMode": [ACCEPTED]}]


def test_direct_makes_it_outright(footnote, fake):
    result = footnote("--after", "has a phrase", "--text", TEXT, "--direct")
    assert result.code == 0, result.err
    assert result.out.splitlines()[-1] == (
        "Footnote 1 made; the mark and its text are in the document.")
    first, second = sent(fake)
    assert first["writeControl"] == {"requiredRevisionId": "revision-1"}
    assert second["writeControl"] == {"requiredRevisionId": "revision-2"}
    note_id = the_note(fake)
    assert body(fake, "SUGGESTIONS_INLINE") == (
        "The second has a phrase^%s [source: an article] in it." % note_id)
    assert fake.footnote(DOC_ID, note_id)[0] == NOTE


def test_remove_takes_the_note_out_and_the_mark_stands_where_it_was(footnote, fake):
    result = footnote("--after", "a phrase", "--remove", " [source: an article]", "--text", TEXT)
    assert result.code == 0, result.err
    assert result.out.splitlines() == [
        "Document: A draft for tests", "After: …has a phrase",
        'Removed: " [source: an article]"', "Text: " + TEXT,
        "Footnote 1 suggested; the mark and its text are in the document."]
    assert body(fake) == "The second has a phrase^%s in it." % the_note(fake)
    deleted = "".join(text for text, style in fake.paragraphs(DOC_ID)[1] if style.get(DELETED))
    assert deleted == " [source: an article]"
    assert len(fake.writes()) == 2


def test_remove_outright_deletes_the_words(footnote, fake):
    result = footnote("--after", "a phrase", "--remove", " [source: an article]", "--text", TEXT,
                      "--direct")
    assert result.code == 0, result.err
    assert body(fake, "SUGGESTIONS_INLINE") == "The second has a phrase^%s in it." % the_note(fake)


def test_a_later_footnote_before_an_earlier_one_takes_its_number(footnote, fake):
    footnote.document(["The first paragraph, with a quoted line.",
                       [("The second has a phrase", {}), (FOOTNOTE, {"footnote": "old"}),
                        (" in it.", {})]], footnotes={"old": "An older note."})
    result = footnote("--after", "quoted line", "--text", "A newer note.")
    assert result.code == 0, result.err
    assert result.out.splitlines()[-1] == (
        "Footnote 1 suggested; the mark and its text are in the document.")
    assert fake.footnote(DOC_ID, "old") == [[(" An older note.", {})]]


def test_dry_run_says_what_would_be_done_and_writes_nothing(footnote, fake):
    result = footnote("--after", "a phrase", "--remove", " [source: an article]", "--text", TEXT,
                      "--dry-run")
    assert (result.code, result.err) == (0, "")
    assert result.out.splitlines() == [
        "Document: A draft for tests", "After: …has a phrase",
        'Removed: " [source: an article]"', "Text: " + TEXT,
        "A footnote would be suggested; nothing changed (--dry-run)."]
    assert fake.writes() == []
    result = footnote("--after", "a phrase", "--text", TEXT, "--dry-run", "--direct")
    assert result.out.splitlines()[-1] == "A footnote would be made; nothing changed (--dry-run)."


@pytest.mark.parametrize("argv, told", [
    (["--after", "no such words", "--text", "x"], '"no such words" is not in the document.'),
    (["--after", "The", "--text", "x"], '"The" is in the document 2 times'),
    (["--after", "a phrase", "--remove", " in it", "--text", "x"],
     '" in it" is not straight after "a phrase"'),
])
def test_words_that_do_not_say_one_place_are_refused_and_nothing_is_written(footnote, fake, argv,
                                                                            told):
    result = footnote(*argv)
    assert result.code == 5
    assert told in result.err and result.err.rstrip().endswith("Nothing was changed.")
    assert fake.writes() == []


def test_words_touching_a_pending_suggestion_are_refused(footnote, fake):
    footnote.document([[("Some ", {}), ("new ", {INSERTED: ["s.1"]}), ("words here.", {})]])
    result = footnote("--after", "Some new words", "--text", "x")
    assert result.code == 5
    assert "touches text in a pending suggestion" in result.err
    assert fake.writes() == []


@pytest.mark.parametrize("argv, told", [
    (["--after", "a phrase"], "the following arguments are required: --text"),
    (["--text", "x"], "the following arguments are required: --after"),
    (["--after", " ", "--text", "x"], "--after needs the words the mark goes after."),
    (["--after", "a\nphrase", "--text", "x"], "--after: the words must lie within one paragraph"),
    (["--after", "a phrase", "--text", ""], "--text needs the footnote's words."),
    (["--after", "a phrase", "--text", "*open"], "--text: '*' is opened here"),
    (["--after", "a phrase", "--remove", "", "--text", "x"], "--remove needs the words to take out"),
    (["--after", "a phrase", "--remove", "a\nb", "--text", "x"],
     "--remove: the words must lie within one paragraph"),
])
def test_bad_arguments_are_exit_2_before_google_is_asked(footnote, fake, argv, told):
    result = footnote(*argv)
    assert result.code == 2
    assert told in result.err
    assert fake.calls == []


def test_a_document_changed_while_reading_is_exit_4_and_nothing_changed(footnote, fake):
    fake.edited_after_reading = True
    fake.edits_left = 1
    result = footnote("--after", "a phrase", "--text", TEXT)
    assert result.code == 4
    assert "changed while insert-footnote was reading it, so nothing was changed" in result.err
    assert fake.files[DOC_ID]["footnotes"] == {}


def test_google_out_of_reach_at_the_first_write_says_the_mark_may_be_there(footnote, fake):
    fake.unreachable_after = 3  # the sign-in, the file and the document, then nothing
    result = footnote("--after", "a phrase", "--text", TEXT)
    assert result.code == 4
    assert "while making the footnote's mark" in result.err
    assert "before running this again, which could put in a second" in result.err


def test_an_error_at_the_first_write_is_exit_4_and_nothing_changed(footnote, fake):
    fake.answers[CHANGE] = (400, {"error": {"code": 400, "message": "Bad footnote"}})
    result = footnote("--after", "a phrase", "--text", TEXT)
    assert result.code == 4
    assert "Bad footnote" in result.err and "nothing was changed" in result.err


def run_failing_second(fake, env, capsys, argv, answer=None):
    """Run insert-footnote with the second change failing: Google answers it with an error, or
    (answer None) cannot be reached."""
    posts = []

    def send(method, url, headers, data, timeout):
        if method == "POST" and url.endswith(":batchUpdate"):
            posts.append(url)
            if len(posts) == 2:
                if answer is None:
                    raise insert_footnote.google.Unreachable("the line went dead")
                return answer[0], json.dumps(answer[1]).encode("utf-8")
        return fake(method, url, headers, data, timeout)

    code = insert_footnote.main([DOC_ID] + argv, env=env, send=send)
    captured = capsys.readouterr()
    for secret in SECRETS:
        assert secret not in captured.out + captured.err
    assert "Traceback" not in captured.err
    return code, captured.err


@pytest.mark.parametrize("answer, said, holds", [
    ((400, {"error": {"code": 400, "message": "Footnote trouble"}}), "Footnote trouble",
     "The document now holds"),
    (None, "the line went dead", "The document may now hold"),
])
def test_a_failed_second_write_says_plainly_an_empty_mark_was_left(footnote, fake, env, capsys,
                                                                   answer, said, holds):
    code, err = run_failing_second(fake, env, capsys, ["--after", "a phrase", "--text", TEXT],
                                   answer)
    assert code == 4
    assert said in err
    assert '%s an empty footnote mark after "…has a phrase", suggested' % holds in err
    assert "before running this again, which would put in a second" in err
    assert len(fake.writes()) == 1  # no retry, no undo
    assert plain(fake.footnote(DOC_ID, the_note(fake))[0]) == [(" ", {})]


def test_an_answer_naming_no_footnote_says_an_empty_mark_may_be_left(footnote, fake):
    fake.answers[CHANGE] = (200, {"replies": [{}], "writeControl": {"requiredRevisionId": "r"}})
    result = footnote("--after", "a phrase", "--text", TEXT, "--direct")
    assert result.code == 4
    assert "Google did not say which footnote it made" in result.err
    assert 'The document now holds an empty footnote mark after "…has a phrase", made' in result.err
    assert len(fake.writes()) == 1


def test_a_footnote_not_as_written_afterwards_is_exit_5(footnote, fake, env, capsys):
    def send(method, url, headers, data, timeout):
        status, answer = fake(method, url, headers, data, timeout)
        if method == "GET" and "suggestionsViewMode" in url:
            described = json.loads(answer.decode("utf-8"))
            described.pop("footnotes", None)
            answer = json.dumps(described).encode("utf-8")
        return status, answer

    code = insert_footnote.main([DOC_ID, "--after", "a phrase", "--text", TEXT], env=env,
                                send=send)
    captured = capsys.readouterr()
    assert code == 5
    assert "the footnote's text is not as written" in captured.err
    assert "Look at it before running this again" in captured.err


def test_quotes_backslashes_dollars_script_and_non_ascii_are_data(footnote, fake):
    odd = 'Say “$HOME” \\ </script> — naïve'
    footnote.document([odd + " and on."])
    result = footnote("--after", odd, "--text", odd, "--direct")
    assert result.code == 0, result.err
    assert fake.footnote(DOC_ID, the_note(fake)) == [[(" " + odd, {})]]


def test_the_command_runs_as_a_program_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run([sys.executable, os.path.join(here, "insert-footnote"), "--help"],
                          cwd=str(tmp_path), capture_output=True, text=True, check=False)
    assert done.returncode == 0 and "insert-footnote" in done.stdout


def test_google_failing_on_the_read_afterwards_is_exit_4_naming_the_step(footnote, fake):
    fake.unreachable_after = 5  # everything up to and including the second change
    result = footnote("--after", "a phrase", "--text", TEXT)
    assert result.code == 4
    assert ("Google could not be reached while reading the document again, to check the "
            "footnote is there") in result.err


def test_an_error_on_the_read_afterwards_is_exit_4_with_its_words(fake, env, capsys):
    from tests.tier2.conftest import DOC_NAME
    fake.add_document(DOC_ID, DOC_NAME, ["root"], ["A phrase here."])

    def send(method, url, headers, data, timeout):
        if method == "GET" and "suggestionsViewMode" in url:
            return 500, json.dumps({"error": {"code": 500, "message": "Backend gone"}}).encode()
        return fake(method, url, headers, data, timeout)

    code = insert_footnote.main([DOC_ID, "--after", "A phrase", "--text", "x"], env=env, send=send)
    assert code == 4
    assert "Backend gone" in capsys.readouterr().err
