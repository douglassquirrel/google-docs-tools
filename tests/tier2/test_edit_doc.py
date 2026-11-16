"""edit-doc against the stand-in: edits made as suggestions or outright, and every refusal."""
import json
import os
import subprocess
import sys

import pytest

from tests.conftest import DELETED, INSERTED
from tests.tier2.conftest import DOC_ID

CHANGE = ("POST", "/v1/documents/%s:batchUpdate" % DOC_ID)
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"


def sent(fake):
    """The one change sent to Google, as JSON."""
    return [json.loads(c["body"].decode("utf-8")) for c in fake.calls
            if (c["method"], c["path"]) == CHANGE]


def test_help_names_the_flags_and_contacts_nothing(edit, fake):
    result = edit("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "EDITS", "--direct", "--dry-run", "--timeout", "suggestion",
                 "propose-edits", "occurrence"):
        assert word in result.out
    assert fake.calls == []


def test_edits_are_suggested_marking_only_the_words_that_change(edit, fake):
    result = edit()
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "E1 | The [quick → slow] fox jumps. | suggested\n"
        "edit 2 | A [bold → strong] word here. | suggested\n"
        "2 edits suggested; each is in the document.\n")
    assert fake.writes() == [CHANGE]
    assert sent(fake)[0]["writeControl"] == {"requiredRevisionId": "revision-1",
                                              "writeMode": "SUGGEST"}
    assert fake.paragraphs(DOC_ID, ACCEPTED) == [
        [("The slow fox jumps.", {})],
        [("A ", {}), ("strong", {"bold": True}), (" word here.", {})]]
    marked = [(text, sorted(key for key in style if key in (INSERTED, DELETED)))
              for text, style in fake.paragraphs(DOC_ID)[0]]
    assert marked == [("The ", []), ("slow", [INSERTED]), ("quick", [DELETED]),
                      (" fox jumps.", [])]
    assert [c["query"] for c in fake.calls if c["path"] == "/v1/documents/" + DOC_ID] == [
        {}, {"suggestionsViewMode": [ACCEPTED]}]


def test_direct_makes_the_edits_outright(edit, fake):
    result = edit("--direct")
    assert result.code == 0
    assert result.out.splitlines() == [
        "E1 | The [quick → slow] fox jumps. | made",
        "edit 2 | A [bold → strong] word here. | made",
        "2 edits made; each is in the document."]
    assert sent(fake)[0]["writeControl"] == {"requiredRevisionId": "revision-1"}
    assert fake.paragraphs(DOC_ID) == [
        [("The slow fox jumps.", {})],
        [("A ", {}), ("strong", {"bold": True}), (" word here.", {})]]


@pytest.mark.parametrize("argv,said", [((), "would be suggested"), (("--direct",), "would be made")])
def test_dry_run_checks_everything_and_writes_nothing(edit, fake, argv, said):
    result = edit("--dry-run", *argv)
    assert result.code == 0
    assert result.out.splitlines() == [
        "E1 | The [quick → slow] fox jumps. | " + said,
        "edit 2 | A [bold → strong] word here. | " + said,
        "2 edits checked; nothing changed (--dry-run)."]
    assert fake.writes() == []


def test_one_edit_is_said_in_the_singular(edit):
    edit.write([{"find": "fox", "replace": "hare"}])
    assert edit().out.splitlines()[-1] == "1 edit suggested; each is in the document."


def test_deletions_and_insertions_and_an_occurrence(edit, fake):
    edit.document(["one and one and one", "Keep this here."])
    edit.write([{"find": " and one", "replace": "", "occurrence": 2},
                {"find": "this here", "replace": "this right here"}])
    result = edit("--direct")
    assert result.code == 0, result.err
    assert result.out.splitlines()[:2] == [
        "edit 1 | one and one[ and one → ] | made",
        "edit 2 | Keep this [ → right ]here. | made"]
    assert fake.paragraphs(DOC_ID) == [[("one and one", {})], [("Keep this right here.", {})]]


def test_curly_quotes_dashes_and_hostile_text_are_data(edit, fake):
    hostile = "it's a \\ \"test\" $HOME </script> é 🐿️ – “so”"
    edit.document(["Before " + hostile + " after."])
    edit.write([{"find": hostile, "replace": hostile.replace("it's", "it’s")}])
    result = edit("--direct")
    assert result.code == 0, result.err
    assert fake.paragraphs(DOC_ID) == [[("Before " + hostile.replace("it's", "it’s")
                                         + " after.", {})]]


def test_edits_that_cannot_be_made_are_all_named_and_nothing_is_changed(edit, fake):
    edit.document(["one and one", [("pending", {INSERTED: ["s1"]}), (" text", {})]])
    edit.write([{"find": "missing", "replace": "x"}, {"id": "E2", "find": "one", "replace": "1"},
                {"find": "pending", "replace": "x"}])
    result = edit()
    assert result.code == 5 and result.out == ""
    assert result.err == (
        "edit-doc: 3 of the 3 edits cannot be made, so nothing was changed:\n"
        '  edit 1: "missing" is not in the document (an edit cannot run across a paragraph '
        "break, a footnote mark, a chip or a picture)\n"
        '  E2: "one" is in the document 2 times; say which with "occurrence"\n'
        '  edit 3: "pending" touches text in a pending suggestion; accept or reject it first\n')
    assert fake.writes() == []


@pytest.mark.parametrize("content,told", [
    (b"[{", "not JSON"),
    (b'[{"find": "", "replace": "x"}]', '"find" must be text and not empty'),
    (b"\xff\xfe not text", "UTF-8"),
])
def test_a_bad_edits_file_is_exit_2_naming_its_faults_and_nothing_is_contacted(
        edit, fake, content, told):
    edit.edits.write_bytes(content)
    result = edit()
    assert result.code == 2 and told in result.err and "edits for chapter 1.json" in result.err
    assert fake.calls == []


def test_an_edits_file_that_is_not_there_is_exit_2(edit, fake):
    edit.edits.unlink()
    result = edit()
    assert result.code == 2 and "could not be read" in result.err and fake.calls == []


def test_a_document_changed_between_reading_and_writing_is_refused_and_left_alone(edit, fake):
    fake.edited_after_reading, fake.edits_left = True, 1
    result = edit()
    assert result.code == 4 and "changed" in result.err and "again" in result.err
    assert fake.paragraphs(DOC_ID) == [[("!The quick fox jumps.", {})],
                                      [("A ", {}), ("bold", {"bold": True}), (" word here.", {})]]


def test_an_edit_not_in_the_document_afterwards_is_exit_5(edit, fake):
    fake.answers[CHANGE] = (200, {"documentId": DOC_ID, "replies": [{}, {}]})
    result = edit()
    assert result.code == 5
    assert result.out.splitlines() == [
        "E1 | The [quick → slow] fox jumps. | suggested, but NOT in the document afterwards",
        "edit 2 | A [bold → strong] word here. | suggested, but NOT in the document afterwards"]
    assert "2 of the 2 edits are not in the document as expected" in result.err


@pytest.mark.parametrize("argv,code,told", [
    (("not an id", "x.json"), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
])
def test_a_bad_id_or_an_unknown_document_is_refused(edit, argv, code, told):
    args = argv if len(argv) == 2 else argv + (str(edit.edits),)
    result = edit(*args, defaults=False)
    assert result.code == code and told in result.err and result.out == ""


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(edit, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_REFRESH_TOKEN"]
    result = edit(environment=environment)
    assert result.code == 3 and fake.calls == []


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document"),
    (4, "reading the document again")])
def test_google_out_of_reach_is_exit_4_naming_the_step(edit, fake, after, step):
    fake.unreachable_after = after
    result = edit()
    assert result.code == 4 and step in result.err


def test_out_of_reach_while_changing_says_the_edits_may_or_may_not_be_made(edit, fake):
    fake.unreachable_after = 3
    result = edit()
    assert result.code == 4
    assert "may or may not" in result.err and "read-doc" in result.err


def test_an_error_from_google_on_the_change_is_exit_4_with_its_words(edit, fake):
    fake.answers[CHANGE] = (500, {"error": {"code": 500, "message": "Backend Error"}})
    result = edit()
    assert result.code == 4 and "Backend Error" in result.err and "nothing was changed" in (
        result.err)


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "edit-doc"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--direct" in done.stdout and done.stderr == ""


def test_an_error_from_google_on_the_second_read_is_exit_4_saying_so(edit, fake):
    reads = []

    def send(method, url, headers, body, timeout):
        if method == "GET" and "/v1/documents/" in url:
            reads.append(url)
            if len(reads) == 2:
                return 503, b'{"error": {"code": 503, "message": "Unavailable"}}'
        return fake(method, url, headers, body, timeout)

    from googledocstools import edit_doc
    code = edit_doc.main([DOC_ID, str(edit.edits)], env={
        "GOOGLE_OAUTH_CLIENT_ID": "client-id-for-tests",
        "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret-for-tests",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "refresh-token-for-tests"}, send=send)
    assert code == 4 and fake.writes() == [CHANGE]
