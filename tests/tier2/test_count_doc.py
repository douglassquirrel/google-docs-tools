"""count-doc against the stand-in: the words in each part of a document, and every refusal."""
import os
import subprocess
import sys

import pytest

from tests.conftest import DELETED, INSERTED, RULE, Listed, Styled
from tests.tier2.conftest import DOC_ID

ACCEPTED = "Pending suggestions are counted as if accepted.\n"


def book():
    """An invented book: text before the title, a title, chapters with sections and a list."""
    return [
        "Two words.",
        Styled("TITLE", "An Invented Book"),
        Styled("HEADING_2", "Chapter 1: The start"),
        "One two three four.",
        Styled("HEADING_3", "A section"),
        Listed("A listed item"),
        RULE,
        Styled("HEADING_2", "Chapter 2"),
        Styled("HEADING_2", "Chapter 3: Filler"),
        "Words {put an example here} end.",
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    ]


def test_help_names_the_flags_and_contacts_nothing(count, fake):
    result = count("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--level", "--exclude-braces", "--exclude-lorem", "--timeout",
                 "changes nothing", "check-manuscript"):
        assert word in result.out
    assert fake.calls == []


def test_prints_the_words_in_each_part_then_the_total_and_changes_nothing(count, fake):
    count.document(book())
    result = count()
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        " 2  Before the first heading\n"
        " 3  An Invented Book\n"
        "13  Chapter 1: The start\n"
        " 2  Chapter 2\n"
        "17  Chapter 3: Filler\n"
        "37  Total\n" + ACCEPTED)
    assert fake.writes() == []
    assert [c["path"] for c in fake.calls] == [
        "/token", "/drive/v3/files/%s" % DOC_ID, "/v1/documents/%s" % DOC_ID]


def test_the_document_is_read_with_its_suggestions_accepted(count, fake):
    count.document([Styled("HEADING_2", "Chapter"),
                    [("Kept ", {}), ("added words ", {INSERTED: ["s1"]}),
                     ("struck out ", {DELETED: ["s2"]}), ("here.", {})]])
    result = count()
    assert result.out == "5  Chapter\n5  Total\n" + ACCEPTED
    assert fake.calls[-1]["query"] == {"suggestionsViewMode": ["PREVIEW_SUGGESTIONS_ACCEPTED"]}


def test_level_three_makes_a_part_of_each_section_too(count):
    count.document(book())
    result = count("--level", "3")
    assert result.out.splitlines()[2:5] == [
        " 8  Chapter 1: The start", " 5  A section", " 2  Chapter 2"]


def test_braces_and_lorem_are_left_out_when_asked_and_said(count):
    count.document(book())
    result = count("--exclude-braces", "--exclude-lorem")
    assert result.code == 0
    assert result.out == (
        " 2  Before the first heading\n"
        " 3  An Invented Book\n"
        "13  Chapter 1: The start\n"
        " 2  Chapter 2\n"
        " 5  Chapter 3: Filler\n"
        "25  Total\n"
        "Left out: 4 words in braces.\n"
        "Left out: 8 words of lorem ipsum.\n" + ACCEPTED)


def test_thousands_are_written_with_commas_and_the_numbers_line_up(count):
    count.document([Styled("HEADING_2", "Long"), " ".join(["word"] * 1234),
                    Styled("HEADING_2", "Short"), "x"])
    assert count().out == "1,235  Long\n    2  Short\n1,237  Total\n" + ACCEPTED


def test_a_document_with_no_words_has_a_total_of_nothing(count):
    count.document([""])
    assert count().out == "0  Total\n" + ACCEPTED


def test_a_heading_with_quotes_backslashes_dollars_and_non_ascii_is_printed_as_data(count):
    hostile = "it's a \\ \"test\" $HOME </script> é 🐿️"
    count.document([Styled("HEADING_2", hostile)])
    assert count().out.splitlines()[0] == "8  " + hostile


@pytest.mark.parametrize("level", ["0", "7", "two", "1.5"])
def test_a_level_that_is_not_one_to_six_is_refused(count, fake, level):
    result = count("--level", level)
    assert result.code == 2 and "--level" in result.err and fake.calls == []


@pytest.mark.parametrize("argv,code,told", [
    (("not an id",), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
])
def test_a_bad_id_or_an_unknown_document_is_refused(count, argv, code, told):
    result = count(*argv, defaults=False)
    assert result.code == code and told in result.err and result.out == ""


def test_a_document_in_the_bin_is_exit_5(count, fake):
    fake.files[DOC_ID]["trashed"] = True
    result = count()
    assert result.code == 5 and "bin" in result.err


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(count, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_CLIENT_ID"]
    result = count(environment=environment)
    assert result.code == 3 and "GOOGLE_OAUTH_CLIENT_ID" in result.err and fake.calls == []


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document")])
def test_google_out_of_reach_is_exit_4_naming_the_step(count, fake, after, step):
    fake.unreachable_after = after
    result = count()
    assert result.code == 4 and step in result.err and result.out == ""


def test_an_error_from_google_is_exit_4_with_its_words(count, fake):
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = count()
    assert result.code == 4 and "Backend Error" in result.err


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "count-doc"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--exclude-lorem" in done.stdout and done.stderr == ""


def test_an_account_that_may_only_view_counts_the_document_as_it_can_see_it(count, fake):
    count.document([Styled("HEADING_2", "Chapter"), "Three words here."])
    fake.suggestions_hidden = True
    result = count()
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "4  Chapter\n4  Total\n"
        "This account may only view the document, so any pending suggestions are not counted.\n")
    assert [c["query"] for c in fake.calls if c["path"] == "/v1/documents/" + DOC_ID] == [
        {"suggestionsViewMode": ["PREVIEW_SUGGESTIONS_ACCEPTED"]}, {}]


def test_any_other_refusal_of_the_suggestions_is_still_an_error(count, fake):
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        403, {"error": {"code": 403, "message": "The caller does not have permission"}})
    result = count()
    assert result.code == 4 and "does not have permission" in result.err
