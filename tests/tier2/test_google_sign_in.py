"""google-sign-in against the stand-ins: every flag, refusal and failure in PLAN.md."""
import os
import re
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from googledocstools import google
from googledocstools.sign_in import Listener, challenge_for
from tests.conftest import CLIENT_ID, NEW_REFRESH_TOKEN, SIGN_IN_CODE
from tests.tier2.conftest import ACCOUNT, ENV_TEXT, STATE, VERIFIER

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sourced(path, name="GOOGLE_OAUTH_REFRESH_TOKEN"):
    """What a shell gets for the variable after sourcing the file."""
    done = subprocess.run(
        ["/bin/sh", "-c", '. "$1"; printf %s "$' + name + '"', "sh", str(path)],
        capture_output=True, env={"PATH": "/usr/bin:/bin"}, check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.decode("utf-8")


# --- the run that works -------------------------------------------------------------------

def test_stores_the_refresh_token_in_the_env_file_and_says_who_signed_in(sign_in):
    result = sign_in()
    assert result.code == 0
    assert sourced(sign_in.path) == NEW_REFRESH_TOKEN
    assert ACCOUNT in result.out and str(sign_in.path) in result.out
    assert result.err == ""


def test_every_other_line_of_the_env_file_is_kept(sign_in):
    sign_in()
    before = ENV_TEXT.splitlines()
    after = sign_in.path.read_text(encoding="utf-8").splitlines()
    assert after[:4] == before[:4] and len(after) == len(before)


def test_the_env_file_ends_up_private_whatever_it_was(sign_in):
    sign_in.path.chmod(0o644)
    sign_in()
    assert stat.S_IMODE(sign_in.path.stat().st_mode) == 0o600


def test_no_temporary_file_is_left_beside_the_env_file(sign_in):
    sign_in()
    assert sorted(os.listdir(str(sign_in.path.parent))) == ["env.sh"]


def test_the_address_printed_is_googles_and_names_this_runs_listener_and_checks(sign_in, fake):
    result = sign_in()
    url = re.search(r"https://accounts\.google\.com/\S+", result.out).group(0)
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["http://127.0.0.1:51234"]
    assert query["state"] == [STATE]
    assert query["code_challenge"] == [challenge_for(VERIFIER)]
    assert query["login_hint"] == [ACCOUNT]
    assert fake.exchanged["code_verifier"] == VERIFIER
    assert fake.exchanged["redirect_uri"] == "http://127.0.0.1:51234"
    assert fake.exchanged["code"] == SIGN_IN_CODE


def test_the_listener_is_always_closed(sign_in):
    sign_in()
    sign_in.answer = None
    sign_in()
    assert [listener.closed for listener in sign_in.listeners] == [True, True]


def test_the_account_is_compared_without_regard_to_case(sign_in, fake):
    fake.account = "Tools-User@Example.ORG"
    assert sign_in().code == 0


# --- arguments ----------------------------------------------------------------------------

def test_help_lists_every_flag_and_does_nothing(sign_in, fake):
    result = sign_in("--help", defaults=False)
    assert result.code == 0
    for flag in ("--account", "--env-file", "--port", "--timeout", "--dry-run"):
        assert flag in result.out
    assert fake.calls == [] and sign_in.listeners == []


@pytest.mark.parametrize("argv", [
    ("--env-file", "x"), ("--account", "a@example.org"), (),
])
def test_the_account_and_the_env_file_must_both_be_given(sign_in, fake, argv):
    result = sign_in(*argv, defaults=False)
    assert result.code == 2
    assert fake.calls == [] and sign_in.listeners == []


@pytest.mark.parametrize("account", ["not-an-address", "", "two words@example.org", "@"])
def test_an_account_that_is_not_an_address_is_refused(sign_in, fake, account):
    result = sign_in("--account", account, "--env-file", str(sign_in.path), defaults=False)
    assert result.code == 2 and "--account" in result.err
    assert fake.calls == [] and sign_in.listeners == []


def test_an_env_file_that_does_not_exist_is_refused_not_created(sign_in, fake, tmp_path):
    missing = tmp_path / "nowhere" / "env.sh"
    result = sign_in("--account", ACCOUNT, "--env-file", str(missing), defaults=False)
    assert result.code == 2 and str(missing) in result.err
    assert not missing.exists()
    assert fake.calls == [] and sign_in.listeners == []


def test_an_env_file_that_is_a_folder_is_refused(sign_in, fake):
    result = sign_in("--account", ACCOUNT, "--env-file", str(sign_in.path.parent),
                     defaults=False)
    assert result.code == 2
    assert fake.calls == [] and sign_in.listeners == []


@pytest.mark.parametrize("flag,value", [
    ("--port", "-1"), ("--port", "65536"), ("--port", "http"), ("--port", "80.5"),
    ("--timeout", "0"), ("--timeout", "-1"), ("--timeout", "later"), ("--timeout", "inf"),
])
def test_a_port_or_timeout_that_makes_no_sense_is_refused(sign_in, fake, flag, value):
    result = sign_in(flag, value)
    assert result.code == 2 and flag in result.err
    assert fake.calls == [] and sign_in.listeners == []


def test_the_port_and_the_timeout_are_passed_on_and_have_defaults(sign_in):
    sign_in()
    sign_in("--port", "8765", "--timeout", "45")
    first, second = sign_in.listeners
    assert (first.asked_port, first.waited) == (0, 300)
    assert (second.asked_port, second.waited) == (8765, 45)


# --- the environment ----------------------------------------------------------------------

@pytest.mark.parametrize("name", ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"])
@pytest.mark.parametrize("how", ["absent", "empty"])
def test_a_client_value_missing_from_the_environment_is_refused_by_name(
        sign_in, fake, env, name, how):
    environment = dict(env)
    if how == "absent":
        del environment[name]
    else:
        environment[name] = ""
    result = sign_in(environment=environment)
    assert result.code == 3
    assert name in result.err and "env.sh" in result.err
    assert fake.calls == [] and sign_in.listeners == []


def test_the_refresh_token_need_not_be_in_the_environment_yet(sign_in, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_REFRESH_TOKEN"]
    assert sign_in(environment=environment).code == 0


# --- dry run ------------------------------------------------------------------------------

def test_dry_run_says_what_it_would_do_and_listens_contacts_and_writes_nothing(sign_in, fake):
    result = sign_in("--dry-run")
    assert result.code == 0
    assert ACCOUNT in result.out and str(sign_in.path) in result.out
    assert "Nothing was" in result.out
    assert fake.calls == [] and sign_in.listeners == []
    assert sign_in.path.read_text(encoding="utf-8") == ENV_TEXT


def test_the_dry_run_names_both_permissions_asked_for(sign_in):
    result = sign_in("--dry-run")
    assert "with permission for Google Docs and Google Drive" in result.out


def test_the_prompt_to_approve_names_both_permissions_asked_for(sign_in):
    result = sign_in()
    assert result.code == 0
    assert "Approve the request for Google Docs and Google Drive." \
        in result.out


# --- the sign-in goes wrong: nothing is stored --------------------------------------------

def unchanged(sign_in):
    return sign_in.path.read_text(encoding="utf-8") == ENV_TEXT


def test_no_answer_in_time_stores_nothing(sign_in, fake):
    sign_in.answer = None
    result = sign_in("--timeout", "45")
    assert result.code == 5 and "45" in result.err
    assert fake.calls == [] and unchanged(sign_in)


def test_a_sign_in_refused_in_the_browser_stores_nothing(sign_in, fake):
    sign_in.answer = {"error": "access_denied", "state": STATE}
    result = sign_in()
    assert result.code == 5 and "access_denied" in result.err
    assert fake.calls == [] and unchanged(sign_in)


def test_an_answer_without_this_runs_check_value_is_not_trusted(sign_in, fake):
    sign_in.answer = {"code": SIGN_IN_CODE, "state": "someone-elses"}
    result = sign_in()
    assert result.code == 5
    assert fake.calls == [] and unchanged(sign_in)


def test_an_answer_without_a_code_stores_nothing(sign_in, fake):
    sign_in.answer = {"state": STATE}
    assert sign_in().code == 5
    assert fake.calls == [] and unchanged(sign_in)


def test_a_code_google_refuses_stores_nothing(sign_in):
    sign_in.answer = {"code": "4/a-code-google-will-not-take", "state": STATE}
    result = sign_in()
    assert result.code == 3 and "invalid_grant" in result.err
    assert "4/a-code-google-will-not-take" not in result.err
    assert unchanged(sign_in)


def test_a_reply_without_a_refresh_token_stores_nothing(sign_in, fake):
    del fake.exchange_reply["refresh_token"]
    result = sign_in()
    assert result.code == 5 and "refresh token" in result.err
    assert unchanged(sign_in)


def test_signing_in_as_another_account_stores_nothing_and_names_both(sign_in, fake):
    fake.account = "squirrel-himself@example.org"
    result = sign_in()
    assert result.code == 5
    assert "squirrel-himself@example.org" in result.err and ACCOUNT in result.err
    assert unchanged(sign_in)


@pytest.mark.parametrize("token", ["two\nlines", "tab\there", "bell\x07", ""])
def test_a_token_that_could_not_be_one_line_of_the_file_stores_nothing(sign_in, fake, token):
    fake.exchange_reply["refresh_token"] = token
    assert sign_in().code == 5
    assert unchanged(sign_in)


@pytest.mark.parametrize("after", [0, 1])
def test_google_out_of_reach_is_exit_4_and_stores_nothing(sign_in, fake, after):
    fake.unreachable_after = after
    result = sign_in()
    assert result.code == 4 and "could not be reached" in result.err
    assert unchanged(sign_in)


def test_an_error_from_google_about_the_account_is_exit_4(sign_in, fake):
    fake.answers[("GET", "/drive/v3/about")] = (
        403, {"error": {"code": 403, "message": "Drive API has not been used in project."}})
    result = sign_in()
    assert result.code == 4 and "Drive API has not been used in project." in result.err
    assert unchanged(sign_in)


def test_a_listener_that_cannot_start_is_reported(sign_in, fake):
    sign_in.listen_error = OSError(48, "Address already in use")
    result = sign_in("--port", "8765")
    assert result.code == 5 and "8765" in result.err and "Address already in use" in result.err
    assert fake.calls == [] and unchanged(sign_in)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_if_the_file_cannot_be_written_it_says_so_and_the_old_file_is_intact(sign_in):
    folder = sign_in.path.parent
    folder.chmod(0o500)
    try:
        result = sign_in()
    finally:
        folder.chmod(0o700)
    assert result.code == 5 and "could not be written" in result.err
    assert unchanged(sign_in)


def test_an_env_file_that_is_not_text_is_refused_before_anything_else(sign_in, fake):
    sign_in.path.write_bytes(b"export A=\xff\xfe\n")
    result = sign_in()
    assert result.code == 2 and "--env-file" in result.err
    assert fake.calls == [] and sign_in.listeners == []


def test_if_the_last_step_of_writing_fails_no_temporary_file_is_left(sign_in, monkeypatch):
    def refuse(source, target):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "replace", refuse)
    result = sign_in()
    assert result.code == 5 and "could not be written" in result.err
    assert unchanged(sign_in)
    assert sorted(os.listdir(str(sign_in.path.parent))) == ["env.sh"]


def test_the_check_values_are_fresh_and_long_on_every_real_run(fake, env, tmp_path, capsys):
    from googledocstools import sign_in as module
    from tests.tier2.conftest import FakeListener

    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")
    states = []
    for _ in range(2):
        def listen(port):
            listener = FakeListener(port)
            listener.answer = None
            return listener

        code = module.main(["--account", ACCOUNT, "--env-file", str(env_file)], env=env,
                           send=fake, listen=listen)
        url = re.search(r"https://accounts\.google\.com/\S+", capsys.readouterr().out).group(0)
        query = parse_qs(urlsplit(url).query)
        states.append((query["state"][0], query["code_challenge"][0]))
        assert code == 5
    assert states[0][0] != states[1][0] and states[0][1] != states[1][1]
    assert all(len(state) >= 43 and len(challenge) == 43 for state, challenge in states)


def test_a_token_with_hostile_characters_survives_the_shell(sign_in, fake):
    hostile = "1//it's \\ \"x\" $HOME `id` é"
    fake.exchange_reply["refresh_token"] = hostile
    result = sign_in()
    assert result.code == 0
    assert sourced(sign_in.path) == hostile
    assert hostile not in result.out


# --- the real listener, on this machine only ----------------------------------------------

def fetch(port, path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5) as page:
            return page.status, page.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def answer_from(listener, paths):
    pages = []
    thread = threading.Thread(
        target=lambda: pages.extend(fetch(listener.port, path) for path in paths))
    thread.start()
    try:
        answer = listener.wait(5)
    finally:
        thread.join()
        listener.close()
    return answer, pages


def test_the_real_listener_is_on_this_machine_only_and_picks_a_free_port():
    listener = Listener(0)
    try:
        assert listener.address == "127.0.0.1" and listener.port > 0
    finally:
        listener.close()


def test_the_real_listener_returns_googles_answer_and_shows_a_plain_page():
    answer, pages = answer_from(Listener(0), ["/?code=4%2Fabc&state=zq%20917&scope=x"])
    assert answer == {"code": "4/abc", "state": "zq 917", "scope": "x"}
    status, page = pages[0]
    assert status == 200 and "close this tab" in page
    assert "4/abc" not in page and "zq" not in page and "917" not in page


def test_the_real_listener_ignores_other_requests_and_keeps_waiting():
    answer, pages = answer_from(Listener(0), ["/favicon.ico", "/?nothing=useful",
                                              "/?code=c&state=s"])
    assert answer == {"code": "c", "state": "s"}
    assert [status for status, _ in pages] == [404, 404, 200]


def test_the_real_listener_returns_a_refusal_and_the_page_says_not_signed_in():
    answer, pages = answer_from(Listener(0), ["/?error=access_denied&state=s"])
    assert answer == {"error": "access_denied", "state": "s"}
    assert "not signed in" in pages[0][1].lower()


def test_the_real_listener_gives_up_after_the_timeout_and_not_before():
    listener = Listener(0)
    started = time.monotonic()
    try:
        assert listener.wait(0.2) is None
    finally:
        listener.close()
    assert 0.15 < time.monotonic() - started < 3


def test_the_real_listener_reports_a_port_already_taken():
    first = Listener(0)
    try:
        with pytest.raises(OSError):
            Listener(first.port)
    finally:
        first.close()


# --- the command file itself --------------------------------------------------------------

def test_the_command_runs_from_any_folder(tmp_path):
    done = subprocess.run(
        [sys.executable, os.path.join(HERE, "google-sign-in"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0
    assert "--env-file" in done.stdout and done.stderr == ""


def test_with_nothing_given_main_uses_the_real_environment_transport_and_listener(capsys):
    from googledocstools import sign_in as module

    assert module.main(["--help"]) == 0
    assert "--account" in capsys.readouterr().out
    assert google.https_send is not None


def test_googles_words_are_not_given_a_second_full_stop(sign_in, fake):
    fake.answers[("GET", "/drive/v3/about")] = (
        403, {"error": {"code": 403, "message": "Drive API has not been used in project."}})
    assert ".." not in sign_in().err
