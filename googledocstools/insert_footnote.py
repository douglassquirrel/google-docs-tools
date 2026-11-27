"""insert-footnote: a footnote put into a Google Doc straight after some words, with the caller's
own text, as a suggestion for its editors to accept or reject, or outright with --direct.

Two writes, as PLAN.md Settled 20 allows: Google gives a new footnote's id only in its answer to
the change that makes the mark, so the text goes in with a second change, only at the revision
the first returned. If the second fails, the document is left with an empty mark, and the
command says so plainly; it neither retries nor undoes."""
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
from googledocstools.footnotes import (
    MarkProblem,
    TextError,
    check,
    mark_requests,
    parse_text,
    place,
    text_requests,
    words_before,
)
from googledocstools.markup import render

COMMAND = "insert-footnote"
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"
AROUND = 3  # words shown before the mark


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Put a footnote into a Google Doc straight after some words, with the text "
        "given, as a suggestion its editors accept or reject (or outright with --direct). The "
        "text is one paragraph in read-doc's markup: *italic* (for a title), **bold** and "
        "[links](https://…); a bare address stays text. With --remove, words standing straight "
        "after (a bracketed note asking for the footnote) are taken out in the same change, so "
        "the mark stands where they were. The mark is made first and its text put in with a "
        "second change; each is made only if the document is as it was. read-doc --footnotes "
        "lists the footnotes a document has.",
        epilog="The Google secrets are read from the environment: run the command through "
        "lobster-tools' secrets with the set that holds them (secrets run google -- COMMAND …), "
        "or source a secrets file in the same command."
        " Exit codes: 0 the footnote put in and found in the document afterwards (with "
        "--dry-run: it can be put in); 2 bad arguments; 3 cannot sign in to Google; 4 Google "
        "could not be reached or answered with an error, the document changed while this ran, or "
        "the footnote's text could not be put in after its mark was made (the message says "
        "where the empty mark is); 5 there is no such document, the words are not in it exactly "
        "once (or touch a pending suggestion), the words to remove are not straight after them, "
        "or the footnote is not in the document afterwards.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--after", metavar="WORDS", required=True,
        help="put the mark straight after these words, which must be in the document exactly "
        "once, within one paragraph")
    parser.add_argument(
        "--text", metavar="TEXT", required=True,
        help="the footnote's text: *italic*, **bold** and [links](https://…) as in read-doc")
    parser.add_argument(
        "--remove", metavar="WORDS",
        help="take out these words, which must stand straight after --after's, in the same change")
    parser.add_argument(
        "--direct", action="store_true",
        help="make the footnote outright instead of as a suggestion")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check everything and say where the footnote would go; change nothing")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _checked(args):
    """The footnote's text as Spans, once every argument is checked; or stop."""
    if not args.after.strip():
        raise Stop(USAGE, "--after needs the words the mark goes after.")
    for flag, words in (("--after", args.after), ("--remove", args.remove)):
        if words is not None and ("\n" in words or "\r" in words):
            raise Stop(USAGE, "%s: the words must lie within one paragraph, with no line break."
                       % flag)
    if args.remove is not None and not args.remove:
        raise Stop(USAGE, "--remove needs the words to take out.")
    try:
        return parse_text(args.text)
    except TextError as error:
        raise Stop(USAGE, str(error))


def _empty(where, done, why, may=False):
    """Stop, saying plainly that the document now holds (or may hold) an empty footnote mark."""
    raise Stop(GOOGLE, '%s The document %s an empty footnote mark after "%s", %s: look at it '
               "(read-doc --footnotes), and reject it (or remove it) or put its text in by "
               "hand, before running this again, which would put in a second."
               % (why, "may now hold" if may else "now holds", where, done))


def _first(session, args, described, mark, progress):
    """Make the mark (and take out the words); the new footnote's id and the revision after."""
    progress.step = "making the footnote's mark"
    try:
        answer = session.change_document(args.document, mark_requests(mark),
                                         described.get("revisionId"), suggest=not args.direct)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while making the footnote's mark: %s. "
                   "The mark may or may not be in the document: look at it (read-doc "
                   "--footnotes, or its suggestions) before running this again, which could put "
                   "in a second." % error)
    except google.Answered as error:
        if "revision" in error.message.lower():
            raise Stop(GOOGLE, "The document changed while insert-footnote was reading it, so "
                       "nothing was changed. Run it again.")
        raise Stop(GOOGLE, "Google answered with an error while making the footnote's mark: %s; "
                   "nothing was changed." % said(error))
    replies = answer.get("replies") or [{}]
    note_id = replies[-1].get("createFootnote", {}).get("footnoteId")
    return note_id, answer.get("writeControl", {}).get("requiredRevisionId")


def _run(args, env, send, out):
    spans = _checked(args)
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    done = "made" if args.direct else "suggested"
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        name, _ = the_document(session, args.document, progress)
        progress.step = "reading the document"
        described = session.document(args.document)
        try:
            mark = place(described, args.after, args.remove)
        except MarkProblem as error:
            raise Stop(UNEXPECTED, "%s Nothing was changed." % error)
        where = words_before(mark.before, AROUND)
        lines = ["Document: %s" % name, "After: %s" % where]
        if args.remove is not None:
            lines.append('Removed: "%s"' % args.remove)
        lines.append("Text: %s" % render(spans))
        out.write("\n".join(lines) + "\n")
        if args.dry_run:
            out.write("A footnote would be %s; nothing changed (--dry-run).\n" % done)
            return OK
        note_id, revision = _first(session, args, described, mark, progress)
        if not note_id:
            _empty(where, done, "Google did not say which footnote it made, so its text could not "
                   "be put in.")
        progress.step = "putting in the footnote's text"
        try:
            session.change_document(args.document, text_requests(note_id, spans), revision,
                                    suggest=not args.direct)
        except google.Unreachable as error:
            _empty(where, done, "The footnote's mark was %s, but Google could not be reached "
                   "while putting in its text: %s." % (done, error), may=True)
        except google.Answered as error:
            _empty(where, done, "The footnote's mark was %s, but its text could not be put in: "
                   "Google answered with an error: %s." % (done, said(error)))
        progress.step = "reading the document again, to check the footnote is there"
        afterwards = session.document(args.document, ACCEPTED)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    number, missing = check(afterwards, args.after, args.remove, note_id, spans)
    if missing:
        raise Stop(UNEXPECTED, "The footnote is not in the document as asked: %s. Look at it "
                   "before running this again, which could put in a second." % "; ".join(missing))
    out.write("Footnote %s %s; the mark and its text are in the document.\n" % (number, done))
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
