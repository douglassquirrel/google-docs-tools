"""edit-doc: a list of find → replace edits made in a Google Doc, as suggestions for its editors to
accept or reject, or outright with --direct. Every edit is the caller's own, written out exactly
in the edits file; the one change is all or nothing, and only at the revision just read."""
import argparse
import os
import sys

from googledocstools import google
from googledocstools.cli import (
    GOOGLE,
    OK,
    UNEXPECTED,
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
from googledocstools.edit_list import EditsError, parse_edits
from googledocstools.editing import EditProblems, check_after, locate, report, requests

COMMAND = "edit-doc"
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Make a list of edits in a Google Doc, each one a suggestion its editors "
        "accept or reject (or made outright with --direct). The edits file is a JSON list of "
        '{"find": …, "replace": …}, with "occurrence" (which match, from 1), "id" and "why" if '
        "wanted: the shape of word-tools' propose-edits list. Each find is exact text within one "
        "paragraph; only the words that change are changed, and new words take the look of the "
        "old. The whole list is checked before anything is changed, the change is all or "
        "nothing, and it is made only if the document is as it was when read.",
        epilog="The Google secrets are read from the environment: source env.sh from the secrets "
        "folder (google-docs-tools-secrets) in the same command. Exit codes: 0 every edit made "
        "and found in the document afterwards (with --dry-run: every edit can be made); 2 bad "
        "arguments or edits file; 3 cannot sign in to Google; 4 Google could not be reached or "
        "answered with an error, or the document changed while this ran; 5 there is no such "
        "document, an edit cannot be made, or an edit is not in the document afterwards.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument("edits", metavar="EDITS", help="the edits file, a JSON list")
    parser.add_argument(
        "--direct", action="store_true",
        help="make the edits outright instead of as suggestions")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check every edit and say where it would go; change nothing")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _edits(path):
    """The edits in the file, or stop naming every fault in it."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise Stop(USAGE, "The edits file %s could not be read: %s." % (path, error.strerror))
    try:
        return parse_edits(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise Stop(USAGE, "The edits file %s is not text in UTF-8." % path)
    except EditsError as error:
        raise Stop(USAGE, "The edits file %s cannot be used:\n%s" % (
            path, "\n".join("  " + problem for problem in error.problems)))


def _counted(number, noun="edit"):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


def _change(session, args, described, located, progress):
    """Send the one change; stop with what is known if it fails."""
    progress.step = "changing the document"
    try:
        session.change_document(args.document, requests(located), described.get("revisionId"),
                                suggest=not args.direct)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while changing the document: %s. The "
                   "edits may or may not have been made: look at the document (read-doc, or its "
                   "suggestions) before running this again, which would make them twice." % error)
    except google.Answered as error:
        if "revision" in error.message.lower():
            raise Stop(GOOGLE, "The document changed while edit-doc was reading it, so nothing "
                       "was changed. Run it again.")
        raise Stop(GOOGLE, "Google answered with an error while changing the document: %s; "
                   "nothing was changed." % said(error))


def _run(args, env, send, out):
    edits = _edits(args.edits)
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    done = "made" if args.direct else "suggested"
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        the_document(session, args.document, progress)
        progress.step = "reading the document"
        described = session.document(args.document)
        try:
            located = locate(described, edits)
        except EditProblems as error:
            raise Stop(UNEXPECTED, "%d of the %d edits cannot be made, so nothing was changed:\n%s"
                       % (len(error.problems), len(edits),
                          "\n".join("  " + problem for problem in error.problems)))
        if args.dry_run:
            for edit in located:
                out.write("%s would be %s\n" % (report(edit), done))
            out.write("%s checked; nothing changed (--dry-run).\n" % _counted(len(located)))
            return OK
        _change(session, args, described, located, progress)
        progress.step = "reading the document again, to check the edits are there"
        afterwards = session.document(args.document, ACCEPTED)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    missing = check_after(afterwards, located)
    for edit in located:
        out.write("%s %s%s\n" % (report(edit), done,
                                 ", but NOT in the document afterwards" if edit in missing else ""))
    if missing:
        raise Stop(UNEXPECTED, "%d of the %d edits %s not in the document as expected: look at it "
                   "before running this again." % (len(missing), len(located),
                                                    "is" if len(missing) == 1 else "are"))
    out.write("%s %s; each is in the document.\n" % (_counted(len(located)), done))
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
