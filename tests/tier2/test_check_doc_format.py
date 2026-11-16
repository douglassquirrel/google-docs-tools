"""check-doc-format against the stand-in: a document checked against a house format and fixed."""
import json
import os
import subprocess
import sys

import pytest

from tests.conftest import Para
from tests.tier1.test_doc_format import H2, H3, LISTED, PAGE, dim
from tests.tier2.conftest import DOC_ID

CHANGE = ("POST", "/v1/documents/%s:batchUpdate" % DOC_ID)
ARIAL = {"weightedFontFamily": {"fontFamily": "Arial"}, "fontSize": dim(11)}


def book():
    """An invented chapter in the house format, but for a pasted paragraph and a list item."""
    return [
        Para("Chapter 1: The start", H2),
        "Body text in the house format.",
        Para([("Pasted from the web.", ARIAL)], {"lineSpacing": 100}),
        Para("An indented item.", {"indentFirstLine": dim(18)}, {"listId": "list-1"}),
        Para("A section", H3),
        [("More text with ", {}), ("emphasis", {"italic": True}), (".", {})],
    ]


def texts(fake):
    return ["".join(text for text, _ in runs) for runs in fake.paragraphs(DOC_ID)]


REPORT = (
    "body text: font not Times New Roman: 1 paragraph\n"
    '  under "## Chapter 1: The start": Pasted from the web.\n'
    "body text: size not 12 pt: 1 paragraph\n"
    '  under "## Chapter 1: The start": Pasted from the web.\n'
    "body text: line spacing not 2: 1 paragraph\n"
    '  under "## Chapter 1: The start": Pasted from the web.\n'
    "list items: first-line indent not 0 in: 1 paragraph\n"
    '  under "## Chapter 1: The start": An indented item.\n'
    "Format: 4 problems in 2 paragraphs.\n")


def test_help_names_the_flags_and_contacts_nothing(doc_format, fake):
    result = doc_format("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--format", "--fix", "--dry-run", "-v", "--timeout", "never"):
        assert word in result.out
    assert fake.calls == []


def test_the_check_reports_what_does_not_match_exit_1_and_writes_nothing(doc_format, fake):
    doc_format.document(book())
    result = doc_format()
    assert (result.code, result.err, result.out) == (1, "", REPORT)
    assert fake.writes() == []


def test_a_document_in_the_format_is_exit_0(doc_format):
    doc_format.document([Para("Chapter 1: The start", H2), "Body text.",
                         Para("An item.", LISTED, {"listId": "list-1"})])
    result = doc_format()
    assert (result.code, result.out) == (0, "Format: everything matches.\n")


def test_verbose_shows_every_paragraph(doc_format):
    doc_format.document([Para("Chapter 1: Start", H2)] + [
        Para([("Pasted %d." % n, {"weightedFontFamily": {"fontFamily": "Arial"}})])
        for n in range(5)])
    assert "-v shows them all" in doc_format().out
    result = doc_format("-v")
    assert result.out.count("Pasted") == 5 and "-v shows" not in result.out


def test_fix_sets_the_format_checks_again_and_changes_no_text(doc_format, fake):
    doc_format.document(book(), dict(PAGE, marginLeft=dim(90)))
    before = texts(fake)
    result = doc_format("--fix")
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "page: margins not 1 in\n" + REPORT.replace(
            "Format: 4 problems in 2 paragraphs.", "Format: 5 problems in 2 paragraphs and the page.")
        + "Set:\n"
        "  the page: margins 1 in\n"
        '  under "## Chapter 1: The start": Pasted from the web.: font Times New Roman, '
        "size 12 pt, line spacing 2\n"
        '  under "## Chapter 1: The start": An indented item.: first-line indent 0 in\n'
        "After the fix:\n"
        "Format: everything matches.\n")
    assert fake.writes() == [CHANGE]
    change = json.loads(fake.calls[[ (c["method"], c["path"]) for c in fake.calls].index(
        CHANGE)]["body"].decode("utf-8"))
    assert change["writeControl"] == {"requiredRevisionId": "revision-1"}
    assert texts(fake) == before
    assert fake.paragraphs(DOC_ID)[5] == [("More text with ", {}), ("emphasis", {"italic": True}),
                                          (".", {})]
    assert fake.files[DOC_ID]["documentStyle"]["marginLeft"] == dim(72)


def test_fix_leaves_what_it_must_not_fix_and_says_so_with_exit_1(doc_format, fake):
    doc_format.document([Para("The start", H2), [("Looks Like A Heading", {"bold": True})]])
    result = doc_format("--fix")
    assert result.code == 1
    assert result.out == (
        "heading 2: does not match ^Chapter \\d+: : 1 paragraph\n"
        "  at the start: The start\n"
        "body text: looks like a heading: 1 paragraph\n"
        '  under "## The start": Looks Like A Heading\n'
        "Format: 2 problems in 2 paragraphs.\n"
        "Nothing to set: what does not match is for a person to change.\n")
    assert fake.writes() == []


def test_fix_with_dry_run_says_what_it_would_set_and_writes_nothing(doc_format, fake):
    doc_format.document(book())
    result = doc_format("--fix", "--dry-run")
    assert result.code == 1
    assert result.out == REPORT + (
        "Would set:\n"
        '  under "## Chapter 1: The start": Pasted from the web.: font Times New Roman, '
        "size 12 pt, line spacing 2\n"
        '  under "## Chapter 1: The start": An indented item.: first-line indent 0 in\n'
        "Nothing changed (--dry-run).\n")
    assert fake.writes() == []


def test_a_document_changed_while_it_was_read_is_left_alone(doc_format, fake):
    doc_format.document(book())
    fake.edited_after_reading, fake.edits_left = True, 1
    result = doc_format("--fix")
    assert result.code == 4 and "changed" in result.err and "again" in result.err
    assert fake.paragraphs(DOC_ID)[2] == [("Pasted from the web.", ARIAL)]


def test_an_error_from_google_on_the_change_is_exit_4_and_nothing_changed(doc_format, fake):
    doc_format.document(book())
    fake.answers[CHANGE] = (500, {"error": {"code": 500, "message": "Backend Error"}})
    result = doc_format("--fix")
    assert result.code == 4 and "Backend Error" in result.err and "nothing was changed" in (
        result.err)


def test_out_of_reach_while_changing_says_it_may_or_may_not_be_done(doc_format, fake):
    doc_format.document(book())
    fake.unreachable_after = 3
    result = doc_format("--fix")
    assert result.code == 4 and "may or may not" in result.err


@pytest.mark.parametrize("content,told", [
    (b"{", "not JSON"),
    (b'{"body": {"font": 12}}', '"font" must be the name of a font'),
    (b"\xff not text", "UTF-8"),
])
def test_a_bad_format_file_is_exit_2_naming_its_faults_and_nothing_is_contacted(
        doc_format, fake, content, told):
    doc_format.file.write_bytes(content)
    result = doc_format()
    assert result.code == 2 and told in result.err and "house format.json" in result.err
    assert fake.calls == []


def test_a_format_file_that_is_not_there_or_not_named_is_exit_2(doc_format, fake):
    doc_format.file.unlink()
    assert doc_format().code == 2
    result = doc_format(DOC_ID, defaults=False)
    assert result.code == 2 and "--format" in result.err and fake.calls == []


@pytest.mark.parametrize("argv,code,told", [
    (("not an id",), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
])
def test_a_bad_id_or_an_unknown_document_is_refused(doc_format, argv, code, told):
    doc_format.document(book())
    result = doc_format(*(argv + ("--format", str(doc_format.file))), defaults=False)
    assert result.code == code and told in result.err and result.out == ""


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(doc_format, fake, env):
    doc_format.document(book())
    environment = dict(env)
    del environment["GOOGLE_OAUTH_CLIENT_ID"]
    result = doc_format(environment=environment)
    assert result.code == 3 and fake.calls == []


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document"),
    (4, "reading the document again")])
def test_google_out_of_reach_is_exit_4_naming_the_step(doc_format, fake, after, step):
    doc_format.document(book())
    fake.unreachable_after = after
    result = doc_format("--fix")
    assert result.code == 4 and step in result.err


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "check-doc-format"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--fix" in done.stdout and done.stderr == ""


def test_an_error_from_google_on_reading_is_exit_4_with_its_words(doc_format, fake):
    doc_format.document(book())
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = doc_format()
    assert result.code == 4 and "reading the document" in result.err and "Backend Error" in (
        result.err)
