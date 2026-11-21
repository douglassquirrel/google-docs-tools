"""insert-paragraphs against the stand-in: new paragraphs put in as suggestions or outright, and
every refusal."""
import json
import os
import subprocess
import sys

import pytest

from googledocstools.document import paragraphs
from googledocstools.text import as_text
from tests.conftest import INSERTED, Para, described
from tests.tier2.conftest import DOC_ID

CHANGE = ("POST", "/v1/documents/%s:batchUpdate" % DOC_ID)
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"
LINES = [
    "Document: A draft for tests",
    "After: The first paragraph under it.",
    "  1 | heading 3 | A new heading",
    "  2 | paragraph | A plain paragraph with an *italic* word.",
    "  3 | paragraph | {A placeholder}",
    "  4 | list item | one",
    "  5 | list item | two",
]
READ = ("## A heading\n\nThe first paragraph under it.\n\n### A new heading\n\nA plain paragraph "
        "with an *italic* word.\n\n{A placeholder}\n\n- one\n\n- two\n\nThe end.\n")


def sent(fake):
    """The changes sent to Google, as JSON."""
    return [json.loads(c["body"].decode("utf-8")) for c in fake.calls
            if (c["method"], c["path"]) == CHANGE]


def as_read(fake, mode="SUGGESTIONS_INLINE"):
    """The document as read-doc would show it."""
    return as_text(paragraphs(described(fake.structured(DOC_ID, mode))))


def ends(fake):
    """Each paragraph's own paragraph style and bullet, as the stand-in holds them."""
    return [(style.get("paragraph"), style.get("bullet"))
            for character, style in fake.files[DOC_ID]["characters"] if character == "\n"]


def test_help_names_the_flags_and_contacts_nothing(put, fake):
    result = put("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "CONTENT", "--after", "--before", "--direct", "--dry-run", "--timeout",
                 "suggestion", "read-doc"):
        assert word in result.out
    assert fake.calls == []


def test_new_paragraphs_are_suggested_after_the_paragraph_holding_the_words(put, fake):
    result = put("--after", "first paragraph")
    assert (result.code, result.err) == (0, "")
    assert result.out.splitlines() == LINES + [
        "5 new paragraphs suggested; each is in the document."]
    assert fake.writes() == [CHANGE]
    assert sent(fake)[0]["writeControl"] == {"requiredRevisionId": "revision-1",
                                              "writeMode": "SUGGEST"}
    assert as_read(fake, ACCEPTED) == READ
    marked = [sorted({bool(style.get(INSERTED)) for _, style in runs})
              for runs in fake.paragraphs(DOC_ID)]
    assert marked == [[False], [False], [True], [True], [True], [True], [True], [False]]
    assert [c["query"] for c in fake.calls if c["path"] == "/v1/documents/" + DOC_ID] == [
        {}, {"suggestionsViewMode": [ACCEPTED]}]


def test_direct_puts_them_in_outright_each_with_its_own_kind_and_nothing_else(put, fake):
    result = put("--after", "first paragraph", "--direct")
    assert result.code == 0, result.err
    assert result.out.splitlines()[-1] == "5 new paragraphs made; each is in the document."
    assert sent(fake)[0]["writeControl"] == {"requiredRevisionId": "revision-1"}
    assert as_read(fake) == READ
    styles = ends(fake)
    assert styles[2:7] == [
        ({"namedStyleType": "HEADING_3"}, None), ({"namedStyleType": "NORMAL_TEXT"}, None),
        ({"namedStyleType": "NORMAL_TEXT"}, None),
        ({"namedStyleType": "NORMAL_TEXT"}, {"listId": styles[5][1]["listId"]}),
        ({"namedStyleType": "NORMAL_TEXT"}, {"listId": styles[5][1]["listId"]})]


def test_before_puts_them_in_before_the_paragraph(put, fake):
    result = put("--before", "The end", "--direct")
    assert result.code == 0, result.err
    assert result.out.splitlines()[1] == "Before: The end."
    assert as_read(fake) == READ


def test_after_the_last_paragraph_they_go_at_the_end(put, fake):
    result = put("--after", "The end", "--direct")
    assert result.code == 0, result.err
    assert as_read(fake) == ("## A heading\n\nThe first paragraph under it.\n\nThe end.\n\n### A "
                             "new heading\n\nA plain paragraph with an *italic* word.\n\n"
                             "{A placeholder}\n\n- one\n\n- two\n")


def test_they_take_no_look_from_the_paragraphs_beside_them(put, fake):
    loud = {"bold": True, "fontSize": {"magnitude": 20, "unit": "PT"},
            "weightedFontFamily": {"fontFamily": "Courier New"}}
    put.content.write_text("Plain.\n\n- item\n", encoding="utf-8")
    for argv in (("--after", "Place"), ("--before", "Next"), ("--after", "Next")):
        put.document([Para([("Place.", loud)], {
            "namedStyleType": "HEADING_1", "alignment": "CENTER",
            "indentStart": {"magnitude": 36, "unit": "PT"}}),
                      Para([("Next.", loud)], {"namedStyleType": "TITLE", "alignment": "END"})])
        result = put(*argv, "--direct")
        assert result.code == 0, result.err
        new = [(runs, end) for runs, end in zip(fake.paragraphs(DOC_ID), ends(fake))
               if runs and runs[0][0] in ("Plain.", "item")]
        assert [(runs, end[0]) for runs, end in new] == [
            ([("Plain.", {})], {"namedStyleType": "NORMAL_TEXT"}),
            ([("item", {})], {"namedStyleType": "NORMAL_TEXT"})]
        assert new[0][1][1] is None and new[1][1][1] is not None


@pytest.mark.parametrize("argv", [("--after", "First"), ("--before", "One item"),
                                  ("--after", "One item")])
def test_bullets_from_a_list_item_beside_them_are_not_taken_on(put, fake, argv):
    put.document(["First paragraph.", Para("One item", bullet={"listId": "old-list"})])
    put.content.write_text("Plain.", encoding="utf-8")
    result = put(*argv, "--direct")
    assert result.code == 0, result.err
    assert [end[1] for runs, end in zip(fake.paragraphs(DOC_ID), ends(fake))
            if runs == [("Plain.", {})]] == [None]
    assert {"listId": "old-list"} in [end[1] for end in ends(fake)]


@pytest.mark.parametrize("argv,said", [((), "would be suggested"), (("--direct",), "would be made")])
def test_dry_run_checks_everything_and_writes_nothing(put, fake, argv, said):
    result = put("--after", "first paragraph", "--dry-run", *argv)
    assert result.code == 0
    assert result.out.splitlines() == LINES + [
        "5 new paragraphs %s; nothing changed (--dry-run)." % said]
    assert fake.writes() == []


def test_one_new_paragraph_is_said_in_the_singular_and_a_long_one_cut_short(put):
    put.content.write_text("A paragraph long enough that the line saying what it is must be "
                           "cut short.", encoding="utf-8")
    result = put("--after", "first paragraph")
    assert result.out.splitlines()[2:] == [
        "  1 | paragraph | A paragraph long enough that the line saying what it is mus…",
        "1 new paragraph suggested; each is in the document."]


def test_quotes_dashes_and_hostile_text_are_data(put, fake):
    hostile = "it's a \\ \"test\" $HOME </script> é 🐿️ – “so”"
    put.document(["Before " + hostile + " after."])
    put.content.write_text("New: " + hostile, encoding="utf-8")
    result = put("--after", "Before " + hostile, "--direct")
    assert result.code == 0, result.err
    assert fake.paragraphs(DOC_ID) == [[("Before " + hostile + " after.", {})],
                                       [("New: " + hostile, {})]]


@pytest.mark.parametrize("words,told", [
    ("Not there", '"Not there" is not in the document'),
    ("One", '"One" is in the document 2 times'),
    ("pending", '"pending" touches text in a pending suggestion'),
])
def test_words_not_there_once_are_refused_and_nothing_is_changed(put, fake, words, told):
    put.document(["One paragraph.", "One more.", [("pending", {INSERTED: ["s1"]}), (" text", {})]])
    result = put("--after", words)
    assert result.code == 5 and result.out == ""
    assert result.err.startswith("insert-paragraphs: " + told) and "Nothing was changed" in (
        result.err)
    assert fake.writes() == []


@pytest.mark.parametrize("content,told", [
    (b"####### Seven\n", "line 1: a heading has one to six #, not 7"),
    (b"\n\n", "there are no paragraphs in it"),
    (b"\xff\xfe not text", "UTF-8"),
    (b"Words: the first paragraph again.", '"first paragraph" themselves'),
])
def test_a_bad_content_file_is_exit_2_naming_its_faults_and_nothing_is_contacted(
        put, fake, content, told):
    put.content.write_bytes(content)
    result = put("--after", "first paragraph")
    assert result.code == 2 and told in result.err
    assert "new paragraphs for chapter 1.md" in result.err or "themselves" in result.err
    assert fake.calls == []


def test_a_content_file_that_is_not_there_is_exit_2(put, fake):
    put.content.unlink()
    result = put("--after", "first paragraph")
    assert result.code == 2 and "could not be read" in result.err and fake.calls == []


@pytest.mark.parametrize("argv,told", [
    ((), "--after"),
    (("--after", "a", "--before", "b"), "not allowed with"),
    (("--after", ""), "words"),
    (("--before", "two\nlines"), "line break"),
])
def test_a_place_not_said_once_and_plainly_is_exit_2(put, fake, argv, told):
    result = put(*argv)
    assert result.code == 2 and told in result.err and fake.calls == []


def test_a_document_changed_between_reading_and_writing_is_refused_and_left_alone(put, fake):
    fake.edited_after_reading, fake.edits_left = True, 1
    result = put("--after", "first paragraph")
    assert result.code == 4 and "changed" in result.err and "again" in result.err
    assert len(fake.paragraphs(DOC_ID)) == 3


def test_new_paragraphs_not_in_the_document_afterwards_are_exit_5(put, fake):
    fake.answers[CHANGE] = (200, {"documentId": DOC_ID, "replies": []})
    result = put("--after", "first paragraph")
    assert result.code == 5
    assert result.out.splitlines()[2:] == [
        line + " | NOT in the document afterwards" for line in LINES[2:]]
    assert result.err == (
        "insert-paragraphs: 5 of the 5 new paragraphs are not in the document as written: look "
        "at it before running this again, which could put them in twice.\n")


@pytest.mark.parametrize("argv,code,told", [
    (("not an id",), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
])
def test_a_bad_id_or_an_unknown_document_is_refused(put, argv, code, told):
    result = put(*argv, str(put.content), "--after", "first", defaults=False)
    assert result.code == code and told in result.err and result.out == ""


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(put, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_REFRESH_TOKEN"]
    result = put("--after", "first", environment=environment)
    assert result.code == 3 and fake.calls == []


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document"),
    (4, "reading the document again")])
def test_google_out_of_reach_is_exit_4_naming_the_step(put, fake, after, step):
    fake.unreachable_after = after
    result = put("--after", "first")
    assert result.code == 4 and step in result.err


def test_out_of_reach_while_changing_says_they_may_or_may_not_be_in(put, fake):
    fake.unreachable_after = 3
    result = put("--after", "first")
    assert result.code == 4
    assert "may or may not" in result.err and "read-doc" in result.err


def test_an_error_from_google_on_the_change_is_exit_4_with_its_words(put, fake):
    fake.answers[CHANGE] = (500, {"error": {"code": 500, "message": "Backend Error"}})
    result = put("--after", "first")
    assert result.code == 4 and "Backend Error" in result.err and "nothing was changed" in (
        result.err)


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "insert-paragraphs"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--before" in done.stdout and done.stderr == ""


def test_an_error_from_google_on_the_second_read_is_exit_4_saying_so(put, fake, env, capsys):
    reads = []

    def send(method, url, headers, body, timeout):
        if method == "GET" and "/v1/documents/" in url:
            reads.append(url)
            if len(reads) == 2:
                return 503, b'{"error": {"code": 503, "message": "Unavailable"}}'
        return fake(method, url, headers, body, timeout)

    from googledocstools import insert_paragraphs
    code = insert_paragraphs.main([DOC_ID, str(put.content), "--after", "first paragraph"],
                                  env=env, send=send)
    assert code == 4 and fake.writes() == [CHANGE]
    err = capsys.readouterr().err
    assert "Unavailable" in err and "reading the document again" in err
