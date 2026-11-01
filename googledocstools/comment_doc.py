"""comment-doc: add a comment to a Google Doc, on some of its words, or list its comments.

From the weekly email's comment command of 1 November 2026, for any document by its id.

It never changes the document's text, a comment already there, or anyone's access: the one
call that changes anything is the one that adds a comment. A comment may be addressed only to
the people in COMMENT_RECIPIENTS (CLAUDE.md non-negotiable 1). PLAN.md has the rest.
"""
import argparse
import os
import sys

from googledocstools import comments, google
from googledocstools.cli import (
    DEFAULT_SETTINGS,
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
    settings_file,
    sign_in,
    the_document,
)
from googledocstools.document import find

COMMAND = "comment-doc"
RECIPIENTS = "COMMENT_RECIPIENTS"


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Add a comment to a Google Doc, on some of its words, or list the document's "
        "comments. It never changes the document's text, a comment already there, or anyone's "
        "access.",
        epilog="Google shows a comment added this way under All comments, not on the words "
        "themselves; the words it is about go at the start of its text, as On \"QUOTE\": TEXT "
        "(with --quote, they go to Google as a quote, which the editor labels \"Original "
        "content deleted\"). --to may name only an address in the setting "
        "COMMENT_RECIPIENTS (commas between, in the settings file ~/.google-docs-tools.conf or "
        "--settings FILE), and the text may hold no other address: Google emails whoever a "
        "comment names. The Google secrets are read from the environment: source env.sh from "
        "the secrets folder (google-docs-tools-secrets) in the same command. Exit codes: 0 done; "
        "2 bad arguments or settings, or an address not allowed; 3 cannot sign in to Google; 4 "
        "Google could not be reached or answered with an error; 5 there is no such document, "
        "or it is not a Google Doc, or the words are not in it exactly once.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--add", metavar="TEXT", help="add a comment with this text (needs --on)")
    parser.add_argument(
        "--on", metavar="QUOTE",
        help="the words the comment is about: in the document exactly once, within a paragraph")
    parser.add_argument(
        "--to", metavar="EMAIL",
        help="address the comment to this person, so that Google emails them; only an "
        "address in the setting COMMENT_RECIPIENTS")
    parser.add_argument(
        "--quote", action="store_true",
        help="give the words to Google as a quote, not at the start of the text (the editor "
        "then shows \"Original content deleted\")")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="check everything and say what would be added, but add nothing")
    parser.add_argument(
        "--list", action="store_true", help="print the document's comments, oldest first")
    parser.add_argument(
        "--open-only", action="store_true", help="with --list: leave out the resolved ones")
    parser.add_argument(
        "--settings", metavar="FILE",
        help="the settings file (default: ~/.google-docs-tools.conf, if it exists)")
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _flags(args):
    """Stop unless the flags go together: one of --add and --list, and only their own flags."""
    if (args.add is None) == (not args.list):
        raise Stop(USAGE, "Give one of --add TEXT (with --on QUOTE) and --list, not %s."
                   % ("both" if args.list else "neither"))
    others = (("--on", args.on is not None), ("--to", args.to is not None),
              ("--quote", args.quote), ("--dry-run", args.dry_run)) if args.list else (
        ("--open-only", args.open_only),)
    for flag, given in others:
        if given:
            raise Stop(USAGE, "%s does not go with %s." % (
                flag, "--list" if args.list else "--add"))
    if args.list:
        return
    if args.on is None:
        raise Stop(USAGE, "--add needs --on QUOTE: the words in the document the comment is "
                   "about.")
    for flag, value in (("--add", args.add), ("--on", args.on)):
        if not value.strip():
            raise Stop(USAGE, "%s is empty." % flag)
    if not args.quote and '": ' in args.on:
        raise Stop(USAGE, '--on holds ": (a quotation mark, a colon and a space), which would '
                   "make the words hard to read back from the comment's text, where they go as "
                   'On "<words>": . Give fewer of the words, or add --quote to give them to '
                   "Google as a quote instead. Nothing was added.")


def _text(args, default_settings):
    """The comment's text as it goes to Google, the mention first; or stop if not allowed."""
    allowed = comments.recipients(settings_file(args, default_settings).get(RECIPIENTS))
    text = args.add if args.quote else "On %s: %s" % (_quoted(args.on), args.add)
    if args.to is not None:
        if not allowed:
            raise Stop(USAGE, "--to needs the setting %s: the addresses a comment may be "
                       "addressed to, with commas between, in the settings file (--settings "
                       "FILE, or ~/.google-docs-tools.conf). Nothing was added."
                       % RECIPIENTS)
        if args.to.lower() not in allowed:
            raise Stop(USAGE, "--to %s is not one of the addresses in the setting %s, the only "
                       "people a comment may be addressed to (Google emails them). Nothing was "
                       "added." % (args.to, RECIPIENTS))
        text = "@%s %s" % (args.to.lower(), text)
    for address in comments.addresses_in(args.add):
        if address not in allowed:
            raise Stop(USAGE, "The text names %s, which is not one of the addresses in the "
                       "setting %s; Google would take it for a mention and email them. Take "
                       "it out. Nothing was added." % (address, RECIPIENTS))
    for address in [] if args.quote else comments.addresses_in(args.on):
        if address not in allowed:
            raise Stop(USAGE, "The words of --on name %s, which is not one of the addresses in "
                       "the setting %s; they go in the comment's text, where Google would take "
                       "it for a mention and email them. Give other words, or add --quote. "
                       "Nothing was added." % (address, RECIPIENTS))
    return text


def _run(args, env, send, default_settings, out):
    _flags(args)
    settings_file(args, default_settings)  # a named file must be readable, list or add
    text = None if args.list else _text(args, default_settings)
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    after = "" if args.list else " Nothing was added."
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        name, link = the_document(session, args.document, progress)
        if args.list:
            progress.step = "reading the comments"
            out.write("\n".join(comments.listing(session.comments(args.document),
                                                 args.open_only)) + "\n")
            return OK
        progress.step = "reading the document"
        described = session.document(args.document)
        places = find(described, args.on)
        if not places:
            raise Stop(UNEXPECTED, "%s is not in the document %r (%s), so there is nothing to "
                       "put the comment on. Copy the words exactly, within one paragraph. "
                       "Nothing was added." % (_quoted(args.on), name, link))
        if len(places) > 1:
            raise Stop(UNEXPECTED, "%s is in the document %r %d times, and must be there "
                       "exactly once. Give more of the words. Nothing was added."
                       % (_quoted(args.on), name, len(places)))
        if args.dry_run:
            out.write("Would add a comment on %s: %s\n" % (_quoted(args.on), text))
            return OK
        progress.step = "adding the comment"
        after = None
        made = session.add_comment(args.document, text, args.on if args.quote else None)
    except google.Unreachable as error:
        if after is None:
            raise Stop(GOOGLE, "Google could not be reached while adding the comment: %s. The "
                       "comment may or may not have been added: run %s %s --list to see "
                       "before trying again." % (error, COMMAND, args.document))
        raise Stop(GOOGLE, "Google could not be reached while %s: %s.%s"
                   % (progress.step, error, after))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s.%s"
                   % (progress.step, said(error), after or " Nothing was added."))
    out.write("Added comment %s on %s\n%s%sdisco=%s\n"
              % (made, _quoted(args.on), link, "&" if "?" in link else "?", made))
    return OK


def _quoted(words):
    return '"%s"' % words


def main(argv, env=None, send=None, default_settings=None):
    """Run the command; the exit code."""
    env = os.environ if env is None else env
    send = google.https_send if send is None else send
    if default_settings is None:
        default_settings = os.path.expanduser(DEFAULT_SETTINGS)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code
    try:
        return _run(args, env, send, default_settings, sys.stdout)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
