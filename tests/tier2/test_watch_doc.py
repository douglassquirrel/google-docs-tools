"""watch-doc against the stand-in: one look, what it prints and saves, and every refusal."""
import os
import stat
import subprocess
import sys

import pytest

from googledocstools import snapshot, watch_doc
from tests.conftest import Listed, Styled
from tests.tier2.conftest import DOC_ID

NOW = "2026-11-01 19:40 UTC"
HEADED = [Styled("HEADING_1", "One"), "A paragraph of plain words here.",
          Styled("HEADING_2", "Two"), "Another paragraph of plain words.",
          "A third paragraph of plain words."]


def _comment(cid, text="Some words", resolved=False, replies=()):
    return {"id": cid, "createdTime": "2026-11-01T19:38:05.000Z", "content": text,
            "resolved": resolved, "author": {"displayName": "Ann Example"},
            "replies": list(replies)}


def _reply(rid, text="A reply"):
    return {"id": rid, "createdTime": "2026-11-01T19:39:05.000Z", "content": text,
            "author": {"displayName": "Bo Example"}}


def _looked(watch, paragraphs=None, comments=()):
    """A snapshot of a document, taken by a first look."""
    watch.document(HEADED if paragraphs is None else paragraphs)
    watch.comments(list(comments))
    assert watch().code == 0


def test_help_names_the_document_the_snapshot_and_the_flags_and_contacts_nothing(watch, fake):
    result = watch("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--snapshot", "--dry-run", "--settings", "--note-open", "--note-close",
                 "--placeholder-open", "--placeholder-close", "--skip-doubled", "--timeout",
                 "changes nothing", "NOTE_OPEN", "SKIP_DOUBLED"):
        assert word in result.out
    assert fake.calls == []


# --- the first look ------------------------------------------------------------------------

def test_with_no_snapshot_it_makes_one_and_prints_the_counts_to_start_with(watch, fake):
    watch.document(["Before [a note in it] and after, {one} {two}.", "[[merge.tag]] {three}"])
    watch.comments([_comment("c1"), _comment("c2", resolved=True), _comment("c3")])
    result = watch()
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "%s: no snapshot yet, so one was made\n"
        "== Notes: 1 ==\n"
        "[a note in it]  in: Before [a note in it] and after, {one} {two}.\n"
        "Placeholders: 3\n"
        "Open comments: 2\n" % NOW)
    assert snapshot.read(watch.file.read_text(encoding="utf-8")) == snapshot.Snapshot(
        DOC_ID, NOW, [("[a note in it]", "Before [a note in it] and after, {one} {two}.")],
        {"c1": {"resolved": False, "replies": []}, "c2": {"resolved": True, "replies": []},
         "c3": {"resolved": False, "replies": []}},
        "Before [a note in it] and after, {one} {two}.\n\n[[merge.tag]] {three}\n")
    assert fake.writes() == []
    assert [c["path"] for c in fake.calls] == [
        "/token", "/drive/v3/files/%s" % DOC_ID, "/v1/documents/%s" % DOC_ID,
        "/drive/v3/files/%s/comments" % DOC_ID]


def test_a_document_with_no_notes_and_no_comments_says_so(watch):
    watch.document(["Plain."])
    assert watch().out == (
        "%s: no snapshot yet, so one was made\n== Notes: 0 ==\nPlaceholders: 0\n"
        "Open comments: 0\n" % NOW)


def test_the_snapshot_is_readable_by_its_owner_alone_for_it_holds_the_documents_text(watch):
    _looked(watch)
    assert stat.S_IMODE(watch.file.stat().st_mode) == 0o600


# --- later looks ---------------------------------------------------------------------------

def test_nothing_new_is_one_line_and_exit_0(watch):
    _looked(watch)
    result = watch()
    assert (result.code, result.out, result.err) == (0, "%s: nothing new\n" % NOW, "")


def test_an_edit_an_addition_and_a_removal_are_three_entries_each_with_its_heading(watch):
    _looked(watch)
    watch.document([Styled("HEADING_1", "One"), "A paragraph of plain words there.",
                    Styled("HEADING_2", "Two"), "Another paragraph of plain words.",
                    "Quite different and brand new, this."])
    result = watch()
    assert result.code == 0
    assert result.out == (
        "%s: 3 paragraphs changed\n"
        "== Changed ==\n"
        'changed, under "# One": …of plain words {-here.-}{+there.+}\n'
        'removed, under "## Two": A third paragraph of plain words.\n'
        'added, under "## Two": Quite different and brand new, this.\n' % NOW)
    assert watch().out == "%s: nothing new\n" % NOW


def test_a_second_look_compares_with_the_one_before_not_the_first(watch):
    _looked(watch)
    watch.document(HEADED + ["Added once."])
    assert watch().out.startswith("%s: 1 paragraph changed\n" % NOW)
    watch.document(HEADED + ["Added once.", "Added twice."])
    assert watch().out == (
        '%s: 1 paragraph changed\n== Changed ==\nadded, under "## Two": Added twice.\n' % NOW)


def test_a_bold_word_made_plain_shows_as_a_change(watch):
    _looked(watch, ["Some **plain** words."], ())
    _looked(watch, [[("A ", {}), ("bold", {"bold": True}), (" word.", {})]], ())
    watch.document(["A bold word."])
    assert "changed, at the start: A {-**bold**-}{+bold+} word." in watch().out


def test_a_list_mark_changing_shows_as_a_change(watch):
    _looked(watch, ["An item of some words."])
    watch.document([Listed("An item of some words.")])
    assert "changed, at the start: {+-+} An item of…\n" in watch().out


def test_a_note_added_and_a_note_removed_are_a_line_each_with_the_words_around(watch):
    _looked(watch, ["Keep this one, [old note] here."])
    watch.document(["Keep this one, here, [new note] now."])
    result = watch()
    assert "1 new note, 1 note gone" in result.out.split("\n")[0]
    assert ("== New notes ==\n[new note]  in: Keep this one, here, [new note] now.\n"
            "== Notes gone ==\n[old note]  in: Keep this one, [old note] here.\n") in result.out


def test_a_merge_tag_added_is_not_a_note(watch):
    _looked(watch, ["Dear you, and so on."])
    watch.document(["Dear [[contact.first_name]], and so on."])
    result = watch()
    assert "new note" not in result.out and "== New notes ==" not in result.out
    assert "1 paragraph changed" in result.out


def test_a_comment_added_a_reply_added_and_a_comment_resolved_are_three_lines(watch):
    _looked(watch, comments=[_comment("c1"), _comment("c2")])
    watch.comments([_comment("c1", replies=[_reply("r1")]), _comment("c2", resolved=True),
                    _comment("c3", "A new one")])
    result = watch()
    assert result.code == 0
    assert result.out == (
        "%s: 1 new comment, 1 new reply, 1 comment resolved\n"
        "== Comments ==\n"
        "new reply by Bo Example, 2026-11-01 19:39 UTC to comment c1: A reply\n"
        "comment c2 resolved: Some words\n"
        "new comment by Ann Example, 2026-11-01 19:38 UTC: A new one\n" % NOW)
    assert watch().out == "%s: nothing new\n" % NOW


def test_the_parts_come_in_order_and_an_empty_one_is_left_out(watch):
    _looked(watch, ["Words and [gone] words."], [_comment("c1")])
    watch.document(["Words and [fresh] words."])
    watch.comments([_comment("c1", resolved=True)])
    out = watch().out
    assert [line for line in out.split("\n") if line.startswith("==")] == [
        "== Changed ==", "== New notes ==", "== Notes gone ==", "== Comments =="]


def test_text_with_quotes_backslashes_dollars_script_and_non_ascii_is_data(watch):
    hostile = "it's a \\ \"test\" $HOME </script> é 🐿️ café [nøte \"x\"]"
    _looked(watch, ["Plain."], [_comment("c1")])
    watch.document(["Plain.", hostile])
    watch.comments([_comment("c1", hostile)])
    result = watch()
    assert result.code == 0 and hostile in result.out
    assert watch().out == "%s: nothing new\n" % NOW


# --- the markers ---------------------------------------------------------------------------

def test_markers_come_from_the_settings_file(watch):
    watch.settings.write_text("NOTE_OPEN=<<\nNOTE_CLOSE=>>\nPLACEHOLDER_OPEN='(('\n"
                              "PLACEHOLDER_CLOSE='))'\n", encoding="utf-8")
    watch.document(["A <<note>> and [not one] and ((one)) and {not}."])
    result = watch()
    assert "== Notes: 1 ==\n<<note>>  in:" in result.out and "Placeholders: 1\n" in result.out


def test_a_flag_wins_over_the_settings_file(watch):
    watch.settings.write_text("NOTE_OPEN=<<\nNOTE_CLOSE=>>\n", encoding="utf-8")
    watch.document(["A <<note>> and %%this%%."])
    result = watch("--note-open", "%%", "--note-close", "%%")
    assert "== Notes: 1 ==\n%%this%%  in:" in result.out


def test_the_settings_file_in_the_home_folder_is_read_and_the_time_is_the_real_one(
        watch, fake, env, tmp_path, monkeypatch, capsys):
    (tmp_path / "home" / ".google-docs-tools.conf").write_text(
        "NOTE_OPEN=<<\nNOTE_CLOSE=>>\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    watch.document(["A <<note>> here."])
    code = watch_doc.main([DOC_ID, "--snapshot", str(watch.file)], env=env, send=fake)
    out = capsys.readouterr().out
    assert code == 0 and "== Notes: 1 ==\n<<note>>  in:" in out
    assert out[:2] == "20" and " UTC: no snapshot yet" in out


def test_a_named_settings_file_is_read(watch, tmp_path):
    named = tmp_path / "other.conf"
    named.write_text("PLACEHOLDER_OPEN=$(\nPLACEHOLDER_CLOSE=)\n", encoding="utf-8")
    watch.document(["One $(placeholder) here."])
    assert "Placeholders: 1\n" in watch("--settings", str(named)).out


@pytest.mark.parametrize("argv,setting,notes", [
    ((), "", 0), ((), "SKIP_DOUBLED=no\n", 1), (("--skip-doubled", "no"), "", 1),
    (("--skip-doubled", "yes"), "SKIP_DOUBLED=no\n", 0), ((), "SKIP_DOUBLED=YES\n", 0),
])
def test_doubled_markers_are_skipped_unless_told_otherwise(watch, argv, setting, notes):
    watch.settings.write_text(setting, encoding="utf-8")
    watch.document(["Dear [[name]]."])
    assert "== Notes: %d ==\n" % notes in watch(*argv).out


@pytest.mark.parametrize("argv,told", [
    (("--note-open", ""), "--note-open"), (("--note-close", ""), "--note-close"),
    (("--placeholder-open", ""), "--placeholder-open"),
    (("--placeholder-close", ""), "--placeholder-close"),
    (("--skip-doubled", "perhaps"), "--skip-doubled"),
])
def test_a_bad_flag_is_exit_2_and_nothing_is_contacted(watch, fake, argv, told):
    result = watch(*argv)
    assert result.code == 2 and told in result.err and result.out == "" and fake.calls == []
    assert not watch.file.exists()


@pytest.mark.parametrize("line,told", [
    ("NOTE_OPEN=''\n", "NOTE_OPEN"), ("SKIP_DOUBLED=perhaps\n", "SKIP_DOUBLED")])
def test_a_bad_setting_is_exit_2_naming_it(watch, fake, line, told):
    watch.settings.write_text(line, encoding="utf-8")
    result = watch()
    assert result.code == 2 and told in result.err and fake.calls == []


def test_a_settings_file_that_cannot_be_read_is_exit_2(watch, fake, tmp_path):
    result = watch("--settings", str(tmp_path / "not-there.conf"))
    assert result.code == 2 and "not-there.conf" in result.err and fake.calls == []


# --- --dry-run -----------------------------------------------------------------------------

def test_dry_run_with_no_snapshot_prints_the_counts_and_makes_none(watch):
    watch.document(["Plain."])
    result = watch("--dry-run")
    assert result.code == 0
    assert result.out.startswith("%s: no snapshot yet, and none was made\n" % NOW)
    assert not watch.file.exists()


def test_dry_run_with_a_snapshot_compares_and_leaves_it_as_it_was(watch):
    _looked(watch)
    held = watch.file.read_bytes()
    watch.document(HEADED + ["Added."])
    assert "1 paragraph changed" in watch("--dry-run").out
    assert watch.file.read_bytes() == held


# --- the snapshot file ---------------------------------------------------------------------

@pytest.mark.parametrize("held", ["A shopping list.\n", "", "online-publishing-tools snapshot 1\n"])
def test_a_file_that_is_not_its_own_snapshot_is_refused_and_left_alone(watch, fake, held):
    watch.file.write_text(held, encoding="utf-8")
    result = watch()
    assert result.code == 2 and "not a snapshot" in result.err and result.out == ""
    assert watch.file.read_text(encoding="utf-8") == held
    assert fake.calls == []


def test_a_file_that_is_not_text_is_refused_and_left_alone(watch, fake):
    watch.file.write_bytes(b"\xff\xfe\x00binary")
    assert watch().code == 2 and watch.file.read_bytes() == b"\xff\xfe\x00binary"
    assert fake.calls == []


def test_a_folder_given_as_the_snapshot_is_refused(watch, fake, tmp_path):
    result = watch(DOC_ID, "--snapshot", str(tmp_path), defaults=False)
    assert result.code == 2 and "not a snapshot" in result.err and fake.calls == []


def test_a_snapshot_of_another_document_is_refused_and_left_alone(watch, fake):
    other = snapshot.make(snapshot.Snapshot("another-document-id", NOW, [], {}, "Text.\n"))
    watch.file.write_text(other, encoding="utf-8")
    result = watch()
    assert result.code == 2 and "another-document-id" in result.err and result.out == ""
    assert watch.file.read_text(encoding="utf-8") == other and fake.calls == []


def test_no_folder_to_make_the_snapshot_in_is_refused(watch, fake, tmp_path):
    result = watch(DOC_ID, "--snapshot", str(tmp_path / "no-folder" / "file"), defaults=False)
    assert result.code == 2 and "no-folder" in result.err and fake.calls == []


def test_a_document_given_by_its_address_matches_a_snapshot_taken_by_its_id(watch):
    _looked(watch)
    address = "https://docs.google.com/document/d/%s/edit" % DOC_ID
    result = watch(address, "--snapshot", str(watch.file), defaults=False)
    assert result.out == "%s: nothing new\n" % NOW


def test_nothing_is_left_beside_the_snapshot(watch):
    _looked(watch)
    assert os.listdir(str(watch.file.parent)).count(watch.file.name) == 1
    assert [name for name in os.listdir(str(watch.file.parent)) if name.endswith(".tmp")] == []


def test_a_snapshot_that_cannot_be_written_is_exit_5_after_the_look_is_printed(
        watch, monkeypatch):
    _looked(watch)
    held = watch.file.read_bytes()
    watch.document(HEADED + ["Added."])

    def refuse(*_):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(watch_doc.os, "replace", refuse)
    result = watch()
    assert result.code == 5 and "1 paragraph changed" in result.out
    assert "No space left on device" in result.err and "same again" in result.err
    assert watch.file.read_bytes() == held
    assert [name for name in os.listdir(str(watch.file.parent)) if name.endswith(".tmp")] == []


def test_a_temporary_file_that_cannot_be_cleared_away_is_still_a_plain_message(
        watch, monkeypatch):
    watch.document(["Plain."])

    def refuse(*_):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(watch_doc.os, "replace", refuse)
    monkeypatch.setattr(watch_doc.os, "unlink", refuse)
    result = watch()
    assert result.code == 5 and "No space left on device" in result.err


def test_a_folder_it_cannot_write_in_is_exit_5(watch, monkeypatch):
    watch.document(["Plain."])

    def refuse(*_, **__):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(watch_doc.tempfile, "mkstemp", refuse)
    result = watch()
    assert result.code == 5 and "Permission denied" in result.err


# --- what Google may do --------------------------------------------------------------------

def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(watch, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_CLIENT_ID"]
    result = watch(environment=environment)
    assert result.code == 3 and "GOOGLE_OAUTH_CLIENT_ID" in result.err and fake.calls == []


def test_a_refused_sign_in_is_exit_3(watch, env):
    result = watch(environment=dict(env, GOOGLE_OAUTH_REFRESH_TOKEN="old"))
    assert result.code == 3 and "google-sign-in" in result.err and not watch.file.exists()


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "reading the document"),
    (3, "reading the comments")])
def test_google_out_of_reach_is_exit_4_naming_the_step_and_the_snapshot_stays(
        watch, fake, after, step):
    _looked(watch)
    held = watch.file.read_bytes()
    fake.calls.clear()
    fake.unreachable_after = after
    result = watch()
    assert result.code == 4 and step in result.err and result.out == ""
    assert "snapshot was left as it was" in result.err and watch.file.read_bytes() == held


@pytest.mark.parametrize("path", [
    "/v1/documents/%s" % DOC_ID, "/drive/v3/files/%s/comments" % DOC_ID])
def test_an_error_from_google_is_exit_4_with_its_words(watch, fake, path):
    watch.document(["Plain."])
    fake.answers[("GET", path)] = (500, {"error": {"code": 500, "message": "Backend Error"}})
    result = watch()
    assert result.code == 4 and "500" in result.err and "Backend Error" in result.err
    assert not watch.file.exists()


def test_no_such_document_is_exit_5(watch, fake):
    result = watch("no-such-document-at-all", "--snapshot", str(watch.file), defaults=False)
    assert result.code == 5 and "no-such-document-at-all" in result.err
    assert not watch.file.exists()


def test_a_document_in_the_bin_or_not_a_google_doc_is_exit_5(watch, fake):
    fake.files[DOC_ID]["trashed"] = True
    assert watch().code == 5
    fake.files[DOC_ID]["trashed"] = False
    fake.files[DOC_ID]["mimeType"] = "application/pdf"
    assert watch().code == 5 and not watch.file.exists()


@pytest.mark.parametrize("argv", [
    (), ("not an id", "--snapshot", "f"), ("--snapshot", "f"), (DOC_ID,),
    (DOC_ID, "--snapshot", "f", "--timeout", "0")])
def test_bad_arguments_are_exit_2(watch, fake, argv, capsys):
    assert watch(*argv, defaults=False).code == 2 and fake.calls == []


def test_the_timeout_goes_with_every_call(watch, fake):
    watch.document(["Plain."])
    assert watch("--timeout", "7").code == 0
    assert {call["timeout"] for call in fake.calls} == {7.0}


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "watch-doc"), "--help"],
        cwd=str(tmp_path), capture_output=True, text=True, env={"PATH": os.environ["PATH"]},
        check=False,
    )
    assert done.returncode == 0 and "--snapshot" in done.stdout and done.stderr == ""


# --- --wait: look every few minutes, return when something is new (Request 34) ----------------

CHANGED = [Styled("HEADING_1", "One"), "A paragraph of changed words here.",
           Styled("HEADING_2", "Two"), "Another paragraph of plain words.",
           "A third paragraph of plain words."]


def leftovers(watch):
    return sorted(path.name for path in watch.file.parent.iterdir() if path.name.startswith("."))


def test_help_names_the_wait_its_timing_and_its_exit_code(watch, fake):
    result = watch("--help", defaults=False)
    out = " ".join(result.out.split())
    for word in ("--wait", "--every", "--for", "6 nothing new"):
        assert word in out
    assert fake.calls == []


def test_wait_with_no_snapshot_returns_at_once_with_the_first_look(watch):
    watch.document(HEADED)
    result = watch("--wait")
    assert (result.code, result.err) == (0, "")
    assert result.out.startswith("%s: no snapshot yet, so one was made\n" % NOW)
    assert watch.time.slept == [] and watch.file.exists()


def test_wait_with_nothing_new_returns_after_for_with_one_line_and_exit_6(watch):
    _looked(watch)
    result = watch("--wait", "--every", "60", "--for", "180")
    assert (result.code, result.err) == (6, "")
    assert result.out == "2026-11-01 19:43 UTC: nothing new in 3 minutes (4 looks)\n"
    assert watch.time.slept == [60, 60, 60]
    assert snapshot.read(watch.file.read_text(encoding="utf-8")).taken == "2026-11-01 19:43 UTC"


def test_looks_that_take_time_still_come_every_every_seconds_until_for(watch):
    # Seen at Google, 22 November 2026: with --every 60 --for 120 it gave up after 2 looks, as
    # each real look takes a few seconds and the full wait came on top.
    _looked(watch)
    watch.time.drift = 2
    result = watch("--wait", "--every", "60", "--for", "180")
    assert result.code == 6
    assert result.out.endswith(": nothing new in 3 minutes (4 looks)\n")
    assert len(watch.time.slept) == 3 and all(50 < seconds < 60 for seconds in watch.time.slept)


def test_wait_looks_every_five_minutes_for_45_minutes_unless_told(watch):
    _looked(watch)
    result = watch("--wait")
    assert result.code == 6
    assert result.out == "2026-11-01 20:25 UTC: nothing new in 45 minutes (10 looks)\n"
    assert watch.time.slept == [300] * 9


def test_wait_returns_with_the_look_that_found_a_change_as_a_plain_run_prints_it(watch, tmp_path):
    _looked(watch)
    other = tmp_path / "the same, looked at without --wait.snapshot"
    other.write_bytes(watch.file.read_bytes())
    watch.time.then[2] = lambda: watch.document(CHANGED)
    result = watch("--wait", "--every", "60", "--for", "600")
    assert (result.code, result.err) == (0, "")
    assert watch.time.slept == [60, 60]
    assert result.out.startswith("2026-11-01 19:42 UTC: 1 paragraph changed\n")
    plain = watch(DOC_ID, "--snapshot", str(other), defaults=False)
    assert (plain.code, plain.out) == (0, result.out)


@pytest.mark.parametrize("after,said", [
    ([_comment("c1"), _comment("c2")], "1 new comment"),
    ([_comment("c1", resolved=True)], "1 comment resolved"),
    ([_comment("c1", replies=[_reply("r1")])], "1 new reply"),
])
def test_wait_counts_a_comment_alone_as_news(watch, after, said):
    _looked(watch, comments=[_comment("c1")])
    watch.time.then[1] = lambda: watch.comments(after)
    result = watch("--wait", "--every", "60", "--for", "600")
    assert result.code == 0
    assert result.out.splitlines()[0] == "2026-11-01 19:41 UTC: " + said


def test_a_failed_look_ends_the_wait_at_once_with_exit_4_and_no_retry(watch, fake):
    _looked(watch)
    watch.time.then[1] = lambda: fake.unreachable.add("docs.googleapis.com")
    result = watch("--wait", "--every", "60", "--for", "600")
    assert result.code == 4 and result.out == ""
    assert "reading the document" in result.err
    assert watch.time.slept == [60]


def test_a_missing_secret_or_another_documents_snapshot_ends_the_wait_at_once(watch, fake, env):
    _looked(watch)
    environment = dict(env)
    del environment["GOOGLE_OAUTH_REFRESH_TOKEN"]
    calls = len(fake.calls)
    assert watch("--wait", environment=environment).code == 3
    assert len(fake.calls) == calls and watch.time.slept == []
    other = watch("other-document-id-0123", "--snapshot", str(watch.file), "--wait",
                  defaults=False)
    assert other.code == 2 and watch.time.slept == []


@pytest.mark.parametrize("stop,code", [("interrupt", 130), ("terminate", 143)])
def test_stopped_while_waiting_it_ends_quietly_and_the_snapshot_is_whole(watch, stop, code):
    import signal

    _looked(watch)
    kept = watch.file.read_bytes()
    handler = signal.getsignal(signal.SIGTERM)

    def stopping():
        if stop == "interrupt":
            raise KeyboardInterrupt
        os.kill(os.getpid(), signal.SIGTERM)

    watch.time.then[1] = stopping
    result = watch("--wait", "--every", "60", "--for", "600")
    assert (result.code, result.out) == (code, "")
    assert result.err == "watch-doc: stopped; the snapshot of the last look is kept.\n"
    assert snapshot.read(watch.file.read_text(encoding="utf-8")).text == snapshot.read(
        kept.decode("utf-8")).text
    assert leftovers(watch) == [] and signal.getsignal(signal.SIGTERM) is handler


def test_stopped_while_saving_it_leaves_no_temporary_file(watch, monkeypatch):
    _looked(watch)
    kept = watch.file.read_bytes()

    def stopped(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(watch_doc.os, "replace", stopped)
    result = watch("--wait", "--every", "60", "--for", "600")
    assert result.code == 130 and leftovers(watch) == []
    assert watch.file.read_bytes() == kept


@pytest.mark.parametrize("argv,told", [
    (("--every", "60"), "--every and --for go with --wait"),
    (("--for", "600"), "--every and --for go with --wait"),
    (("--wait", "--every", "10"), "--every must be at least 60"),
    (("--wait", "--every", "400", "--for", "300"), "--every must not be more than --for"),
    (("--wait", "--every", "soon"), "--every"),
])
def test_wait_timing_that_makes_no_sense_is_exit_2_and_nothing_is_contacted(
        watch, fake, argv, told):
    result = watch(*argv)
    assert result.code == 2 and told in result.err and fake.calls == []


# --- --wait --settle: return only once the writer pauses (Request 36) --------------------------

def changed(words):
    """HEADED with its first plain paragraph's words changed."""
    return [HEADED[0], words] + HEADED[2:]


def plain_report(watch, tmp_path, kept):
    """What a single look prints, compared with the snapshot held before the wait."""
    other = tmp_path / "the snapshot before the wait.snapshot"
    other.write_bytes(kept)
    return watch(DOC_ID, "--snapshot", str(other), defaults=False).out


def test_settle_with_no_change_at_all_is_exit_6_as_without_it(watch):
    _looked(watch)
    result = watch("--wait", "--every", "60", "--for", "180", "--settle", "30")
    assert (result.code, result.out) == (
        6, "2026-11-01 19:43 UTC: nothing new in 3 minutes (4 looks)\n")


def test_settle_keeps_to_every_while_nothing_changes_though_looks_take_time(watch):
    # Seen at Google, 22 November 2026: --every 60 --for 120 --settle 30 made 2 looks, not 3.
    _looked(watch)
    watch.time.drift = 2
    result = watch("--wait", "--every", "60", "--for", "180", "--settle", "30")
    assert result.code == 6
    assert result.out.endswith(": nothing new in 3 minutes (4 looks)\n")


def test_settle_returns_once_the_document_has_stood_still_with_what_changed(watch, tmp_path):
    _looked(watch)
    kept = watch.file.read_bytes()
    watch.time.then[1] = lambda: watch.document(changed("A paragraph of new words here."))
    result = watch("--wait", "--every", "60", "--for", "600", "--settle", "30")
    assert (result.code, result.err) == (0, "")
    assert watch.time.slept == [60, 30]
    assert result.out.startswith("2026-11-01 19:41 UTC: 1 paragraph changed\n")
    assert snapshot.read(watch.file.read_text(encoding="utf-8")).text != snapshot.read(
        kept.decode("utf-8")).text
    assert plain_report(watch, tmp_path, kept) == result.out


def test_changes_a_minute_apart_come_back_once_start_to_end(watch, tmp_path):
    _looked(watch)
    kept = watch.file.read_bytes()
    for number, words in ((1, "A paragraph"), (2, "A paragraph of"),
                          (3, "A paragraph of fresh words.")):
        watch.time.then[number] = lambda words=words: watch.document(changed(words))
    result = watch("--wait", "--every", "60", "--for", "600", "--settle", "90")
    assert result.code == 0
    assert watch.time.slept == [60, 90, 90, 90]
    assert result.out.splitlines()[0].endswith(": 1 paragraph changed")
    assert "fresh" in result.out and result.out.count("under ") == 1
    assert plain_report(watch, tmp_path, kept) == result.out


def test_a_note_typed_in_two_goes_comes_back_once_whole(watch):
    _looked(watch)
    watch.time.then[1] = lambda: watch.document(changed("A paragraph of plain words here [equiv"))
    watch.time.then[2] = lambda: watch.document(
        changed("A paragraph of plain words here [equivalent for biologists]"))
    result = watch("--wait", "--every", "60", "--for", "600", "--settle", "30")
    assert result.code == 0
    lines = result.out.splitlines()
    assert lines[0].endswith(": 1 paragraph changed, 1 new note")
    assert lines[lines.index("== New notes ==") + 1].startswith("[equivalent for biologists]  in:")


def test_a_writer_who_never_pauses_gets_everything_at_for(watch):
    _looked(watch)
    for number in range(1, 10):
        watch.time.then[number] = lambda number=number: watch.document(
            changed("A paragraph of plain words here, %d." % number))
    result = watch("--wait", "--every", "60", "--for", "300", "--settle", "60")
    assert result.code == 0
    assert result.out.splitlines()[0] == "2026-11-01 19:45 UTC: 1 paragraph changed"
    assert "here, 5." in result.out


def test_a_comment_added_while_it_settles_is_in_the_report(watch):
    _looked(watch, comments=[_comment("c1")])
    watch.time.then[1] = lambda: watch.document(
        changed("A paragraph of plain words here, and more."))
    watch.time.then[2] = lambda: watch.comments([_comment("c1"), _comment("c2")])
    result = watch("--wait", "--every", "60", "--for", "600", "--settle", "30")
    assert result.code == 0 and watch.time.slept == [60, 30, 30]
    assert result.out.splitlines()[0].endswith(": 1 paragraph changed, 1 new comment")


def test_changes_undone_before_it_settles_are_nothing_new(watch):
    _looked(watch)
    watch.time.then[1] = lambda: watch.document(changed("Gone again."))
    watch.time.then[2] = lambda: watch.document(HEADED)
    result = watch("--wait", "--every", "60", "--for", "180", "--settle", "30")
    assert result.code == 6 and "nothing new" in result.out


def test_a_failed_look_while_it_settles_says_the_changes_are_left_for_the_next_run(watch, fake):
    _looked(watch)
    kept = watch.file.read_bytes()
    watch.time.then[1] = lambda: watch.document(changed("Unreported words."))
    watch.time.then[2] = lambda: fake.unreachable.add("docs.googleapis.com")
    result = watch("--wait", "--every", "60", "--for", "600", "--settle", "30")
    assert result.code == 4 and result.out == ""
    assert "Changes were seen and not reported" in result.err and "next run" in result.err
    assert watch.file.read_bytes() == kept
    fake.unreachable.clear()
    assert "Unreported" in watch().out


def test_settle_with_no_snapshot_yet_returns_at_once_with_the_first_look(watch):
    watch.document(HEADED)
    result = watch("--wait", "--settle", "60")
    assert result.code == 0 and "no snapshot yet" in result.out and watch.time.slept == []


@pytest.mark.parametrize("argv,told", [
    (("--settle", "60"), "--settle goes with --wait"),
    (("--wait", "--settle", "10"), "--settle must be at least 30"),
    (("--wait", "--settle", "400", "--for", "300"), "--settle must not be more than --for"),
])
def test_settle_that_makes_no_sense_is_exit_2_and_nothing_is_contacted(watch, fake, argv, told):
    result = watch(*argv)
    assert result.code == 2 and told in result.err and fake.calls == []


def test_help_names_settle(watch):
    assert "--settle" in watch("--help", defaults=False).out
