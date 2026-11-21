"""insert-paragraphs: new paragraphs, written out in a file, put into a Google Doc beside the
paragraph that holds some words, as suggestions for its editors to accept or reject, or outright
with --direct. Every word and every paragraph's kind is the caller's own, written out in the file;
the one change is all or nothing, and only at the revision just read."""
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
from googledocstools.inserting import (
    AnchorProblem,
    ContentError,
    anchor,
    not_there,
    parse_content,
    requests_for,
)
from googledocstools.markup import render

COMMAND = "insert-paragraphs"
ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"
SHOWN = 60  # characters of a paragraph shown in its line
KINDS = {"NORMAL_TEXT": "paragraph"}


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Put new paragraphs into a Google Doc, after (or before) the paragraph that "
        "holds some words, as suggestions its editors accept or reject (or outright with "
        "--direct). The new paragraphs are written in a file in read-doc's markup: # to ###### "
        "for a heading 1 to 6, - for a bulleted list item, plain paragraphs, **bold**, *italic* "
        "and [links](https://…), a blank line between paragraphs. Each takes the document's own "
        "style for its kind, not the look of the paragraph beside it. The change is all or "
        "nothing, and it is made only if the document is as it was when read.",
        epilog="The Google secrets are read from the environment: source env.sh from the secrets "
        "folder (google-docs-tools-secrets) in the same command. Exit codes: 0 every new "
        "paragraph put in and found in the document afterwards (with --dry-run: they can be put "
        "in); 2 bad arguments or content file; 3 cannot sign in to Google; 4 Google could not be "
        "reached or answered with an error, or the document changed while this ran; 5 there is "
        "no such document, the words are not in it exactly once (or are in a table or a pending "
        "suggestion), or a new paragraph is not in the document afterwards.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument("content", metavar="CONTENT", help="the file of new paragraphs")
    place = parser.add_mutually_exclusive_group(required=True)
    place.add_argument(
        "--after", metavar="WORDS",
        help="put them after the paragraph holding these words, which must be in the document "
        "exactly once, within one paragraph")
    place.add_argument(
        "--before", metavar="WORDS", help="put them before the paragraph holding these words")
    parser.add_argument(
        "--direct", action="store_true",
        help="put them in outright instead of as suggestions")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check everything and say where they would go; change nothing")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _words(args):
    """The words saying the place, or stop."""
    words = args.before if args.before is not None else args.after
    flag = "--before" if args.before is not None else "--after"
    if not words.strip():
        raise Stop(USAGE, "%s needs the words of the paragraph to put them beside." % flag)
    if "\n" in words or "\r" in words:
        raise Stop(USAGE, "%s: the words must lie within one paragraph, with no line break."
                   % flag)
    return words


def _content(path, words):
    """The new paragraphs in the file, or stop naming every fault in it."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise Stop(USAGE, "The content file %s could not be read: %s." % (path, error.strerror))
    try:
        new = parse_content(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise Stop(USAGE, "The content file %s is not text in UTF-8." % path)
    except ContentError as error:
        raise Stop(USAGE, "The content file %s cannot be used:\n%s" % (
            path, "\n".join("  " + problem for problem in error.problems)))
    if any(words in "".join(span.text for span in paragraph.spans) for paragraph in new):
        raise Stop(USAGE, 'The new paragraphs hold the words "%s" themselves, so the place could '
                   "not be told from them afterwards. Give other words." % words)
    return new


def _cut(text):
    return text if len(text) <= SHOWN else text[:SHOWN - 1] + "…"


def _line(number, paragraph):
    kind = KINDS.get(paragraph.kind, paragraph.kind.lower().replace("_", " "))
    return "  %d | %s | %s" % (number, "list item" if paragraph.item else kind,
                               _cut(render(paragraph.spans)))


def _counted(number):
    return "%d new paragraph%s" % (number, "" if number == 1 else "s")


def _change(session, args, described, made, progress):
    """Send the one change; stop with what is known if it fails."""
    progress.step = "changing the document"
    try:
        session.change_document(args.document, made, described.get("revisionId"),
                                suggest=not args.direct)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while changing the document: %s. The new "
                   "paragraphs may or may not be in it: look at the document (read-doc, or its "
                   "suggestions) before running this again, which could put them in twice."
                   % error)
    except google.Answered as error:
        if "revision" in error.message.lower():
            raise Stop(GOOGLE, "The document changed while insert-paragraphs was reading it, so "
                       "nothing was changed. Run it again.")
        raise Stop(GOOGLE, "Google answered with an error while changing the document: %s; "
                   "nothing was changed." % said(error))


def _run(args, env, send, out):
    words = _words(args)
    new = _content(args.content, words)
    before = args.before is not None
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
            place = anchor(described, words)
        except AnchorProblem as error:
            raise Stop(UNEXPECTED, "%s Nothing was changed." % error)
        lines = ["Document: %s" % name,
                 "%s: %s" % ("Before" if before else "After", _cut(place.text))]
        if args.dry_run:
            out.write("\n".join(lines + [_line(number, paragraph) for number, paragraph
                                         in enumerate(new, start=1)]) + "\n")
            out.write("%s would be %s; nothing changed (--dry-run).\n" % (_counted(len(new)), done))
            return OK
        _change(session, args, described, requests_for(place, new, before), progress)
        progress.step = "reading the document again, to check the new paragraphs are there"
        afterwards = session.document(args.document, ACCEPTED)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s."
                   % (progress.step, said(error)))
    missing = not_there(afterwards, words, new, before)
    for number, paragraph in enumerate(new, start=1):
        lines.append(_line(number, paragraph) + (
            " | NOT in the document afterwards" if number in missing else ""))
    out.write("\n".join(lines) + "\n")
    if missing:
        raise Stop(UNEXPECTED, "%d of the %s %s not in the document as written: look at it before "
                   "running this again, which could put them in twice." % (
                       len(missing), _counted(len(new)), "is" if len(missing) == 1 else "are"))
    out.write("%s %s; each is in the document.\n" % (_counted(len(new)), done))
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
