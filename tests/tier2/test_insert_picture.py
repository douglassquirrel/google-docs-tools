"""insert-picture against the stand-in: a picture from a file or an address, every refusal, and
exactly what it writes."""
import json
import os
import subprocess
import sys

import pytest

from tests.conftest import PICTURE, invented_gif, invented_jpeg, invented_png
from tests.tier2.conftest import DOC_ID, DOC_NAME, PICTURE_URL, PLACE, UPLOADS

UPLOADED = "picture for %s, 2026-11-02 21:50 UTC, a frame grab.png" % DOC_NAME
DRIVE_URI = "https://drive.google.com/uc?id=upload-1"


def _picture(uri=DRIVE_URI, width=220):
    return {"picture": {"uri": uri, "width": width, "unit": "PT", "height": None}}


def _from_file_writes():
    return [("POST", "/upload/drive/v3/files"),
            ("POST", "/drive/v3/files/upload-1/permissions"),
            ("POST", "/v1/documents/%s:batchUpdate" % DOC_ID),
            ("DELETE", "/drive/v3/files/upload-1/permissions/permission-1")]


def _change_requests(fake):
    return [json.loads(c["body"].decode("utf-8"))["requests"] for c in fake.calls
            if c["path"].endswith(":batchUpdate")]


def test_help_names_every_flag_and_contacts_nothing(insert, fake):
    result = insert("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--at", "--image-file", "--image-url", "--caption", "--link", "--width",
                 "--no-centre", "--folder", "UPLOAD_FOLDER_ID", "--settings", "--dry-run",
                 "--timeout", "Restricted"):
        assert word in result.out
    assert fake.calls == []


# --- from a file -----------------------------------------------------------------------------

def test_a_picture_from_a_file_is_uploaded_shared_for_the_change_alone_and_unshared(insert, fake):
    result = insert()
    assert (result.code, result.err) == (0, "")
    assert fake.writes() == _from_file_writes()
    assert fake.paragraphs(DOC_ID) == [
        [("Words before.", {})], [(PICTURE, _picture())], [("Words after.", {})]]
    copy = fake.files["upload-1"]
    assert (copy["name"], copy["parents"], copy["mimeType"], copy["data"], copy["permissions"]) == (
        UPLOADED, [UPLOADS], "image/png", insert.file.read_bytes(), [])
    assert fake.alignments(DOC_ID) == [None, "CENTER", None]
    assert result.out == (
        "Document: %s\nLink: %s\nIn place of: %s\nPicture: %s (PNG, 16 x 12 pixels)\n"
        "Uploaded copy: %s, in the folder %s, kept and no longer shared: %s\n"
        "Width: 220 pt\nCentred: yes\nCaption paragraphs: 0\n"
        % (DOC_NAME, fake.link(DOC_ID), PLACE, insert.file, UPLOADED, UPLOADS,
           fake.link("upload-1")))


@pytest.mark.parametrize("data,mime", [
    (invented_png(), "image/png"), (invented_jpeg(), "image/jpeg"), (invented_gif(), "image/gif")])
def test_a_png_a_jpeg_and_a_gif_each_go_up_as_what_they_are(insert, fake, data, mime):
    insert.file.write_bytes(data)
    assert insert().code == 0
    assert fake.files["upload-1"]["mimeType"] == mime


def test_a_file_name_with_spaces_quotes_and_non_ascii_is_data(insert, fake, tmp_path):
    named = tmp_path / "it's a \"frame\" $HOME café 🐿️.png"
    named.write_bytes(invented_png())
    result = insert(DOC_ID, "--at", PLACE, "--image-file", str(named), defaults=False)
    assert result.code == 0
    assert fake.files["upload-1"]["name"] == (
        "picture for %s, 2026-11-02 21:50 UTC, %s" % (DOC_NAME, named.name))


@pytest.mark.parametrize("data,told", [
    (b"Just words.\n", "not a PNG, JPEG or GIF"), (b"", "is empty")])
def test_a_file_that_is_not_a_picture_is_refused_before_google_is_asked(insert, fake, data, told):
    insert.file.write_bytes(data)
    result = insert()
    assert result.code == 2 and told in result.err and str(insert.file) in result.err
    assert fake.calls == []


def test_an_over_large_file_is_refused_before_google_is_asked(insert, fake):
    from googledocstools.picture_file import LARGEST

    with open(str(insert.file), "wb") as handle:
        handle.truncate(LARGEST + 1)
    result = insert()
    assert result.code == 2 and "50 MB" in result.err and fake.calls == []


def test_no_upload_folder_is_refused_before_google_is_asked(insert, fake):
    insert.settings.write_text("", encoding="utf-8")
    result = insert()
    assert result.code == 2 and "UPLOAD_FOLDER_ID" in result.err and "--folder" in result.err
    assert fake.calls == []


def test_the_folder_flag_wins_over_the_setting(insert, fake):
    from tests.conftest import FOLDER

    fake.add("other-folder", "Other", FOLDER)
    assert insert("--folder", "other-folder").code == 0
    assert fake.files["upload-1"]["parents"] == ["other-folder"]


@pytest.mark.parametrize("change", ["missing", "trashed", "not a folder"])
def test_a_folder_that_is_not_one_this_account_can_use_is_exit_5_and_nothing_is_uploaded(
        insert, fake, change):
    if change == "missing":
        del fake.files[UPLOADS]
    elif change == "trashed":
        fake.files[UPLOADS]["trashed"] = True
    else:
        fake.files[UPLOADS]["mimeType"] = "image/png"
    result = insert()
    assert result.code == 5 and UPLOADS in result.err and fake.writes() == []


# --- from an address -------------------------------------------------------------------------

def test_a_picture_from_an_address_is_fetched_by_google_with_nothing_uploaded_or_shared(
        insert, fake):
    insert.settings.write_text("", encoding="utf-8")
    result = insert(DOC_ID, "--at", PLACE, "--image-url", PICTURE_URL, defaults=False)
    assert result.code == 0
    assert fake.writes() == [("POST", "/v1/documents/%s:batchUpdate" % DOC_ID)]
    assert fake.paragraphs(DOC_ID)[1] == [(PICTURE, _picture(PICTURE_URL))]
    assert "Picture: %s\n" % PICTURE_URL in result.out and "Uploaded copy" not in result.out


@pytest.mark.parametrize("address", [
    "http://example.org/a.png", "example.org/a.png", "", "https://", "https://a b.png",
    "https://example.org/a.png\n", "file:///etc/passwd", "https://example.org/" + "a" * 2000])
def test_an_address_that_is_not_a_plain_https_one_is_refused(insert, fake, address):
    result = insert(DOC_ID, "--at", PLACE, "--image-url", address, defaults=False)
    assert result.code == 2 and "--image-url" in result.err and fake.calls == []


def test_google_refusing_to_fetch_an_address_is_exit_4_with_its_words(insert, fake):
    fake.unfetchable.add(PICTURE_URL)
    result = insert(DOC_ID, "--at", PLACE, "--image-url", PICTURE_URL, defaults=False)
    assert result.code == 4 and "problem retrieving the image" in result.err
    assert "Nothing was written" in result.err and fake.paragraphs(DOC_ID)[1] == [(PLACE, {})]


@pytest.mark.parametrize("argv", [
    (DOC_ID, "--at", PLACE), (DOC_ID, "--at", PLACE, "--image-url", PICTURE_URL,
                              "--image-file", "x.png")])
def test_one_source_and_not_both_must_be_given(insert, fake, argv):
    result = insert(*argv, defaults=False)
    assert result.code == 2 and "--image-file" in result.err and "--image-url" in result.err
    assert fake.calls == []


# --- the caption, the link, the width, the centring ------------------------------------------

def test_a_caption_follows_the_picture_in_its_markup_a_point_smaller(insert, fake):
    assert insert("--caption", "A **frame** grab.\n\nSecond line.").code == 0
    small = {"fontSize": {"magnitude": 10, "unit": "PT"}}
    assert fake.paragraphs(DOC_ID) == [
        [("Words before.", {})], [(PICTURE, _picture())],
        [("A ", small), ("frame", dict(small, bold=True)), (" grab.", small)],
        [("Second line.", small)], [("Words after.", {})]]
    assert fake.alignments(DOC_ID) == [None, "CENTER", "CENTER", "CENTER", None]


def test_a_caption_whose_markup_is_wrong_is_refused(insert, fake):
    result = insert("--caption", "An **open mark")
    assert result.code == 2 and "--caption" in result.err and fake.calls == []


def test_a_link_goes_on_the_picture_itself(insert, fake):
    assert insert("--link", "https://v.example/watch?v=1&t=2").code == 0
    assert fake.paragraphs(DOC_ID)[1] == [
        (PICTURE, dict(_picture(), link={"url": "https://v.example/watch?v=1&t=2"}))]


@pytest.mark.parametrize("link", ["ftp://x.example/a", "https://a b", "x" * 10, ""])
def test_a_link_that_is_not_a_web_address_is_refused(insert, fake, link):
    result = insert("--link", link)
    assert result.code == 2 and "--link" in result.err and fake.calls == []


def test_width_and_no_centre(insert, fake):
    assert insert("--width", "180", "--no-centre").code == 0
    assert fake.paragraphs(DOC_ID)[1] == [(PICTURE, _picture(width=180))]
    assert fake.alignments(DOC_ID) == [None, None, None]


@pytest.mark.parametrize("width", ["0", "-10", "wide", "inf", "nan"])
def test_a_width_that_is_not_a_number_above_0_is_refused(insert, fake, width):
    result = insert("--width", width)
    assert result.code == 2 and "--width" in result.err and fake.calls == []


# --- where it goes ---------------------------------------------------------------------------

def test_words_not_there_or_there_twice_are_exit_5_and_nothing_is_uploaded(insert, fake):
    result = insert(DOC_ID, "--at", "no such words", "--image-file", str(insert.file),
                    defaults=False)
    assert result.code == 5 and "no such words" in result.err and fake.writes() == []
    insert.document([PLACE, "Words.", PLACE])
    result = insert()
    assert result.code == 5 and "2 times" in result.err and fake.writes() == []


def test_words_not_alone_in_their_paragraph_are_exit_5(insert, fake):
    insert.document(["See it here: " + PLACE])
    result = insert()
    assert result.code == 5 and "alone in its paragraph" in result.err and fake.writes() == []
    assert "other words shares it" in result.err


# --- --dry-run -------------------------------------------------------------------------------

def test_dry_run_reads_and_says_what_it_would_do_and_writes_nothing(insert, fake):
    result = insert("--dry-run", "--caption", "A caption.", "--link", "https://v.example/x")
    assert result.code == 0 and fake.writes() == []
    assert result.out == (
        "Dry run: nothing was uploaded, shared or changed.\n"
        "Document: %s\nLink: %s\nIn place of: %s\nPicture: %s (PNG, 16 x 12 pixels)\n"
        "Would upload: %s, into the folder %s, shared only while it goes in\n"
        "Width: 220 pt\nCentred: yes\nCaption paragraphs: 1\nCaption size: 10 pt\n"
        "Picture link: https://v.example/x\n"
        % (DOC_NAME, fake.link(DOC_ID), PLACE, insert.file, UPLOADED, UPLOADS))


# --- when Google fails -----------------------------------------------------------------------

def test_a_document_changed_meanwhile_is_exit_4_and_the_copy_is_still_unshared(insert, fake):
    fake.edited_after_reading = True
    result = insert()
    assert result.code == 4 and "changed by someone" in result.err
    assert fake.writes() == _from_file_writes()
    assert fake.files["upload-1"]["permissions"] == []
    assert "kept, not shared" in result.err and UPLOADED in result.err


def test_sharing_that_cannot_be_taken_back_fails_the_run_loudly(insert, fake):
    fake.unshare_refused = True
    result = insert()
    assert result.code == 4
    assert "STILL SHARED" in result.err and fake.link("upload-1") in result.err
    assert "Restricted" in result.err and "The picture is in the document" in result.err
    assert fake.files["upload-1"]["permissions"] != []
    assert fake.paragraphs(DOC_ID)[1] == [(PICTURE, _picture())]


def test_sharing_that_cannot_be_taken_back_after_a_failed_change_says_both(insert, fake):
    fake.unshare_refused = True
    fake.edited_after_reading = True
    result = insert()
    assert result.code == 4 and "STILL SHARED" in result.err and "changed by someone" in result.err


@pytest.mark.parametrize("path,told", [
    ("/upload/drive/v3/files", "uploading the picture"),
    ("/drive/v3/files/upload-1/permissions", "sharing the uploaded copy")])
def test_an_error_from_google_on_the_upload_or_the_share_is_exit_4_and_the_document_untouched(
        insert, fake, path, told):
    fake.answers[("POST", path)] = (500, {"error": {"code": 500, "message": "Backend Error"}})
    result = insert()
    assert result.code == 4 and told in result.err and "Backend Error" in result.err
    assert fake.paragraphs(DOC_ID)[1] == [(PLACE, {})]
    assert not [c for c in fake.calls if c["path"].endswith(":batchUpdate")]


@pytest.mark.parametrize("after,told", [
    (0, "signing in"), (1, "looking up the document"), (2, "looking up the folder"),
    (3, "reading the document"), (4, "may or may not have been uploaded"),
    (5, "may or may not be shared"), (6, "may or may not be in the document")])
def test_google_out_of_reach_at_each_step_is_exit_4_saying_what_may_have_happened(
        insert, fake, after, told):
    fake.unreachable_after = after
    result = insert()
    assert result.code == 4 and told in result.err and result.out == ""


def test_google_out_of_reach_while_unsharing_is_loud(insert, fake):
    fake.unreachable_after = 7
    result = insert()
    assert result.code == 4 and "STILL SHARED" in result.err


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(insert, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_CLIENT_SECRET"]
    result = insert(environment=environment)
    assert result.code == 3 and fake.calls == []


def test_no_such_document_is_exit_5(insert, fake):
    result = insert("no-such-document-at-all", "--at", PLACE, "--image-file", str(insert.file),
                    defaults=False)
    assert result.code == 5 and fake.writes() == []


def test_the_timeout_goes_with_every_call(insert, fake):
    assert insert("--timeout", "9").code == 0
    assert {call["timeout"] for call in fake.calls} == {9.0}


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "insert-picture"), "--help"], cwd=str(tmp_path),
        capture_output=True, text=True, env={"PATH": os.environ["PATH"]}, check=False)
    assert done.returncode == 0 and "--image-file" in done.stdout and done.stderr == ""


def test_an_error_from_google_while_reading_is_exit_4_with_its_words(insert, fake):
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = insert()
    assert result.code == 4 and "Backend Error" in result.err and fake.writes() == []


def test_the_settings_file_in_the_home_folder_is_read(insert, fake, env, tmp_path, monkeypatch,
                                                      capsys):
    from googledocstools import insert_picture

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    code = insert_picture.main([DOC_ID, "--at", PLACE, "--image-file", str(insert.file)],
                               env=env, send=fake)
    capsys.readouterr()
    assert code == 0 and fake.files["upload-1"]["parents"] == [UPLOADS]
