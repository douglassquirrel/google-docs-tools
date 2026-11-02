"""What insert-picture and replace-picture share: where the picture comes from, the folder an
uploaded copy goes into, and the one change made with that copy shared only while it goes in.

The writes here are the ones CLAUDE.md non-negotiable 1 allows: the upload into the named folder,
sharing that one copy with anyone as a reader, the one change to the document, and taking the
sharing back. Nothing is deleted or binned.
"""
import argparse
import datetime
import os
import re
import unicodedata
from collections import namedtuple

from googledocstools import google
from googledocstools.cli import GOOGLE, UNEXPECTED, USAGE, Stop, said, settings_file
from googledocstools.picture_file import NotAPicture, read_picture

LONGEST = 2000  # Google takes a picture's address, or a link, of at most 2 kB
FOLDER_SETTING = "UPLOAD_FOLDER_ID"
DRIVE_PICTURE = "https://drive.google.com/uc?id=%s"
UNSHARE = ("Open it in Drive, choose Share, and set General access to Restricted, so that only "
           "the people it was shared with by name can see it.")

# Where the picture comes from: an address Google fetches, or a picture read from a file, to be
# uploaded into folder.
Source = namedtuple("Source", "url picture path folder")


def link_address(text):
    """An argparse type: a web address to link the picture to."""
    if not re.fullmatch(r"https?://\S+", text) or len(text) > LONGEST or any(
            unicodedata.category(each) == "Cc" for each in text):
        raise argparse.ArgumentTypeError(
            "%r is not one web address that starts http:// or https://, with no space, of at most "
            "%d characters" % (text, LONGEST))
    return text


def add_source_arguments(parser):
    """The flags that say where the picture comes from, and the upload folder's."""
    parser.add_argument(
        "--image-file", metavar="FILE",
        help="a PNG, JPEG or GIF on this machine: uploaded into the folder, shared only while "
        "it goes in, then kept there unshared")
    parser.add_argument(
        "--image-url", metavar="URL",
        help="the picture's public https address instead; Google fetches it, nothing is uploaded")
    parser.add_argument(
        "--folder", metavar="ID",
        help="the Drive folder an uploaded copy goes into (setting %s)" % FOLDER_SETTING)
    parser.add_argument(
        "--settings", metavar="FILE",
        help="the settings file (default: ~/.google-docs-tools.conf, if it exists)")


def source(args, default_settings):
    """Where the picture comes from, checked before Google is asked anything; or stop."""
    if (args.image_file is None) == (args.image_url is None):
        raise Stop(USAGE, "Give the picture as --image-file FILE or as --image-url ADDRESS, one of "
                   "them and not both.")
    if args.image_url is not None:
        if not re.fullmatch(r"https://\S+", args.image_url) or len(args.image_url) > LONGEST:
            raise Stop(USAGE, "--image-url %r must be one public address that starts https://, "
                       "with no spaces, of at most %d characters." % (args.image_url, LONGEST))
        return Source(args.image_url, None, None, None)
    try:
        picture = read_picture(args.image_file)
    except NotAPicture as error:
        raise Stop(USAGE, "--image-file: %s Nothing was changed." % error)
    folder = args.folder or settings_file(args, default_settings).get(FOLDER_SETTING)
    if not folder:
        raise Stop(USAGE, "A picture from a file is uploaded into a Drive folder first, and none "
                   "is named: give --folder ID, or the setting %s in the settings file. Nothing "
                   "was changed." % FOLDER_SETTING)
    return Source(None, picture, args.image_file, folder)


def check_folder(session, folder):
    """Stop unless the upload folder is a folder this account can see, not in the bin."""
    found = session.describe(folder)
    if found is None or found.get("trashed") or found.get("mimeType") != google.FOLDER_TYPE:
        raise Stop(UNEXPECTED, "The upload folder %r is not a folder this account can see, or it "
                   "is in the bin. Check the folder's id (between /folders/ and the end of its "
                   "address), and that it is shared with the account the tools sign in as. "
                   "Nothing was changed." % folder)


def upload_name(name, clock, path):
    """What the uploaded copy is called: after the document, the time and the file."""
    when = clock().astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "picture for %s, %s, %s" % (name, when, os.path.basename(path))


def described_picture(found):
    """How the picture is named in what is printed."""
    if found.url is not None:
        return found.url
    return "%s (%s, %d x %d pixels)" % (found.path, found.picture.kind, found.picture.width,
                                        found.picture.height)


def _changed_meanwhile(error):
    return error.status == 400 and "revision" in error.message.lower()


def _change(session, document, name, link, requests, revision):
    """Make the one change; or stop, saying whether it may have been made."""
    try:
        session.change_document(document, requests, revision)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while putting the picture in: %s. The "
                   "picture may or may not be in the document: look at it (%s) before running "
                   "this again." % (error, link))
    except google.Answered as error:
        if _changed_meanwhile(error):
            raise Stop(GOOGLE, "The document %r was changed by someone while this ran, so the "
                       "picture was not put in (Google: %s). Nothing was written to the document. "
                       "Look at it, then run this again." % (name, error.message))
        raise Stop(GOOGLE, "Google answered with an error while putting the picture in: %s. "
                   "Nothing was written to the document. Google has to be able to fetch the "
                   "picture itself, and takes only a PNG, JPEG or GIF." % said(error))


def put_in(session, found, document, name, link, requests_for, revision, copy_name):
    """Make the one change, with the picture from an address, or from its uploaded copy shared
    only for the change. The line saying what became of the copy ("" for an address); or stop."""
    if found.url is not None:
        _change(session, document, name, link, requests_for(found.url), revision)
        return ""
    try:
        made = session.upload(found.folder, copy_name, found.picture.mime, found.picture.data)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while uploading the picture: %s. It may "
                   "or may not have been uploaded into the folder %s, as %r; nothing was shared "
                   "and the document was not changed." % (error, found.folder, copy_name))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while uploading the picture: %s. "
                   "Nothing was uploaded, shared or changed." % said(error))
    copy, copy_link = made.get("id"), made.get("webViewLink") or "the folder %s" % found.folder
    kept = "%s, in the folder %s" % (copy_name, found.folder)
    try:
        shared = session.share_with_anyone(copy)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while sharing the uploaded copy: %s. It "
                   "may or may not be shared with anyone who has the link: check it (%s). %s The "
                   "document was not changed." % (error, copy_link, UNSHARE))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while sharing the uploaded copy: %s. "
                   "It was not shared, and the document was not changed. The copy is kept, not "
                   "shared: %s (%s)." % (said(error), kept, copy_link))
    failed = None
    try:
        _change(session, document, name, link, requests_for(DRIVE_PICTURE % copy), revision)
    except Stop as stop:
        failed = stop
    try:
        session.unshare(copy, shared)
    except (google.Unreachable, google.Answered) as error:
        raise Stop(GOOGLE, "STILL SHARED: the uploaded copy %s is still shared with anyone who "
                   "has the link (%s), because taking the sharing back failed: %s. %s %s" % (
                       kept, copy_link, error, UNSHARE,
                       failed.message if failed else "The picture is in the document."))
    if failed is not None:
        raise Stop(failed.code, "%s The uploaded copy is kept, not shared: %s (%s)." % (
            failed.message, kept, copy_link))
    return "Uploaded copy: %s, kept and no longer shared: %s\n" % (kept, copy_link)
