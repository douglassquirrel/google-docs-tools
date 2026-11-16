"""check-typography: straight quotes and odd dashes in a Google Doc, with the form each should take.
Reads only."""
import argparse
import os
import sys

from googledocstools import google
from googledocstools.cli import (
    DEFAULT_SETTINGS,
    EXISTS,
    GOOGLE,
    OK,
    USAGE,
    Progress,
    Stop,
    document_id,
    said,
    seconds,
    secrets,
    settings_file,
    sign_in,
    the_document,
)
from googledocstools.document import paragraphs
from googledocstools.typography import KINDS, chosen, findings

COMMAND = "check-typography"
FOUND = EXISTS  # 1: something to fix


def _checks(text):
    """An argparse type: the checks, a comma list."""
    try:
        return chosen(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="List each paragraph of a Google Doc that holds a straight quote or "
        "apostrophe (quotes), or a double hyphen or a hyphen with a space each side (dashes), "
        "with the curly quote or en dash each should be. Link text that is a web address and "
        "merge tags such as [[contact.first_name]] are left out. Every call it makes to Google "
        "is a read; it changes nothing (edit-doc makes the changes, given them exactly).",
        epilog="The Google secrets are read from the environment: source env.sh from the secrets "
        "folder (google-docs-tools-secrets) in the same command. Exit codes: 0 nothing to fix; "
        "1 something to fix; 2 bad arguments or settings; 3 cannot sign in to Google; 4 Google "
        "could not be reached or answered with an error; 5 there is no such document, or it is "
        "not a Google Doc.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--checks", metavar="LIST", type=_checks,
        help="which checks, a comma list of %s (default: the setting TYPOGRAPHY_CHECKS, or "
        "both)" % " and ".join(KINDS))
    parser.add_argument(
        "--settings", metavar="FILE",
        help="the settings file to read (default: %s, if there is one)" % DEFAULT_SETTINGS)
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _kinds(args, default_settings):
    """The checks: the flag, else the setting, else both; stop if the setting is not right."""
    if args.checks is not None:
        return args.checks
    setting = settings_file(args, default_settings).get("TYPOGRAPHY_CHECKS")
    if setting is None:
        return KINDS
    try:
        return chosen(setting)
    except ValueError as error:
        raise Stop(USAGE, "The setting TYPOGRAPHY_CHECKS in the settings file is not right: %s."
                   % error)


def _report(found):
    lines = ["== Typography: %d ==" % len(found)]
    for finding in found:
        lines.append("%s: %s" % (finding.place, finding.beginning))
        lines += ["  %s → %s" % fix for fix in finding.fixes]
    if not found:
        lines.append("Typography: nothing to fix.")
    else:
        lines.append("Typography: %d paragraph%s to fix." % (len(found), "" if len(found) == 1
                                                              else "s"))
    return "\n".join(lines) + "\n"


def _run(args, env, send, out, default_settings):
    kinds = _kinds(args, default_settings)
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        the_document(session, args.document, progress)
        progress.step = "reading the document"
        described = session.document(args.document)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    found = findings(paragraphs(described), kinds)
    out.write(_report(found))
    return FOUND if found else OK


def main(argv, env=None, send=None, default_settings=None):
    """Run the command; the exit code."""
    env = os.environ if env is None else env
    send = google.https_send if send is None else send
    default_settings = os.path.expanduser(
        DEFAULT_SETTINGS if default_settings is None else default_settings)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code
    try:
        return _run(args, env, send, sys.stdout, default_settings)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
