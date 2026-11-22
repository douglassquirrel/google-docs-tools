"""watch-doc: what is new in a Google Doc and its comments since the last look. It changes nothing.

Every call it makes to Google is a read; the one thing it writes is its snapshot. PLAN.md has what
it prints and the exit codes. From online-publishing-tools' watch-weekly-email (1 November 2026),
for any document by its id, with its comments.
"""
import argparse
import contextlib
import datetime
import os
import signal
import sys
import tempfile
import time

from googledocstools import comments, google, snapshot
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
    settings_file,
    sign_in,
    the_document,
)
from googledocstools.document import paragraphs
from googledocstools.notes import Markers, notes, placeholders
from googledocstools.text import as_text

COMMAND = "watch-doc"
# Each marker: its flag, its setting, and what it is without either.
MARKERS = (("--note-open", "NOTE_OPEN", "["), ("--note-close", "NOTE_CLOSE", "]"),
           ("--placeholder-open", "PLACEHOLDER_OPEN", "{"),
           ("--placeholder-close", "PLACEHOLDER_CLOSE", "}"))
DOUBLED = "SKIP_DOUBLED"
NOTHING_NEW = 6  # --wait: no look found anything new in --for seconds
EVERY, FOR, LEAST = 300, 2700, 60  # --wait's timing, in seconds: the defaults and the floor
SETTLE_LEAST = 30  # --settle's floor, in seconds
UNREPORTED = (" Changes were seen and not reported; the snapshot was not moved on, so the next run "
              "reports them.")
STOPPED = "stopped; the snapshot of the last look is kept."


class _Stopped(Exception):
    """The process was told to stop (SIGTERM) while it waited."""


def _whole_seconds(text):
    if not text.isdigit() or int(text) == 0:
        raise argparse.ArgumentTypeError("%r is not a whole number of seconds" % text)
    return int(text)


def _timing(args):
    """(every, for) in seconds for --wait; or stop if they make no sense."""
    if not args.wait:
        if args.every is not None or args.for_ is not None:
            raise Stop(USAGE, "--every and --for go with --wait; without it watch-doc looks once.")
        if args.settle is not None:
            raise Stop(USAGE, "--settle goes with --wait; without it watch-doc looks once.")
        return None, None
    every = EVERY if args.every is None else args.every
    for_ = FOR if args.for_ is None else args.for_
    if every < LEAST:
        raise Stop(USAGE, "--every must be at least %d seconds, so as not to ask Google too "
                   "often." % LEAST)
    if every > for_:
        raise Stop(USAGE, "--every must not be more than --for (%d seconds)." % for_)
    if args.settle is not None and args.settle < SETTLE_LEAST:
        raise Stop(USAGE, "--settle must be at least %d seconds." % SETTLE_LEAST)
    if args.settle is not None and args.settle > for_:
        raise Stop(USAGE, "--settle must not be more than --for (%d seconds)." % for_)
    return every, for_


def _parser():
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Compare a Google Doc and its comments with the snapshot of the last look, "
        "print only what is new, and save a new snapshot over it. It changes nothing at Google: "
        "every call it makes is a read.",
        epilog="The first line is always a summary: the time of this look and what is new, or "
        "nothing new. With no snapshot yet it makes one and prints the notes, how many "
        "placeholders there are and how many comments are open. Otherwise what is new follows, "
        "in parts, each left out when it is empty: == Changed == (each paragraph changed, added "
        "or removed, and where), == New notes ==, == Notes gone ==, == Comments ==. The text is "
        "compared as read-doc prints it. The markers and SKIP_DOUBLED can be set in the settings "
        "file as NOTE_OPEN, NOTE_CLOSE, PLACEHOLDER_OPEN and PLACEHOLDER_CLOSE; a flag wins. The "
        "Google secrets are read from the environment: run the command through lobster-tools' "
        "secrets with the set that holds them (secrets run google -- COMMAND …), or source a "
        "secrets file in the same command."
        " With --wait it looks every --every seconds and returns with the first look that finds "
        "anything new, printed as above; after --for seconds of nothing new it prints one line "
        "saying so. With --settle too, a look that finds something new does not end it: it "
        "looks again every --settle seconds and returns once nothing has changed since the look "
        "before, with one report of all that changed since it began. Exit codes: 0 the look "
        "worked, whether "
        "or not anything is new (the summary line says which), or with --wait a look found "
        "something new; 6 nothing new in --for seconds (--wait); 130 or 143 stopped while "
        "waiting; 2 bad arguments or settings, or a "
        "--snapshot file that is not this command's snapshot of this document; 3 cannot sign in "
        "to Google; 4 Google could not be reached or answered with an error; 5 there is no such "
        "document, or it is not a Google Doc, or the snapshot could not be written.",
    )
    parser.add_argument(
        "document", metavar="DOC", type=document_id,
        help="the document's id (between /d/ and /edit in its address), or its whole address")
    parser.add_argument(
        "--snapshot", metavar="FILE", required=True,
        help="the snapshot of the last look, written over with this one; made if it is not there")
    parser.add_argument(
        "--dry-run", action="store_true", help="do the look and print it, but save no snapshot")
    parser.add_argument(
        "--wait", action="store_true",
        help="look again and again, and return when a look finds anything new (exit 0) or "
        "after --for seconds of nothing new (exit 6); a look that fails ends it at once")
    parser.add_argument(
        "--every", metavar="SECONDS", type=_whole_seconds,
        help="with --wait, the seconds between looks (default: %d; at least %d)" % (EVERY, LEAST))
    parser.add_argument(
        "--for", metavar="SECONDS", type=_whole_seconds, dest="for_",
        help="with --wait, how long to look before giving up (default: %d)" % FOR)
    parser.add_argument(
        "--settle", metavar="SECONDS", type=_whole_seconds,
        help="with --wait, return only once the document has stood still this long (at least %d), "
        "with all that changed since the wait began" % SETTLE_LEAST)
    parser.add_argument(
        "--settings", metavar="FILE",
        help="the settings file (default: ~/.google-docs-tools.conf, if it exists)")
    for flag, setting, usual in MARKERS:
        parser.add_argument(flag, metavar="TEXT", help="the marker, taken literally (setting "
                            "%s, default %s)" % (setting, usual))
    parser.add_argument(
        "--skip-doubled", metavar="yes|no",
        help="whether text in doubled note markers, such as a merge tag, is left out of the "
        "notes (setting %s, default yes)" % DOUBLED)
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=seconds, default=30,
        help="how long to wait for each answer from Google (default: 30)")
    return parser


def _markers(args, default_settings):
    """The markers from the flags, then the settings, then the defaults; or stop."""
    chosen = settings_file(args, default_settings)
    found = []
    for flag, setting, usual in MARKERS:
        given = getattr(args, flag[2:].replace("-", "_"))
        value = chosen.get(setting, usual) if given is None else given
        if not value:
            raise Stop(USAGE, "%s is empty: a marker must have something in it." % (
                setting if given is None else flag))
        found.append(value)
    given = args.skip_doubled
    value = (chosen.get(DOUBLED, "yes") if given is None else given).lower()
    if value not in ("yes", "no"):
        raise Stop(USAGE, "%s must be yes or no, not %r." % (
            DOUBLED if given is None else "--skip-doubled", value))
    return Markers(*found, value == "yes")


def _before(path, document):
    """The snapshot of the last look, None if there is none yet; or stop if FILE cannot be used."""
    if not os.path.lexists(path):
        parent = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(parent):
            raise Stop(USAGE, "--snapshot %s cannot be made: there is no folder %s to make it "
                       "in." % (path, parent))
        return None
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            taken = snapshot.read(handle.read())
    except (OSError, UnicodeDecodeError, ValueError):
        raise Stop(USAGE, "--snapshot %s is there and is not a snapshot made by this command, so "
                   "it is never written over. Give a name that is not taken, or the snapshot's "
                   "own." % path)
    if taken.document != document:
        raise Stop(USAGE, "--snapshot %s is a snapshot of another document (%s, not %s), so "
                   "nothing is compared and it is left as it was. Give each document a snapshot "
                   "file of its own." % (path, taken.document, document))
    return taken


def _save(path, text):
    """Put a snapshot at path, moved into place whole; mkstemp makes it readable by its owner."""
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(
            dir=os.path.dirname(os.path.abspath(path)), prefix=".snapshot-", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as written:
            written.write(text)
        os.replace(temporary, path)
    except BaseException as error:  # a stop while saving leaves nothing beside the snapshot
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
        if not isinstance(error, OSError):
            raise
        raise Stop(UNEXPECTED, "The look above was printed, but the snapshot %s was not written: "
                   "%s. What was there is as it was, so the next look will report the same "
                   "again." % (path, error.strerror))


def _noted(items):
    return ["%s  in: %s" % item for item in items]


def _first_look(when, found, document, markers, dry_run):
    """The lines of a look with no snapshot to compare with."""
    seen = notes(document, markers)
    left_open = [comment for comment in comments.alive(found) if not comment.get("resolved")]
    return (["%s: no snapshot yet, %s" % (
        when, "and none was made" if dry_run else "so one was made"),
             "== Notes: %d ==" % len(seen)] + _noted(seen)
            + ["Placeholders: %d" % placeholders(document, markers),
               "Open comments: %d" % len(left_open)])


def _later_look(when, before, text, seen, found):
    """The lines of a look compared with the snapshot before, and whether anything is new."""
    changed = snapshot.changes(before.text, text)
    fresh = snapshot.newly([note for note, _ in before.notes], seen)
    gone = snapshot.newly([note for note, _ in seen], before.notes)
    compared = snapshot.comment_changes(before.comments, found)
    lines = [snapshot.summary(when, len(changed), len(fresh), len(gone), compared)]
    for title, part in (("Changed", changed), ("New notes", _noted(fresh)),
                        ("Notes gone", _noted(gone)), ("Comments", compared.lines)):
        if part:
            lines += ["== %s ==" % title] + part
    return lines, snapshot.anything_new(len(changed), len(fresh), len(gone), compared)


def _read(args, env, send):
    """Sign in and read the document and its comments: (what the Docs API says, the comments)."""
    client_id, client_secret, refresh_token = secrets(env)
    session = google.Google(send, args.timeout)
    progress = Progress()
    try:
        sign_in(session, client_id, client_secret, refresh_token)
        the_document(session, args.document, progress)
        progress.step = "reading the document"
        described = session.document(args.document)
        progress.step = "reading the comments"
        return described, session.comments(args.document)
    except google.Unreachable as error:
        raise Stop(GOOGLE, "Google could not be reached while %s: %s. Nothing was changed and "
                   "the snapshot was left as it was; run this again." % (progress.step, error))
    except google.Answered as error:
        raise Stop(GOOGLE, "Google answered with an error while %s: %s. Nothing was changed and "
                   "the snapshot was left as it was." % (progress.step, said(error)))


def _stamp(clock):
    return clock().astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _observe(args, env, send, markers):
    """The document as a look sees it: (its paragraphs, its text, its notes, its comments)."""
    described, found = _read(args, env, send)
    document = paragraphs(described)
    return document, as_text(document), notes(document, markers), found


def _keep(args, when, seen, found, text):
    if not args.dry_run:
        _save(args.snapshot, snapshot.make(snapshot.Snapshot(
            args.document, when, seen, snapshot.comment_state(found), text)))


def _look(args, env, send, markers, out, clock):
    """One look: printed if anything is new (always, without --wait), the snapshot saved after.
    Whether anything was new; a first look always is."""
    before = _before(args.snapshot, args.document)
    document, text, seen, found = _observe(args, env, send, markers)
    when = _stamp(clock)
    if before is None:
        lines, new = _first_look(when, found, document, markers, args.dry_run), True
    else:
        lines, new = _later_look(when, before, text, seen, found)
    if new or not args.wait:
        out.write("\n".join(lines) + "\n")
        out.flush()
    _keep(args, when, seen, found, text)
    return new


def _settling(args, env, send, markers, out, clock, sleep, every, for_):
    """--wait --settle: look every --every seconds until something is new since the snapshot, then
    every --settle seconds until a look sees nothing changed since the one before; then one report
    against the snapshot, which is saved only then. True if it reported, False if --for ran out with
    nothing new; and how many looks."""
    base = _before(args.snapshot, args.document)
    start, looks, previous = clock(), 0, None  # previous: the last look, while something is new
    while True:
        looked = (clock() - start).total_seconds()
        try:
            _, text, seen, found = _observe(args, env, send, markers)
        except Stop as stop:
            raise Stop(stop.code, stop.message + (UNREPORTED if previous is not None else ""))
        looks += 1
        when = _stamp(clock)
        lines, new = _later_look(when, base, text, seen, found)
        now = (text, seen, snapshot.comment_state(found))
        due = looked + (args.settle if new else every)
        if new and (now == previous or due > for_):
            out.write("\n".join(lines) + "\n")
            out.flush()
            _keep(args, when, seen, found, text)
            return True, looks
        previous = now if new else None
        if due > for_:
            return False, looks
        sleep(max(0, due - (clock() - start).total_seconds()))


def _run(args, env, send, default_settings, out, clock, sleep):
    every, for_ = _timing(args)
    markers = _markers(args, default_settings)
    start, looks = clock(), 0
    if args.settle is not None and _before(args.snapshot, args.document) is not None:
        reported, looks = _settling(args, env, send, markers, out, clock, sleep, every, for_)
        if reported:
            return OK
    else:  # a single look, a --wait, or a --settle with no snapshot yet (its first look returns)
        while True:
            new = _look(args, env, send, markers, out, clock)
            looks += 1
            if new or not args.wait:
                return OK
            due = looks * every  # the next look, in seconds from the first: every --every seconds
            if due > for_:
                break
            sleep(max(0, due - (clock() - start).total_seconds()))
    minutes = round((clock() - start).total_seconds() / 60)
    out.write("%s: nothing new in %d minute%s (%d looks)\n" % (
        _stamp(clock), minutes, "" if minutes == 1 else "s", looks))
    return NOTHING_NEW


def _stop(number, frame):
    raise _Stopped()


def main(argv, env=None, send=None, default_settings=None, clock=None, sleep=None):
    """Run the command; the exit code. clock() is the time now, with its time zone; sleep(n)
    waits n seconds."""
    clock = (lambda: datetime.datetime.now(datetime.timezone.utc)) if clock is None else clock
    sleep = time.sleep if sleep is None else sleep
    env = os.environ if env is None else env
    send = google.https_send if send is None else send
    if default_settings is None:
        default_settings = os.path.join(os.path.expanduser("~"), ".google-docs-tools.conf")
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code
    handler = signal.signal(signal.SIGTERM, _stop) if args.wait else None
    try:
        return _run(args, env, send, default_settings, sys.stdout, clock, sleep)
    except Stop as stop:
        sys.stderr.write("%s: %s\n" % (COMMAND, stop.message))
        return stop.code
    except (KeyboardInterrupt, _Stopped) as stopped:
        sys.stderr.write("%s: %s\n" % (COMMAND, STOPPED))
        return 130 if isinstance(stopped, KeyboardInterrupt) else 143
    finally:
        if args.wait:
            signal.signal(signal.SIGTERM, handler)
