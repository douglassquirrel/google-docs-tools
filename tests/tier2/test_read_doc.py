"""read-doc against the stand-in: the document as text, and every refusal."""
import os
import subprocess
import sys

import pytest

from tests.conftest import RULE, Listed, Styled
from tests.tier2.conftest import DOC_ID, DOC_NAME


def test_help_names_the_document_and_the_flags_and_contacts_nothing(read, fake):
    result = read("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--highlights", "--title", "--timeout", "changes nothing", "list items"):
        assert word in result.out
    assert fake.calls == []


def test_prints_the_document_as_text_with_headings_marks_links_and_rules_and_changes_nothing(
        read, fake):
    result = read()
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "# A real subject\n\n"
        "Provocative tips and events from the test squad\n\n"
        "Hi there, here is this week’s news.\n\n"
        "## Briefly…\n\n"
        "The main text, with a **bold** word.\n\n"
        "---\n\n"
        "## Services\n\n"
        "Please forward this to a friend who might like it, and [tell us](https://example.org/tell) "
        "what you think.\n\n"
        "Stay warm! -squirrel\n")
    assert fake.writes() == []
    assert [c["path"] for c in fake.calls] == [
        "/token", "/drive/v3/files/%s" % DOC_ID, "/v1/documents/%s" % DOC_ID]


def test_title_puts_the_documents_name_first(read):
    result = read("--title")
    assert result.code == 0 and result.out.startswith(DOC_NAME + "\n\n# A real subject\n")


def test_highlights_are_marked_only_when_asked(read):
    read.document([Styled("TITLE", "T"),
                   [("plain ", {}), ("marked", {"backgroundColor": {"color": {"rgbColor": {"red": 1}}}})],
                   RULE])
    plain = read()
    assert plain.out == "# T\n\nplain marked\n\n---\n"
    marked = read("--highlights")
    assert marked.out == "# T\n\nplain {==marked==}\n\n---\n"


def test_text_with_quotes_backslashes_dollars_script_and_non_ascii_is_printed_as_data(read):
    hostile = "it's a \\ \"test\" $HOME </script> é 🐿️"
    read.document([hostile])
    result = read()
    assert result.out == hostile + "\n"


def test_the_document_may_be_given_by_its_address(read):
    result = read("https://docs.google.com/document/d/%s/edit#heading=h.1" % DOC_ID, defaults=False)
    assert result.code == 0 and result.out.startswith("# A real subject\n")


@pytest.mark.parametrize("argv,code,told", [
    (("not an id",), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
])
def test_a_bad_id_or_an_unknown_document_is_refused(read, fake, argv, code, told):
    result = read(*argv, defaults=False)
    assert result.code == code and told in result.err and result.out == ""


def test_a_document_in_the_bin_or_not_a_google_doc_is_exit_5(read, fake):
    fake.files[DOC_ID]["trashed"] = True
    assert read().code == 5
    fake.files[DOC_ID]["trashed"] = False
    fake.files[DOC_ID]["mimeType"] = "application/pdf"
    result = read()
    assert result.code == 5 and "not a Google Doc" in result.err


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(read, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_REFRESH_TOKEN"]
    result = read(environment=environment)
    assert result.code == 3 and "GOOGLE_OAUTH_REFRESH_TOKEN" in result.err
    assert "google-docs-tools-secrets" in result.err and fake.calls == []


def test_a_refused_sign_in_is_exit_3(read, fake, env):
    result = read(environment=dict(env, GOOGLE_OAUTH_REFRESH_TOKEN="old"))
    assert result.code == 3 and "google-sign-in" in result.err


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document")])
def test_google_out_of_reach_is_exit_4_naming_the_step(read, fake, after, step):
    fake.unreachable_after = after
    result = read()
    assert result.code == 4 and step in result.err and result.out == ""


def test_an_error_from_google_is_exit_4_with_its_words(read, fake):
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = read()
    assert result.code == 4 and "500" in result.err and "Backend Error" in result.err


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "read-doc"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--highlights" in done.stdout and done.stderr == ""


def test_lists_are_marked_nested_and_numbered_and_a_paragraph_after_is_not(read, fake):
    read.document([Styled("HEADING_1", "Contents"),
                   Listed("Part one"), Listed("Chapter one", level=1),
                   Listed("Chapter two", level=1), Listed("Part two"),
                   Listed("First", "steps", numbered=True),
                   Listed([("Second", {"bold": True})], "steps", numbered=True),
                   "A paragraph after."])
    result = read()
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "# Contents\n\n"
        "- Part one\n\n  - Chapter one\n\n  - Chapter two\n\n- Part two\n\n"
        "1. First\n\n2. **Second**\n\n"
        "A paragraph after.\n")
    assert fake.writes() == []
