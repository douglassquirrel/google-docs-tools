"""replace-picture: list a Google Doc's pictures, or put a new picture in place of one, keeping its
link, its width and whatever is around it. It changes that one picture and nothing else.

Taken out and put in, in one change, since Google's own replaceImage crops the new picture to the
old one's shape (online-publishing-tools, 2 November 2026). PLAN.md has the steps.
"""
import argparse
import datetime
import os
import re
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
from googledocstools.document import picture_places, picture_widths, replacing
from googledocstools.notes import beginning
from googledocstools.putting import (
    add_source_arguments,
    check_folder,
    described_picture,
    put_in,
    source,
    upload_name,
)

COMMAND = "replace-picture"


def _number(text):
    """An argparse type: a picture's number, 1 or more."""
    if not re.fullmatch("[0-9]+", text) or int(text) < 1:
        raise argparse.ArgumentTypeError("%r is not a picture's number, 1 or more" % text)
    return int(text)


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="List a Google Doc's pictures, or put a new picture in place of one of them, "
        "keeping its link and its width and everything around it, the caption under it "
        "included. It changes that one picture and nothing else.",
        epilog="Pictures are numbered from 1 in the order they come in the document, as --list "
        "prints them. From a file, the new picture is uploaded into the folder (--folder, or the "
        "setting UPLOAD_FOLDER_ID), shared with anyone who has the link only while it goes in, "
        "then unshared and kept there; if the sharing cannot be taken back the run fails, saying "
        "so: open the copy in Drive, Share, General access, Restricted. From an address, Google "
        "fetches it and nothing is uploaded. The Google secrets are read from the environment: "
        "source env.sh from the secrets folder (google-docs-tools-secrets) in the same command. "
        "Exit codes: 0 listed or replaced (or, with --dry-run, checked); 2 bad arguments, "
        "settings or picture file, or no folder; 3 cannot sign in to Google; 4 Google could not "
        "be reached or answered with an error (a picture it cannot fetch, the document changed "
        "meanwhile), or the sharing could not be taken back; 5 there is no such document, "
        "folder or picture, or Google does not say the old picture's width and --width is not "
        "given.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--list", action="store_true",
        help="print the pictures, numbered, with their width, address, link and the text after")
    parser.add_argument(
        "--picture", metavar="N", type=_number, help="the number of the picture to replace")
    add_source_arguments(parser)
    parser.add_argument(
        "--width", metavar="POINTS", type=points,
        help="the new picture's width in points (default: the old one's)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check everything and say which picture would go; upload, share and change nothing")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _flags(args):
    """Stop unless the flags go together: --list alone, or --picture N with a picture."""
    if args.list:
        for flag, given in (("--picture", args.picture), ("--image-file", args.image_file),
                            ("--image-url", args.image_url), ("--width", args.width),
                            ("--folder", args.folder), ("--dry-run", args.dry_run or None)):
            if given is not None:
                raise Stop(USAGE, "--list goes alone: %s is for replacing a picture, with "
                           "--picture N." % flag)
    elif args.picture is None:
        raise Stop(USAGE, "Give --list to see the pictures, or --picture N to replace one.")


def _about(width, place):
    """What is said of a picture: its width, where it came from, its link, the text after it."""
    parts = ["%g pt wide" % width if width is not None else "width not given"]
    if place.source:
        parts.append("from %s" % place.source)
    if place.link:
        parts.append("linked to %s" % place.link)
    if place.after.strip():
        parts.append('then "%s"' % beginning(place.after))
    return parts


def _read(args, env, send, folder):
    """Sign in, look up the document (and the folder), read it: (session, name, link, described)."""
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        name, link = the_document(session, args.document, progress)
        if folder is not None:
            progress.step = "looking up the folder"
            check_folder(session, folder)
        progress.step = "reading the document"
        return session, name, link, session.document(args.document)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s. Nothing was changed."
                   % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s. Nothing was changed."
                   % (progress.step, said(error)))


def _run(args, env, send, default_settings, out, clock):
    _flags(args)
    found = None if args.list else source(args, default_settings)
    session, name, link, described = _read(args, env, send, found and found.folder)
    places, widths = picture_places(described), picture_widths(described)
    if args.list:
        lines = ["%d picture%s in %s" % (len(places), "" if len(places) == 1 else "s", name)
                 if places else "No pictures in %s" % name]
        lines += ["%d. %s" % (number, ", ".join(_about(width, place)))
                  for number, (place, width) in enumerate(zip(places, widths), start=1)]
        out.write("\n".join(lines) + "\n")
        return OK
    if args.picture > len(places):
        raise Stop(UNEXPECTED, "The document %r has %d picture%s, so there is no picture %d: "
                   "replace-picture DOC --list lists them. Nothing was changed." % (
                       name, len(places), "" if len(places) == 1 else "s", args.picture))
    place, old_width = places[args.picture - 1], widths[args.picture - 1]
    width = args.width if args.width is not None else old_width
    if width is None:
        raise Stop(UNEXPECTED, "Google does not say how wide picture %d is, so give --width "
                   "POINTS. Nothing was changed." % args.picture)
    gone = "picture %d, %s" % (args.picture, ", ".join(_about(None, place)[1:]))
    copy_name = upload_name(name, clock, found.path) if found.path else None
    details = "Width: %g pt\n" % width + ("Picture link: %s\n" % place.link if place.link else "")
    lines = "Document: %s\nLink: %s\n%s: %s\nPicture: %s\n" % (
        name, link, "Would replace" if args.dry_run else "Replaced", gone,
        described_picture(found))
    if args.dry_run:
        upload = "Would upload: %s, into the folder %s, shared only while it goes in\n" % (
            copy_name, found.folder) if found.path else ""
        out.write("Dry run: nothing was uploaded, shared or changed.\n" + lines + upload + details)
        return OK
    kept = put_in(session, found, args.document, name, link,
                  lambda uri: replacing(place.index, uri, width, place.link or None),
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
        return _run(args, env, send, default_settings, sys.stdout, clock)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
