"""read-doc: print a Google Doc as text, with its headings, bold, italic and links. Reads only."""
import argparse
import os
import sys

from googledocstools import google
from googledocstools.cli import (
    GOOGLE,
    OK,
    Progress,
    Stop,
    document_id,
    said,
    seconds,
    secrets,
    sign_in,
    the_document,
)
from googledocstools.document import paragraphs
from googledocstools.text import as_text

COMMAND = "read-doc"


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Print a Google Doc as text: its title and headings with #, **bold**, "
        "*italic* and [links](address), a blank line between paragraphs, a --- for a horizontal "
        "rule. Every call it makes to Google is a read; it changes nothing.",
        epilog="The Google secrets are read from the environment: source env.sh from the secrets "
        "folder (google-docs-tools-secrets) in the same command. Exit codes: 0 printed; 2 bad "
        "arguments; 3 cannot sign in to Google; 4 Google could not be reached or answered with "
        "an error; 5 there is no such document, or it is not a Google Doc.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--highlights", action="store_true",
        help="mark highlighted text as {==text==}")
    parser.add_argument(
        "--title", action="store_true", help="print the document's name first, as a line")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _run(args, env, send, out):
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        name, _link = the_document(session, args.document, progress)
        progress.step = "reading the document"
        described = session.document(args.document)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    if args.title:
        out.write("%s\n\n" % name)
    out.write(as_text(paragraphs(described), args.highlights))
    return OK


def main(argv, env=None, send=None):
    """Run the command; the exit code."""
    env = os.environ if env is None else env
    send = google.https_send if send is None else send
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code
    try:
        return _run(args, env, send, sys.stdout)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
