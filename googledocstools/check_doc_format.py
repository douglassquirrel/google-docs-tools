"""check-doc-format: a Google Doc checked against a house format, and, with --fix, set to it. The
format is the caller's own, written out in the format file; a fix changes formatting only."""
import argparse
import os
import sys

from googledocstools import google
from googledocstools.cli import (
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
    sign_in,
    the_document,
)
from googledocstools.doc_format import FormatError, check, parse_format, report

COMMAND = "check-doc-format"
DIFFERS = EXISTS  # 1: something does not match


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Check a Google Doc against a house format: the page, body text, list items, "
        "the title and each heading level, as the format file says. Reports each paragraph that "
        "does not match, grouped by what is wrong, headings at a level the format does not "
        "name or not matching their pattern, and normal text that looks like a heading. The "
        "check only reads. With --fix, it sets the fonts, sizes, spacing, indents, alignment, "
        "page breaks, colours and page that do not match, in one change, then checks again; it "
        "never changes a character of text, never a heading's level, and never bold or italic "
        "in body text or list items.",
        epilog="The Google secrets are read from the environment: source env.sh from the secrets "
        "folder (google-docs-tools-secrets) in the same command. Exit codes: 0 everything "
        "matches (after the fix, with --fix); 1 something does not match; 2 bad arguments or "
        "format file; 3 cannot sign in to Google; 4 Google could not be reached or answered "
        "with an error, or the document changed while this ran; 5 there is no such document, "
        "or it is not a Google Doc.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--format", metavar="FILE", required=True,
        help="the house format, a JSON file (see check-doc-format.example.json)")
    parser.add_argument(
        "--fix", action="store_true", help="set what does not match, then check again")
    parser.add_argument(
        "--dry-run", action="store_true", help="with --fix: say what would be set; change nothing")
    parser.add_argument(
        "-v", dest="verbose", action="store_true",
        help="list every paragraph that does not match, not three of each kind")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _format(path):
    """The house format in the file, or stop naming every fault in it."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise Stop(USAGE, "The format file %s could not be read: %s." % (path, error.strerror))
    try:
        return parse_format(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise Stop(USAGE, "The format file %s is not text in UTF-8." % path)
    except FormatError as error:
        raise Stop(USAGE, "The format file %s cannot be used:\n%s" % (
            path, "\n".join("  " + problem for problem in error.problems)))


def _set_lines(fixes):
    return ["  %s: %s" % ("the page" if fix.place is None else "%s: %s" % (
        fix.place, fix.beginning), ", ".join(fix.said)) for fix in fixes]


def _change(session, args, described, fixes, progress):
    """Send the one change; stop with what is known if it fails."""
    progress.step = "changing the document"
    try:
        session.change_document(args.document, [request for fix in fixes
                                                for request in fix.requests],
                                described.get("revisionId"))
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while changing the document: %s. The "
                   "format may or may not have been set: run this again without --fix to see."
                   % error)
    except google.Answered as error:
        if "revision" in error.message.lower():
            raise Stop(GOOGLE, "The document changed while check-doc-format was reading it, so "
                       "nothing was changed. Run it again.")
        raise Stop(GOOGLE, "Google answered with an error while changing the document: %s; "
                   "nothing was changed." % said(error))


def _run(args, env, send, out):
    wanted = _format(args.format)
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        the_document(session, args.document, progress)
        progress.step = "reading the document"
        described = session.document(args.document)
        checked = check(described, wanted)
        out.write(report(checked, args.verbose))
        if not args.fix or not checked.problems:
            return DIFFERS if checked.problems else OK
        if not checked.fixes:
            out.write("Nothing to set: what does not match is for a person to change.\n")
            return DIFFERS
        out.write("\n".join(["Would set:" if args.dry_run else "Set:"]
                            + _set_lines(checked.fixes)) + "\n")
        if args.dry_run:
            out.write("Nothing changed (--dry-run).\n")
            return DIFFERS
        _change(session, args, described, checked.fixes, progress)
        progress.step = "reading the document again, to check it"
        again = check(session.document(args.document), wanted)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    out.write("After the fix:\n" + report(again, args.verbose))
    return DIFFERS if again.problems else OK


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
