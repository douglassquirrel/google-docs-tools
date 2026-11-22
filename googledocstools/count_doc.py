"""count-doc: the words in each part of a Google Doc, as word-tools' check-manuscript counts them.
Reads only."""
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
from googledocstools.counting import count_parts
from googledocstools.document import paragraphs

COMMAND = "count-doc"
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"


def _level(text):
    """An argparse type: a heading level, 1 to 6."""
    if text not in ("1", "2", "3", "4", "5", "6"):
        raise argparse.ArgumentTypeError("%r is not a heading level from 1 to 6" % text)
    return int(text)


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Print the words in each part of a Google Doc: a part starts at the title or "
        "a heading at the level asked or above and runs to the next, its heading's words "
        "included; then the total. Words are counted as word-tools' check-manuscript counts "
        "them: what lies between spaces, in every paragraph of the body. Pending suggestions are "
        "counted as if accepted. Every call it makes to Google is a read; it changes nothing.",
        epilog="The Google secrets are read from the environment: run the command through "
        "lobster-tools' secrets with the set that holds them (secrets run google -- COMMAND …), "
        "or source a secrets file in the same command."
        " Exit codes: 0 counted; 2 bad "
        "arguments; 3 cannot sign in to Google; 4 Google could not be reached or answered with "
        "an error; 5 there is no such document, or it is not a Google Doc.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--level", metavar="N", type=_level, default=2,
        help="the heading level that starts a part, 1 to 6; headings above it and the title "
        "start one too (default: 2, a book's chapters)")
    parser.add_argument(
        "--exclude-braces", action="store_true",
        help="leave out text in braces, {like this}, and say how many words that was")
    parser.add_argument(
        "--exclude-lorem", action="store_true",
        help="leave out paragraphs of lorem ipsum filler, and say how many words that was")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _report(counted, args, viewer=False):
    """The lines count-doc prints, the numbers lined up."""
    rows = [(part.words, "Before the first heading" if part.heading is None else part.heading)
            for part in counted.parts] + [(counted.total, "Total")]
    width = max(len(f"{number:,}") for number, _ in rows)
    lines = [f"{number:>{width},}  {name}" for number, name in rows]
    if args.exclude_braces:
        lines.append(f"Left out: {counted.braces:,} words in braces.")
    if args.exclude_lorem:
        lines.append(f"Left out: {counted.lorem:,} words of lorem ipsum.")
    lines.append("This account may only view the document, so any pending suggestions are not "
                 "counted." if viewer else "Pending suggestions are counted as if accepted.")
    return "\n".join(lines) + "\n"


def _run(args, env, send, out):
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        the_document(session, args.document, progress)
        progress.step = "reading the document"
        viewer = False
        try:
            described = session.document(args.document, ACCEPTED)
        except google.Answered as error:
            # As seen at Google on 16 November 2026: an account that may only view a document
            # is refused its suggestions, but may read it as it is shown to a viewer.
            if error.status != 403 or "suggestions" not in error.message:
                raise
            viewer = True
            described = session.document(args.document)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    counted = count_parts(paragraphs(described), args.level, args.exclude_braces,
                          args.exclude_lorem)
    out.write(_report(counted, args, viewer))
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
