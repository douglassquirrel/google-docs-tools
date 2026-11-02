"""replace-picture against the stand-in: the list, a picture put in place of another keeping its
link, width and caption, every refusal, and exactly what it writes."""
import json
import os
import subprocess
import sys

import pytest

from tests.conftest import PICTURE
from tests.tier2.conftest import DOC_ID, DOC_NAME, PICTURE_URL, UPLOADS

DRIVE_URI = "https://drive.google.com/uc?id=upload-1"
UPLOADED = "picture for %s, 2026-11-02 21:50 UTC, a frame grab.png" % DOC_NAME


def _look(uri, width, link=None):
    look = {"picture": {"uri": uri, "width": width, "unit": "PT", "height": None}}
    if link:
        look["link"] = {"url": link}
    return look


def _unchanged(fake, but=None):
    """The document's paragraphs as the fixture made them, with picture 2 as given."""
    two = but or _look("https://img.example/two.png", 165, "https://v.example/two")
    return [[("Before.", {})], [(PICTURE, _look("https://img.example/one.png", 220))],
            [("Caption one.", {})], [(PICTURE, two)],
            [("Caption two, under the second picture.", {})],
            [(PICTURE, _look("https://img.example/three.png", 300))], [("After.", {})]]


def test_help_names_every_flag_and_contacts_nothing(replace, fake):
    result = replace("--help", defaults=False)
    assert result.code == 0
    for word in ("DOC", "--list", "--picture", "--image-file", "--image-url", "--width",
                 "--folder", "UPLOAD_FOLDER_ID", "--settings", "--dry-run", "--timeout",
                 "Restricted"):
        assert word in result.out
    assert fake.calls == []


def test_list_numbers_the_pictures_with_width_source_link_and_what_follows_and_writes_nothing(
        replace, fake):
    result = replace(DOC_ID, "--list", defaults=False)
    assert (result.code, result.err) == (0, "")
    assert result.out == (
        "3 pictures in %s\n"
        '1. 220 pt wide, from https://img.example/one.png, then "Caption one."\n'
        "2. 165 pt wide, from https://img.example/two.png, linked to https://v.example/two, "
        'then "Caption two, under the second picture."\n'
        '3. 300 pt wide, from https://img.example/three.png, then "After."\n' % DOC_NAME)
    assert fake.writes() == []


def test_list_of_a_document_with_no_pictures_says_so(replace, fake):
    replace.document(["Only words."])
    assert replace(DOC_ID, "--list", defaults=False).out == "No pictures in %s\n" % DOC_NAME


def test_list_says_what_google_does_not(replace, fake):
    replace.document([[(PICTURE, {})], [(PICTURE, {})]])
    assert replace(DOC_ID, "--list", defaults=False).out == (
        "2 pictures in %s\n1. width not given\n2. width not given\n" % DOC_NAME)


def test_picture_2_from_a_file_keeps_its_link_width_and_caption_and_the_others_stay(
        replace, fake):
    result = replace()
    assert (result.code, result.err) == (0, "")
    assert fake.paragraphs(DOC_ID) == _unchanged(
        fake, _look(DRIVE_URI, 165, "https://v.example/two"))
    assert fake.writes() == [
        ("POST", "/upload/drive/v3/files"), ("POST", "/drive/v3/files/upload-1/permissions"),
        ("POST", "/v1/documents/%s:batchUpdate" % DOC_ID),
        ("DELETE", "/drive/v3/files/upload-1/permissions/permission-1")]
    change = next(c for c in fake.calls if c["path"].endswith(":batchUpdate"))
    requests = json.loads(change["body"].decode("utf-8"))["requests"]
    assert [next(iter(request)) for request in requests] == [
        "deleteContentRange", "insertInlineImage", "updateTextStyle"]
    assert fake.files["upload-1"]["permissions"] == [] and fake.files["upload-1"]["name"] == UPLOADED
    assert result.out == (
        "Document: %s\nLink: %s\n"
        "Replaced: picture 2, from https://img.example/two.png, linked to https://v.example/two, "
        'then "Caption two, under the second picture."\n'
        "Picture: %s (PNG, 16 x 12 pixels)\n"
        "Uploaded copy: %s, in the folder %s, kept and no longer shared: %s\n"
        "Width: 165 pt\nPicture link: https://v.example/two\n"
        % (DOC_NAME, fake.link(DOC_ID), replace.file, UPLOADED, UPLOADS, fake.link("upload-1")))


def test_a_picture_with_no_link_gets_none_and_width_wins_when_given(replace, fake):
    result = replace(DOC_ID, "--picture", "1", "--image-url", PICTURE_URL, "--width", "100",
                     defaults=False)
    assert result.code == 0
    assert fake.paragraphs(DOC_ID)[1] == [(PICTURE, _look(PICTURE_URL, 100))]
    assert fake.writes() == [("POST", "/v1/documents/%s:batchUpdate" % DOC_ID)]
    assert "Picture link" not in result.out


def test_the_last_picture_can_be_replaced(replace, fake):
    assert replace(DOC_ID, "--picture", "3", "--image-url", PICTURE_URL, defaults=False).code == 0
    assert fake.paragraphs(DOC_ID)[5] == [(PICTURE, _look(PICTURE_URL, 300))]


def test_a_picture_beyond_the_last_is_exit_5_and_nothing_is_uploaded(replace, fake):
    result = replace(DOC_ID, "--picture", "4", "--image-file", str(replace.file), defaults=False)
    assert result.code == 5 and "3 pictures" in result.err and "--list" in result.err
    assert fake.writes() == []


@pytest.mark.parametrize("number", ["0", "-1", "two", "1.5"])
def test_a_picture_number_that_is_not_1_or_more_is_refused(replace, fake, number):
    result = replace(DOC_ID, "--picture", number, "--image-url", PICTURE_URL, defaults=False)
    assert result.code == 2 and "--picture" in result.err and fake.calls == []


def test_a_picture_whose_width_google_does_not_give_needs_width(replace, fake):
    replace.document(["Words.", [(PICTURE, {})]])
    result = replace(DOC_ID, "--picture", "1", "--image-url", PICTURE_URL, defaults=False)
    assert result.code == 5 and "--width" in result.err and fake.writes() == []
    result = replace(DOC_ID, "--picture", "1", "--image-url", PICTURE_URL, "--width", "50",
                     defaults=False)
    assert result.code == 0


@pytest.mark.parametrize("argv", [
    (DOC_ID,), (DOC_ID, "--list", "--picture", "1"), (DOC_ID, "--list", "--image-url", PICTURE_URL),
    (DOC_ID, "--list", "--width", "10"), (DOC_ID, "--list", "--dry-run"),
    (DOC_ID, "--list", "--folder", "x"), (DOC_ID, "--image-url", PICTURE_URL)])
def test_list_goes_alone_and_otherwise_a_picture_number_is_needed(replace, fake, argv):
    result = replace(*argv, defaults=False)
    assert result.code == 2 and "--list" in result.err and "--picture" in result.err
    assert fake.calls == []


def test_a_file_that_is_not_a_picture_is_refused_before_google_is_asked(replace, fake):
    replace.file.write_bytes(b"words\n")
    result = replace()
    assert result.code == 2 and "not a PNG, JPEG or GIF" in result.err and fake.calls == []


def test_dry_run_says_which_picture_would_go_and_writes_nothing(replace, fake):
    result = replace("--dry-run")
    assert result.code == 0 and fake.writes() == []
    assert result.out == (
        "Dry run: nothing was uploaded, shared or changed.\n"
        "Document: %s\nLink: %s\n"
        "Would replace: picture 2, from https://img.example/two.png, linked to "
        'https://v.example/two, then "Caption two, under the second picture."\n'
        "Picture: %s (PNG, 16 x 12 pixels)\n"
        "Would upload: %s, into the folder %s, shared only while it goes in\n"
        "Width: 165 pt\nPicture link: https://v.example/two\n"
        % (DOC_NAME, fake.link(DOC_ID), replace.file, UPLOADED, UPLOADS))


def test_a_document_changed_meanwhile_is_exit_4_and_the_copy_unshared(replace, fake):
    fake.edited_after_reading = True
    result = replace()
    assert result.code == 4 and "changed by someone" in result.err
    assert fake.files["upload-1"]["permissions"] == []


def test_sharing_that_cannot_be_taken_back_fails_the_run_loudly(replace, fake):
    fake.unshare_refused = True
    result = replace()
    assert result.code == 4 and "STILL SHARED" in result.err


@pytest.mark.parametrize("after,step", [
    (0, "signing in"), (1, "looking up the document"), (2, "looking up the folder"),
    (3, "reading the document")])
def test_google_out_of_reach_before_any_write_is_exit_4(replace, fake, after, step):
    fake.unreachable_after = after
    result = replace()
    assert result.code == 4 and step in result.err and "Nothing was changed" in result.err


def test_an_error_from_google_while_reading_is_exit_4_with_its_words(replace, fake):
    fake.answers[("GET", "/v1/documents/%s" % DOC_ID)] = (
        500, {"error": {"code": 500, "message": "Backend Error"}})
    result = replace(DOC_ID, "--list", defaults=False)
    assert result.code == 4 and "Backend Error" in result.err


def test_no_such_folder_is_exit_5(replace, fake):
    del fake.files[UPLOADS]
    assert replace().code == 5 and fake.writes() == []


def test_a_missing_secret_is_exit_3_and_nothing_is_contacted(replace, fake, env):
    environment = dict(env)
    del environment["GOOGLE_OAUTH_REFRESH_TOKEN"]
    result = replace(environment=environment)
    assert result.code == 3 and fake.calls == []


def test_the_command_runs_from_any_folder(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    done = subprocess.run(
        [sys.executable, os.path.join(here, "replace-picture"), "--help"], cwd=str(tmp_path),
        capture_output=True, text=True, env={"PATH": os.environ["PATH"]}, check=False)
    assert done.returncode == 0 and "--picture" in done.stdout and done.stderr == ""


def test_the_settings_file_in_the_home_folder_is_read(replace, fake, env, tmp_path, monkeypatch,
                                                      capsys):
    from googledocstools import replace_picture

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    code = replace_picture.main([DOC_ID, "--picture", "1", "--image-file", str(replace.file)],
                                env=env, send=fake)
    capsys.readouterr()
    assert code == 0 and fake.files["upload-1"]["parents"] == [UPLOADS]
    assert fake.files["upload-1"]["name"].startswith("picture for %s, 20" % DOC_NAME)
