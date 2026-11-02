"""insert-picture: put a picture into a Google Doc where some words stand alone, with an optional
caption under it. It changes that one place in that one document and nothing else.

From online-publishing-tools' insert-weekly-image (1 November 2026), for any document by its id,
and from a file as well as an address. PLAN.md has the steps.
"""
import argparse
import datetime
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
    points,
    said,
    seconds,
    secrets,
    sign_in,
    the_document,
)
from googledocstools.document import alone, find, picture, sharing, text_size
from googledocstools.markup import MarkupError, parse
from googledocstools.putting import (
    add_source_arguments,
    check_folder,
    described_picture,
    link_address,
    put_in,
    source,
    upload_name,
)

COMMAND = "insert-picture"
WIDTH = 220  # points, as insert-weekly-image


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Put a picture into a Google Doc where some words stand alone in their "
        "paragraph, with an optional caption under it. It changes that one place in that one "
        "document and nothing else.",
        epilog="The words must be in the document exactly once and alone in their paragraph, "
        "which becomes the picture. From a file, the picture is uploaded into the folder "
        "(--folder, or the setting UPLOAD_FOLDER_ID), shared with anyone who has the link only "
        "while it goes in, then unshared and kept there; if the sharing cannot be taken back the "
        "run fails, saying so: open the copy in Drive, Share, General access, Restricted. From "
        "an address, Google fetches it and nothing is uploaded. The Google secrets are read from "
        "the environment: source env.sh from the secrets folder (google-docs-tools-secrets) in "
        "the same command. Exit codes: 0 put in (or, with --dry-run, checked); 2 bad arguments, "
        "settings or picture file, or no folder; 3 cannot sign in to Google; 4 Google could not "
        "be reached or answered with an error (a picture it cannot fetch, the document changed "
        "meanwhile), or the sharing could not be taken back; 5 there is no such document or "
        "folder, or the words are not there exactly once and alone in their paragraph.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--at", metavar="WORDS", required=True,
        help="the words the picture takes the place of, alone in their paragraph, like [PICTURE]")
    add_source_arguments(parser)
    parser.add_argument(
        "--caption", metavar="TEXT",
        help="a caption under the picture, in read-doc's markup (**bold**, *italic*, "
        "[words](address), a blank line between paragraphs), a point smaller than the text")
    parser.add_argument(
        "--link", metavar="URL", type=link_address, help="make the picture itself a link")
    parser.add_argument(
        "--width", metavar="POINTS", type=points, default=WIDTH,
        help="the picture's width in points (default: %d); Google keeps its proportions" % WIDTH)
    parser.add_argument(
        "--no-centre", action="store_true",
        help="leave the picture and its caption aligned as the words' paragraph was; without "
        "this they are centred")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check everything and say what would be done; upload, share and change nothing")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _caption(text):
    """The caption's paragraphs, or stop."""
    if text is None:
        return []
    try:
        return parse(text)
    except MarkupError as error:
        raise Stop(USAGE, "--caption: %s. Nothing was changed." % error)


def _place(described, words, name):
    """Where the words are: (start, end), once and alone in their paragraph; or stop."""
    places = find(described, words)
    if len(places) != 1:
        raise Stop(UNEXPECTED, "%r is in the document %r %d times, and must be there exactly once. "
                   "Nothing was changed." % (words, name, len(places)) if places else
                   "%r is not in the document %r. Copy the words exactly. Nothing was changed."
                   % (words, name))
    start, end = places[0]
    if not alone(described, start, end):
        raise Stop(UNEXPECTED, "%r is not alone in its paragraph in the document %r: %s shares "
                   "it, and its paragraph is what becomes the picture. Put the words in a "
                   "paragraph of their own, then run this again. Nothing was changed." % (
                       words, name, " and ".join(sharing(described, start, end))))
    return start, end


def _run(args, env, send, default_settings, out, clock):
    found = source(args, default_settings)
    caption = _caption(args.caption)
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        name, link = the_document(session, args.document, progress)
        if found.folder is not None:
            progress.step = "looking up the folder"
            check_folder(session, found.folder)
        progress.step = "reading the document"
        described = session.document(args.document)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s. Nothing was changed."
                   % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s. Nothing was changed."
                   % (progress.step, said(error)))
    start, end = _place(described, args.at, name)
    size = text_size(described, start) - 1 if caption else None
    copy_name = upload_name(name, clock, found.path) if found.path else None
    lines = "Document: %s\nLink: %s\nIn place of: %s\nPicture: %s\n" % (
        name, link, args.at, described_picture(found))
    details = "Width: %g pt\nCentred: %s\nCaption paragraphs: %d\n" % (
        args.width, "no" if args.no_centre else "yes", len(caption))
    if caption:
        details += "Caption size: %g pt\n" % size
    if args.link:
        details += "Picture link: %s\n" % args.link
    if args.dry_run:
        upload = "Would upload: %s, into the folder %s, shared only while it goes in\n" % (
            copy_name, found.folder) if found.path else ""
        out.write("Dry run: nothing was uploaded, shared or changed.\n" + lines + upload + details)
        return OK
    kept = put_in(
        session, found, args.document, name, link,
        lambda uri: picture(start, end, uri, args.width, caption, centred=not args.no_centre,
                            caption_size=size, link=args.link),
        described["revisionId"], copy_name)
    out.write(lines + kept + details)
    return OK


def main(argv, env=None, send=None, default_settings=None, clock=None):
    """Run the command; the exit code. clock() is the time now, with its time zone."""
    clock = (lambda: datetime.datetime.now(datetime.timezone.utc)) if clock is None else clock
    env = os.environ if env is None else env
    send = google.https_send if send is None else send
    if default_settings is None:
        default_settings = os.path.join(os.path.expanduser("~"), ".google-docs-tools.conf")
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code
    try:
        return _run(args, env, send, default_settings, out=sys.stdout, clock=clock)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
