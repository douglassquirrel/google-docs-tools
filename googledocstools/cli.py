"""What every command shares: the exit codes, stopping with a message, reading secrets, finding
a document by its id. From online-publishing-tools' cli.py (1 November 2026), without the weekly email."""
import argparse
import math
import re

from googledocstools import google
from googledocstools.settings import SettingsError, read_settings

OK, EXISTS, USAGE, SIGN_IN, GOOGLE, UNEXPECTED = 0, 1, 2, 3, 4, 5

SECRETS_FOLDER = "google-docs-tools-secrets"
SOURCE_LINE = (
    'set -a; . "<the secrets folder>/env.sh"; set +a   (the folder is '
    "%s, beside this checkout)" % SECRETS_FOLDER
)
SECRETS = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN")
DEFAULT_SETTINGS = "~/.google-docs-tools.conf"
DOC_ID = re.compile(r"[A-Za-z0-9_-]{10,}")


class Stop(Exception):
    """End the run with this exit code and this message on stderr."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _positive(what):
    """An argparse type: a number of something, above 0."""

    def number(text):
        try:
            value = float(text)
        except ValueError:
            value = math.nan
        if not (value > 0 and math.isfinite(value)):
            raise argparse.ArgumentTypeError("%r is not a number of %s above 0" % (text, what))
        return value

    return number


seconds = _positive("seconds")
points = _positive("points")


def document_id(text):
    """An argparse type: a Google document's id, as it stands in the document's address between
    /d/ and /edit; the whole address is taken too."""
    match = re.search(r"/d/([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1)
    if not DOC_ID.fullmatch(text):
        raise argparse.ArgumentTypeError(
            "%r is not a document id (letters, digits, - and _, as between /d/ and /edit in the "
            "document's address) or a document's address" % text)
    return text


def secrets(env, names=SECRETS):
    """The named secrets from the environment, or stop, naming the first one missing."""
    for name in names:
        if name not in env:
            raise Stop(SIGN_IN, "%s is not set, so there is nothing to sign in to Google with. "
                       "Run this in the same command, first: %s" % (name, SOURCE_LINE))
        if not env[name]:
            raise Stop(SIGN_IN, "%s is empty: it has not been filled in yet in env.sh in the "
                       "secrets folder (%s, beside this checkout). The README's one-time set-up "
                       "says where each value comes from." % (name, SECRETS_FOLDER))
    return [env[name] for name in names]


def settings_file(args, default_settings):
    """The settings from --settings or the default file, or stop if a named file is unreadable."""
    try:
        return read_settings(args.settings, default_settings)
    except SettingsError as error:
        raise Stop(USAGE, str(error))


class Progress:
    """Which step a run is at, for the message if Google cannot be reached during it."""

    step = "signing in"


def sign_in(session, client_id, client_secret, refresh_token):
    """Trade the refresh token for an access token, or stop if Google refuses it."""
    try:
        session.refresh(client_id, client_secret, refresh_token)
    except google.SignInRefused as error:
        raise Stop(SIGN_IN, "Google refused the sign-in: %s. The stored token is no longer "
                   "accepted, or the client id or secret is wrong. Squirrel signs in again "
                   "with google-sign-in, then run this again." % error)


def the_document(session, doc_id, progress):
    """The Google Doc with this id: (its name, its link), or stop if there is no such document
    this account can see, it is in the bin, or it is not a Google Doc."""
    progress.step = "looking up the document"
    found = session.describe(doc_id)
    if found is None:
        raise Stop(UNEXPECTED, "Google has no document with the id %r that this account can see. "
                   "Check the id, and that the document is shared with the account the tools "
                   "sign in as." % doc_id)
    if found.get("trashed"):
        raise Stop(UNEXPECTED, "The document %r (id %r) is in the bin. Restore it first."
                   % (found.get("name"), doc_id))
    if found.get("mimeType") != google.DOC_TYPE:
        raise Stop(UNEXPECTED, "%r (id %r) is not a Google Doc (it is %s), so these tools cannot "
                   "read it." % (found.get("name"), doc_id, found.get("mimeType")))
    link = found.get("webViewLink") or "https://docs.google.com/document/d/%s/edit" % doc_id
    return found.get("name", ""), link


def said(error):
    """Google's status and its own words for an error, without a full stop to double ours."""
    return "%d, %s" % (error.status, error.message.rstrip("."))
