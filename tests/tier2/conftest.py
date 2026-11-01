"""Running the commands' main() against the stand-in. From online-publishing-tools' tier 2
conftest (1 November 2026), for a document given by its id."""
from datetime import datetime, timezone

import pytest

from tests.conftest import (
    ACCESS_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET,
    NEW_REFRESH_TOKEN,
    REFRESH_TOKEN,
    SIGN_IN_CODE,
)

SECRETS = (CLIENT_SECRET, REFRESH_TOKEN, ACCESS_TOKEN, NEW_REFRESH_TOKEN, SIGN_IN_CODE)


class Result:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err


@pytest.fixture
def env():
    return {
        "GOOGLE_OAUTH_CLIENT_ID": CLIENT_ID,
        "GOOGLE_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
        "GOOGLE_OAUTH_REFRESH_TOKEN": REFRESH_TOKEN,
    }


ENV_TEXT = (
    "# Secrets for tests. All invented.\n"
    "export GOOGLE_OAUTH_CLIENT_ID=''\n"
    "export GOOGLE_OAUTH_CLIENT_SECRET=''\n"
    "# From the one-time sign-in.\n"
    "export GOOGLE_OAUTH_REFRESH_TOKEN=''\n"
)
STATE = "state-for-tests"
VERIFIER = "verifier-for-tests-0123456789-0123456789-0123456789"
ACCOUNT = "tools-user@example.org"


class FakeListener:
    """Stands in for the listener on 127.0.0.1: gives the answer a test chose, at once."""

    def __init__(self, port):
        self.asked_port = port
        self.port = 51234
        self.answer = {"code": SIGN_IN_CODE, "state": STATE}
        self.waited = None
        self.closed = False

    def wait(self, timeout):
        self.waited = timeout
        return self.answer

    def close(self):
        self.closed = True


@pytest.fixture
def sign_in(fake, env, tmp_path, capsys):
    """Run google-sign-in. Every run is checked for secrets in what it printed."""
    from googledocstools import sign_in as module

    env_file = tmp_path / "secrets" / "env.sh"
    env_file.parent.mkdir()
    env_file.write_text(ENV_TEXT, encoding="utf-8")
    env_file.chmod(0o600)
    fake.account = ACCOUNT

    class Runner:
        path = env_file
        answer = "unset"
        listen_error = None

        def listen(self, port):
            if self.listen_error is not None:
                raise self.listen_error
            listener = FakeListener(port)
            if self.answer != "unset":
                listener.answer = self.answer
            self.listeners.append(listener)
            return listener

        def __call__(self, *argv, defaults=True, environment=None):
            args = list(argv)
            if defaults:
                args = ["--account", ACCOUNT, "--env-file", str(env_file)] + args
            texts = iter([STATE, VERIFIER])
            code = module.main(
                args, env=env if environment is None else environment, send=fake,
                listen=self.listen, random_text=lambda: next(texts),
            )
            captured = capsys.readouterr()
            for secret in SECRETS:
                assert secret not in captured.out and secret not in captured.err
            assert "Traceback" not in captured.err
            return Result(code, captured.out, captured.err)

    runner = Runner()
    runner.listeners = []  # per run of the fixture, not shared by the class
    return runner


BOLD = {"bold": True}
FIXED_WITH_LINK = [
    ("Please forward this to a friend who might like it, and ", {}),
    ("tell us", {"link": {"url": "https://example.org/tell"}}), (" what you think.", {}),
]
DOC_ID = "a-document-id-for-tests"
DOC_NAME = "A draft for tests"


def doc_paragraphs():
    """An invented document with a title, headings, styled text, a rule and a link."""
    from tests.conftest import RULE, Styled

    return [
        Styled("TITLE", "A real subject"),
        "Provocative tips and events from the test squad",
        "Hi there, here is this week’s news.",
        Styled("HEADING_2", "Briefly…"),
        [("The main text, with a ", {}), ("bold", BOLD), (" word.", {})],
        RULE,
        Styled("HEADING_2", "Services"),
        list(FIXED_WITH_LINK),
        "Stay warm! -squirrel",
    ]


ALLOWED = "laura@example.org, Squirrel@Example.net"


@pytest.fixture
def comment(fake, env, tmp_path, capsys):
    """Run comment-doc against a document, Laura and Squirrel (invented) allowed."""
    from googledocstools import comment_doc

    fake.add_described(DOC_ID, DOC_NAME, ["root"], doc_paragraphs())
    home = tmp_path / "home"
    home.mkdir()
    settings = home / ".google-docs-tools.conf"
    settings.write_text("COMMENT_RECIPIENTS=%s\n" % ALLOWED, encoding="utf-8")

    def run(*argv, defaults=True, environment=None):
        args = list(argv)
        if defaults:
            args = [DOC_ID] + args
        code = comment_doc.main(
            args, env=env if environment is None else environment, send=fake,
            default_settings=str(settings))
        captured = capsys.readouterr()
        for secret in SECRETS:
            assert secret not in captured.out and secret not in captured.err
        assert "Traceback" not in captured.err
        return Result(code, captured.out, captured.err)

    def added():
        return fake.files[DOC_ID].get("comments", [])

    def document(paragraphs):
        fake.files[DOC_ID]["described"] = paragraphs

    run.added = added
    run.settings = settings
    run.document = document
    return run


@pytest.fixture
def read(fake, env, capsys):
    """Run read-doc against a document."""
    from googledocstools import read_doc

    fake.add_described(DOC_ID, DOC_NAME, ["root"], doc_paragraphs())

    def run(*argv, defaults=True, environment=None):
        args = list(argv)
        if defaults:
            args = [DOC_ID] + args
        code = read_doc.main(args, env=env if environment is None else environment, send=fake)
        captured = capsys.readouterr()
        for secret in SECRETS:
            assert secret not in captured.out and secret not in captured.err
        assert "Traceback" not in captured.err
        return Result(code, captured.out, captured.err)

    def document(paragraphs):
        fake.files[DOC_ID]["described"] = paragraphs

    run.document = document
    return run


@pytest.fixture
def watch(fake, env, tmp_path, capsys):
    """Run watch-doc against a document, with a snapshot of its own and the clock fixed."""
    from googledocstools import watch_doc

    fake.add_described(DOC_ID, DOC_NAME, ["root"], ["# unused"])
    file = tmp_path / "a look.snapshot"
    home = tmp_path / "home"
    home.mkdir()
    settings = home / ".google-docs-tools.conf"

    def run(*argv, defaults=True, environment=None):
        args = list(argv)
        if defaults:
            args = [DOC_ID, "--snapshot", str(file)] + args
        code = watch_doc.main(
            args, env=env if environment is None else environment, send=fake,
            default_settings=str(settings),
            clock=lambda: datetime(2026, 11, 1, 19, 40, tzinfo=timezone.utc))
        captured = capsys.readouterr()
        for secret in SECRETS:
            assert secret not in captured.out and secret not in captured.err
        assert "Traceback" not in captured.err
        return Result(code, captured.out, captured.err)

    def document(paragraphs):
        fake.files[DOC_ID]["described"] = paragraphs

    def comments(found):
        fake.files[DOC_ID]["comments"] = found

    run.document = document
    run.comments = comments
    run.file = file
    run.settings = settings
    return run
