"""google-sign-in: the one-time browser sign-in that stores the tools' Google refresh token."""
import argparse
import base64
import hashlib
import http.server
import os
import re
import secrets as secrets_module
import shlex
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from googledocstools import google
from googledocstools.cli import (
    GOOGLE,
    OK,
    SIGN_IN,
    UNEXPECTED,
    USAGE,
    Stop,
    said,
    seconds,
    secrets,
)

COMMAND = "google-sign-in"
TOKEN_NAME = "GOOGLE_OAUTH_REFRESH_TOKEN"
CLIENT_SECRETS = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")


def challenge_for(verifier):
    """The PKCE challenge for a verifier: its SHA-256, base64url, no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorization_url(client_id, redirect_uri, state, challenge, account):
    """The Google address to open in a browser to sign in."""
    return google.AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(google.SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "login_hint": account,
    })


_TOKEN_LINE = re.compile(r"^([ \t]*(?:export[ \t]+)?%s=)[^\r\n]*" % re.escape(TOKEN_NAME),
                         re.MULTILINE)


def with_token(text, token):
    """The env file's text with the refresh token stored in it, every other line as it was.

    Each line that sets the token gets the new value, so no stale one is left; if there is
    none, the line is added at the end. The value is quoted for the shell.
    """
    quoted = shlex.quote(token)
    changed, count = _TOKEN_LINE.subn(lambda match: match.group(1) + quoted, text)
    if count:
        return changed
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "export %s=%s\n" % (TOKEN_NAME, quoted)


_SIGNED_IN_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Signed in</title>"
    "<p>Signed in. You can close this tab and go back to Terminal.</p>"
)
_REFUSED_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Not signed in</title>"
    "<p>Not signed in. Go back to Terminal to see why.</p>"
)
_NOTHING_PAGE = "<!doctype html><meta charset=utf-8><title>Nothing here</title><p>Nothing here.</p>"


class _Handler(http.server.BaseHTTPRequestHandler):
    """Takes Google's answer from the browser. The pages it shows are fixed text."""

    def do_GET(self):
        parts = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        if parts.path == "/" and ("code" in query or "error" in query):
            self.server.answer = query
            self._page(200, _REFUSED_PAGE if "error" in query else _SIGNED_IN_PAGE)
        else:
            self._page(404, _NOTHING_PAGE)

    def _page(self, status, page):
        body = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Listener:
    """Listens on this machine only for the browser to bring back Google's answer."""

    def __init__(self, port):
        self._server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
        self._server.answer = None
        self.address, self.port = self._server.server_address[:2]

    def wait(self, timeout):
        """Google's answer as a dictionary, or None if none came within the timeout."""
        deadline = time.monotonic() + timeout
        while self._server.answer is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._server.timeout = remaining
            self._server.handle_request()
        return self._server.answer

    def close(self):
        self._server.server_close()


def _port(text):
    try:
        port = int(text)
    except ValueError:
        port = -1
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("%r is not a port number from 0 to 65535" % text)
    return port


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Sign in to Google once, in a browser, as the account the tools act as, "
        "and store the refresh token in the secrets file without showing it. Run by Squirrel "
        "in Terminal on the Mac; run again only when Google stops accepting the token.",
        epilog="The client id and secret are read from the environment: source env.sh from "
        "the secrets folder in the same command. Exit codes: 0 signed in and stored (or, "
        "with --dry-run, checked); 2 bad arguments; 3 a client value is missing or Google "
        "refused the sign-in; 4 Google could not be reached or answered with an error; "
        "5 no answer, the wrong account, or anything else not as it must be. Unless the "
        "exit code is 0, nothing was stored.",
    )
    parser.add_argument(
        "--account", metavar="EMAIL", required=True,
        help="the Google address that must be the one signed in; if another account signs "
        "in, nothing is stored")
    parser.add_argument(
        "--env-file", metavar="FILE", required=True,
        help="the secrets file to store the token in; it must already exist")
    parser.add_argument(
        "--port", metavar="N", type=_port, default=0,
        help="the port to listen on, on 127.0.0.1 only (default: any free port)")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=300,
        help="how long to wait for the sign-in to be finished in the browser (default: 300)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check the arguments, the environment and the file, and say what would happen")
    return parser


def _env_file(path):
    """The real path of the env file, having checked it is a file of text that is there."""
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise Stop(USAGE, "--env-file %s is not a file that exists. This command stores the "
                   "token in a secrets file that is already there; it does not make one."
                   % path)
    try:
        with open(real, encoding="utf-8", newline="") as handle:
            handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise Stop(USAGE, "--env-file %s could not be read: %s" % (path, error))
    return real


def _store(path, token):
    """Put the token in the env file through a temporary file beside it, mode 600."""
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    handle_number, temporary = tempfile.mkstemp(prefix=".env-", dir=os.path.dirname(path))
    try:
        with os.fdopen(handle_number, "w", encoding="utf-8", newline="") as handle:
            handle.write(with_token(text, token))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def _run(args, env, send, listen, random_text, out):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", args.account):
        raise Stop(USAGE, "--account %r is not an email address." % args.account)
    path = _env_file(args.env_file)
    client_id, client_secret = secrets(env, CLIENT_SECRETS)
    if args.dry_run:
        out.write(
            "Dry run. Would listen on 127.0.0.1, ask Google to sign in as %s with permission "
            "for Google Docs and Google Drive, and store the refresh "
            "token in %s as %s.\n"
            "Nothing was contacted, and nothing was written.\n"
            % (args.account, path, TOKEN_NAME))
        return OK

    try:
        listener = listen(args.port)
    except OSError as error:
        raise Stop(UNEXPECTED, "Could not listen on 127.0.0.1 port %s: %s. Give another "
                   "--port, or leave it out to use any free one."
                   % (args.port or "(any)", error.strerror or error))
    try:
        state, verifier = random_text(), random_text()
        redirect_uri = "http://127.0.0.1:%d" % listener.port
        out.write(
            "Open this address in a browser where you can sign in to Google as %s:\n\n"
            "  %s\n\n"
            "Approve the request for Google Docs and Google Drive. "
            "Waiting for the answer on "
            "127.0.0.1 port %d, for up to %g seconds.\n"
            % (args.account,
               authorization_url(client_id, redirect_uri, state, challenge_for(verifier),
                                 args.account),
               listener.port, args.timeout))
        out.flush()
        answer = listener.wait(args.timeout)
    finally:
        listener.close()

    if answer is None:
        raise Stop(UNEXPECTED, "No answer came from the browser within %g seconds. Nothing was "
                   "stored. Run this again and finish the sign-in in the browser."
                   % args.timeout)
    if "error" in answer:
        raise Stop(UNEXPECTED, "Google did not sign you in: %s. Nothing was stored."
                   % answer["error"])
    if answer.get("state") != state or not answer.get("code"):
        raise Stop(UNEXPECTED, "The answer that came back was not the answer to this run's "
                   "request, so it was not used. Nothing was stored. Run this again and use "
                   "the address it prints.")

    session = google.Google(send, 30)
    step = "trading the sign-in for tokens"
    try:
        tokens = session.exchange(client_id, client_secret, answer["code"], verifier,
                                  redirect_uri)
        step = "asking which account signed in"
        signed_in = session.account()
    except google.SignInRefused as error:
        raise Stop(SIGN_IN, "Google refused the sign-in: %s. Nothing was stored. Check the "
                   "client id and secret in the secrets file, then run this again." % error)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s. Nothing was stored."
                   % (step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s. Nothing was "
                   "stored." % (step, said(error)))

    token = tokens.get("refresh_token")
    if not isinstance(token, str) or not token or any(
            ord(character) < 32 or ord(character) == 127 for character in token):
        raise Stop(UNEXPECTED, "Google's reply had no usable refresh token in it. Nothing was "
                   "stored. Run this again.")
    if signed_in.casefold() != args.account.casefold():
        raise Stop(UNEXPECTED, "The account that signed in was %s, not %s. Nothing was "
                   "stored. Run this again and choose %s in the browser, or use a browser "
                   "window where only that account is signed in."
                   % (signed_in or "(unknown)", args.account, args.account))
    try:
        _store(path, token)
    except OSError as error:
        raise Stop(UNEXPECTED, "The token could not be written to %s: %s. Nothing was stored "
                   "and the file is as it was. Run this again once the file can be written."
                   % (path, error.strerror or error))
    out.write("Signed in as %s.\nThe refresh token is stored in %s as %s. It was not shown.\n"
              % (signed_in, path, TOKEN_NAME))
    return OK


def main(argv, env=None, send=None, listen=None, random_text=None):
    env = os.environ if env is None else env
    send = google.https_send if send is None else send
    listen = Listener if listen is None else listen
    if random_text is None:
        def random_text():
            return secrets_module.token_urlsafe(48)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code
    try:
        return _run(args, env, send, listen, random_text, sys.stdout)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
