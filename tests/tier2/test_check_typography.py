"""check-typography against the stand-in: straight quotes and odd dashes listed, and every refusal."""
import os
import subprocess
import sys

import pytest

from tests.conftest import Styled
from tests.tier2.conftest import DOC_ID


def draft():
    return [
        Styled("TITLE", "An Invented Issue"),
        "All fine here – with “curly” quotes.",
        Styled("HEADING_2", "Briefly…"),
        'We don\'t want "this" -- or that.',
        [("Read ", {}), ("https://example.org/it's", {"link": {"url": "https://example.org/it's"}}),
         (" now, [[contact.first_name]].", {})],
        "A spaced - hyphen.",
    ]


def test_help_names_the_flags_and_contacts_nothing(typography, fake):
    result = typography("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--checks", "--settings", "--timeout", "TYPOGRAPHY_CHECKS",
                 "changes nothing", "quotes", "dashes"):
        assert word in result.out
    assert fake.calls == []


def test_lists_each_paragraph_to_fix_with_the_proposed_forms_exit_1_and_writes_nothing(
        typography, fake):
    typography.document(draft())
    result = typography()
    assert (result.code, result.err) == (1, "")
    assert result.out == (
        "== Typography: 2 ==\n"
        'under "## Briefly…": We don\'t want "this" -- or that.\n'
        "  We don't want → We don’t want\n"
        '  want "this" -- or → want “this” – or\n'
        'under "## Briefly…": A spaced - hyphen.\n'
        "  spaced - hyphen. → spaced – hyphen.\n"
        "Typography: 2 paragraphs to fix.\n")
    assert fake.writes() == []
    assert [c["path"] for c in fake.calls] == [
        "/token", "/drive/v3/files/%s" % DOC_ID, "/v1/documents/%s" % DOC_ID]


def test_a_clean_document_is_exit_0(typography):
    typography.document([Styled("TITLE", "Clean"), "Nothing – “wrong” here."])
    result = typography()
    assert (result.code, result.out) == (0, "== Typography: 0 ==\nTypography: nothing to fix.\n")


def test_one_paragraph_is_said_in_the_singular(typography):
    typography.document(["it's"])
    result = typography()
    assert result.out.endswith("Typography: 1 paragraph to fix.\n")


def test_checks_names_which_kinds_to_look_for(typography):
    typography.document(draft())
    result = typography("--checks", "quotes")
    assert result.code == 1
    assert '  want "this" -- → want “this” --\n' in result.out
    assert "spaced" not in result.out


def test_the_setting_chooses_the_checks_and_the_flag_wins(typography):
    typography.document(draft())
    typography.settings.write_text("TYPOGRAPHY_CHECKS=dashes\n", encoding="utf-8")
    by_setting = typography()
    assert "spaced - hyphen" in by_setting.out and "don’t" not in by_setting.out
    by_flag = typography("--checks", "quotes")
    assert "don’t" in by_flag.out and "spaced" not in by_flag.out


def test_a_settings_file_may_be_named(typography, tmp_path):
    typography.document(draft())
    named = tmp_path / "other.conf"
    named.write_text("TYPOGRAPHY_CHECKS=quotes\n", encoding="utf-8")
    result = typography("--settings", str(named))
    assert "don’t" in result.out and "spaced" not in result.out


@pytest.mark.parametrize("argv", [("--checks", "quotes,spaces"), ("--checks", "")])
def test_an_unknown_or_empty_check_is_exit_2_and_nothing_is_contacted(typography, fake, argv):
    result = typography(*argv)
    assert result.code == 2 and "--checks" in result.err and fake.calls == []


def test_an_unknown_check_in_the_setting_is_exit_2(typography, fake):
    typography.settings.write_text("TYPOGRAPHY_CHECKS=quotes, curly\n", encoding="utf-8")
    result = typography()
    assert result.code == 2 and "TYPOGRAPHY_CHECKS" in result.err and "curly" in result.err
    assert fake.calls == []


def test_a_settings_file_that_cannot_be_read_is_exit_2(typography, fake, tmp_path):
    result = typography("--settings", str(tmp_path / "missing.conf"))
    assert result.code == 2 and "missing.conf" in result.err and fake.calls == []


def test_hostile_text_is_printed_as_data(typography):
    hostile = "it's a \\ $HOME </script> é 🐿️"
    typography.document([hostile])
    result = typography()
    assert result.out.splitlines()[1:3] == [
        "at the start: " + hostile, "  it's a → it’s a"]


@pytest.mark.parametrize("argv,code,told", [
    (("not an id",), 2, "document id"),
    (("no-such-document-at-all",), 5, "no-such-document-at-all"),
])
def test_a_bad_id_or_an_unknown_document_is_refused(typography, argv, code, told):
    result = typography(*argv, defaults=False)
    assert result.code == code and told in result.err and result.out == ""


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(typography, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_CLIENT_SECRET"]
    result = typography(environment=environment)
    assert result.code == 3 and fake.calls == []


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document")])
def test_google_out_of_reach_is_exit_4_naming_the_step(typography, fake, after, step):
    fake.unreachable_after = after
    result = typography()
    assert result.code == 4 and step in result.err and result.out == ""


def test_an_error_from_google_is_exit_4_with_its_words(typography, fake):
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = typography()
    assert result.code == 4 and "Backend Error" in result.err


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "check-typography"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--checks" in done.stdout and done.stderr == ""
