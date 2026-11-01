"""Each call to Google: what is sent, and what is made of the answer."""
import json

import pytest

from googledocstools import google
from tests.conftest import (
    ACCESS_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET,
    DOC,
    FOLDER,
    REFRESH_TOKEN,
)

HOSTILE = "it's a \\ \"test\"\n$HOME </script> é 🐿️ ' or name != '"


def signed_in(fake):
    session = google.Google(fake, 30)
    session.refresh(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    return session


def test_a_query_literal_is_quoted_with_quotes_and_backslashes_escaped():
    assert google.query_literal("plain") == "'plain'"
    assert google.query_literal("it's") == "'it\\'s'"
    assert google.query_literal("back\\slash") == "'back\\\\slash'"
    assert google.query_literal("\\'") == "'\\\\\\''"


def test_refresh_posts_the_form_to_the_token_address_and_keeps_the_access_token(fake):
    session = google.Google(fake, 12)
    session.refresh(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    call = fake.calls[0]
    assert (call["method"], call["url"]) == ("POST", "https://oauth2.googleapis.com/token")
    assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert call["timeout"] == 12
    assert session.token == ACCESS_TOKEN


def test_a_refused_refresh_token_is_a_refused_sign_in_with_googles_reason(fake):
    session = google.Google(fake, 30)
    with pytest.raises(google.SignInRefused) as error:
        session.refresh(CLIENT_ID, CLIENT_SECRET, "stale")
    assert "invalid_grant" in str(error.value)
    assert "expired or revoked" in str(error.value)


def test_a_refused_client_is_a_refused_sign_in(fake):
    session = google.Google(fake, 30)
    with pytest.raises(google.SignInRefused) as error:
        session.refresh(CLIENT_ID, "wrong", REFRESH_TOKEN)
    assert "invalid_client" in str(error.value)


def test_a_refusal_never_repeats_the_secrets_it_was_given(fake):
    session = google.Google(fake, 30)
    with pytest.raises(google.SignInRefused) as error:
        session.refresh(CLIENT_ID, "wrong-secret-value", "stale-token-value")
    assert "wrong-secret-value" not in str(error.value)
    assert "stale-token-value" not in str(error.value)


def test_a_token_reply_without_an_access_token_is_an_error_from_google(fake):
    fake.answers[("POST", "/token")] = (200, {"token_type": "Bearer"})
    with pytest.raises(google.Answered):
        google.Google(fake, 30).refresh(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)


def test_a_server_error_from_the_token_address_is_not_called_a_refusal(fake):
    fake.answers[("POST", "/token")] = (503, {"error": "backend_error"})
    with pytest.raises(google.Answered) as error:
        google.Google(fake, 30).refresh(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    assert error.value.status == 503


def test_describe_asks_for_the_five_facts_with_the_access_token(fake):
    fake.add("doc-1", "Template", DOC)
    session = signed_in(fake)
    assert session.describe("doc-1") == {
        "id": "doc-1", "name": "Template", "mimeType": DOC, "trashed": False,
        "webViewLink": fake.link("doc-1"),
    }
    call = fake.calls[-1]
    assert (call["method"], call["host"], call["path"]) == (
        "GET", "www.googleapis.com", "/drive/v3/files/doc-1")
    assert call["query"] == {"fields": ["id,name,mimeType,trashed,webViewLink"]}
    assert call["headers"]["Authorization"] == "Bearer " + ACCESS_TOKEN


def test_describe_gives_nothing_for_a_file_google_does_not_know(fake):
    assert signed_in(fake).describe("nowhere") is None


def test_an_id_with_hostile_characters_stays_one_piece_of_the_address(fake):
    fake.add("a/b?c#d e", "Odd", DOC)
    session = signed_in(fake)
    assert session.describe("a/b?c#d e")["name"] == "Odd"
    assert fake.calls[-1]["raw_path"] == "/drive/v3/files/a%2Fb%3Fc%23d%20e"


def test_named_in_folder_finds_only_that_name_in_that_folder_and_not_in_the_bin(fake):
    fake.add("folder-1", "Weekly", FOLDER)
    fake.add("a", "2026-10-12 issue", DOC, ["folder-1"])
    fake.add("b", "2026-10-12 issue", DOC, ["other-folder"])
    fake.add("c", "2026-10-19 issue", DOC, ["folder-1"])
    fake.add("d", "2026-10-12 issue", DOC, ["folder-1"], trashed=True)
    found = signed_in(fake).named_in_folder("folder-1", "2026-10-12 issue")
    assert [f["id"] for f in found] == ["a"]
    assert found[0]["webViewLink"] == fake.link("a")
    assert fake.calls[-1]["query"]["fields"] == ["files(id,name,webViewLink)"]


def test_named_in_folder_is_empty_when_nothing_matches(fake):
    assert signed_in(fake).named_in_folder("folder-1", "anything") == []


def test_a_name_with_hostile_characters_is_matched_as_text_not_as_a_query(fake):
    fake.add("a", HOSTILE, DOC, ["folder-1"])
    fake.add("b", "innocent", DOC, ["folder-1"])
    found = signed_in(fake).named_in_folder("folder-1", HOSTILE)
    assert [f["id"] for f in found] == ["a"]


def test_text_of_exports_plain_text_without_the_byte_order_mark(fake):
    fake.add("doc-1", "Template", DOC, text="[DATE]: 🐿️ [TITLE]\nHello")
    assert signed_in(fake).text_of("doc-1") == "[DATE]: 🐿️ [TITLE]\nHello"
    call = fake.calls[-1]
    assert (call["method"], call["path"]) == ("GET", "/drive/v3/files/doc-1/export")
    assert call["query"] == {"mimeType": ["text/plain"]}


def test_docx_of_asks_for_the_word_export_and_gives_its_bytes_whole(fake):
    fake.add("doc-1", "Issue", DOC, text="x")
    fake.files["doc-1"]["docx"] = b"PK\x03\x04\x00binary\xff\xfe\r\n"
    assert signed_in(fake).docx_of("doc-1") == b"PK\x03\x04\x00binary\xff\xfe\r\n"
    call = fake.calls[-1]
    assert (call["method"], call["path"]) == ("GET", "/drive/v3/files/doc-1/export")
    assert call["query"] == {"mimeType": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]}


def test_copy_into_names_the_copy_and_its_one_parent_folder(fake):
    fake.add("doc-1", "Template", DOC, text="body")
    made = signed_in(fake).copy_into("doc-1", HOSTILE, "folder-1")
    call = fake.calls[-1]
    assert (call["method"], call["path"]) == ("POST", "/drive/v3/files/doc-1/copy")
    assert call["query"] == {"fields": ["id,name,webViewLink"]}
    assert call["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(call["body"].decode("utf-8")) == {"name": HOSTILE, "parents": ["folder-1"]}
    assert made == {"id": "copy-1", "name": HOSTILE, "webViewLink": fake.link("copy-1")}


def test_replace_text_matches_case_and_reports_how_many_were_changed(fake):
    fake.add("doc-2", "Issue", DOC, text="[DATE] and [date] and [DATE]")
    changed = signed_in(fake).replace_text("doc-2", "[DATE]", "12 Oct 2026")
    call = fake.calls[-1]
    assert (call["method"], call["host"], call["path"]) == (
        "POST", "docs.googleapis.com", "/v1/documents/doc-2:batchUpdate")
    assert json.loads(call["body"].decode("utf-8")) == {"requests": [{"replaceAllText": {
        "containsText": {"text": "[DATE]", "matchCase": True}, "replaceText": "12 Oct 2026"}}]}
    assert changed == 2
    assert fake.files["doc-2"]["text"] == "12 Oct 2026 and [date] and 12 Oct 2026"


def test_replace_text_counts_nought_when_google_leaves_the_count_out(fake):
    fake.add("doc-2", "Issue", DOC, text="nothing to fill")
    assert signed_in(fake).replace_text("doc-2", "[DATE]", "12 Oct 2026") == 0


def test_account_is_the_address_google_gives_for_the_token(fake):
    fake.account = "someone@example.org"
    assert signed_in(fake).account() == "someone@example.org"
    call = fake.calls[-1]
    assert (call["method"], call["path"]) == ("GET", "/drive/v3/about")
    assert call["query"] == {"fields": ["user(emailAddress)"]}


def test_an_error_answer_carries_googles_status_and_message(fake):
    fake.answers[("GET", "/drive/v3/files/doc-1")] = (
        403, {"error": {"code": 403, "message": "The user does not have sufficient permissions."}})
    with pytest.raises(google.Answered) as error:
        signed_in(fake).describe("doc-1")
    assert error.value.status == 403
    assert error.value.message == "The user does not have sufficient permissions."


def test_an_error_answer_that_is_not_json_still_gives_the_status(fake):
    fake.files["doc-1"] = None  # never reached
    session = signed_in(fake)

    def broken(method, url, headers, body, timeout):
        return 502, b"<html>Bad Gateway</html>"

    session.send = broken
    with pytest.raises(google.Answered) as error:
        session.describe("doc-1")
    assert error.value.status == 502
    assert error.value.message == "no message"


def test_a_good_answer_that_is_not_json_is_an_error_not_a_traceback(fake):
    session = signed_in(fake)
    session.send = lambda *a: (200, b"not json")
    with pytest.raises(google.Answered) as error:
        session.describe("doc-1")
    assert error.value.status == 200


def test_unreachable_passes_straight_through(fake):
    session = signed_in(fake)
    fake.unreachable.add("www.googleapis.com")
    with pytest.raises(google.Unreachable):
        session.describe("doc-1")


def test_exchange_trades_the_sign_in_code_for_tokens_and_keeps_the_access_token(fake):
    from tests.conftest import NEW_REFRESH_TOKEN, SIGN_IN_CODE

    session = google.Google(fake, 30)
    answer = session.exchange(
        CLIENT_ID, CLIENT_SECRET, SIGN_IN_CODE, "a-verifier", "http://127.0.0.1:5000")
    assert answer["refresh_token"] == NEW_REFRESH_TOKEN
    assert session.token == ACCESS_TOKEN
    assert fake.exchanged == {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": SIGN_IN_CODE,
        "code_verifier": "a-verifier", "grant_type": "authorization_code",
        "redirect_uri": "http://127.0.0.1:5000",
    }


def test_a_refused_sign_in_code_is_a_refused_sign_in(fake):
    with pytest.raises(google.SignInRefused):
        google.Google(fake, 30).exchange(
            CLIENT_ID, CLIENT_SECRET, "wrong", "a-verifier", "http://127.0.0.1:5000")


def test_document_id_asks_the_docs_api_for_the_id_only(fake):
    fake.add("doc-1", "Template", DOC)
    assert signed_in(fake).document_id("doc-1") == "doc-1"
    call = fake.calls[-1]
    assert (call["method"], call["host"], call["path"]) == (
        "GET", "docs.googleapis.com", "/v1/documents/doc-1")
    assert call["query"] == {"fields": ["documentId"]}
    assert call["headers"]["Authorization"] == "Bearer " + ACCESS_TOKEN


def test_document_asks_the_docs_api_for_the_whole_description(fake):
    fake.add_document("doc-1", "An issue", ["folder-1"],
                      ["Hello.", [("Lead-in ", {"bold": True}), ("[INSIGHT]", {})]])
    answer = signed_in(fake).document("doc-1")
    call = fake.calls[-1]
    assert (call["method"], call["host"], call["path"]) == (
        "GET", "docs.googleapis.com", "/v1/documents/doc-1")
    assert call["query"] == {}
    assert answer["revisionId"] == "revision-1"
    assert [element["textRun"]["content"]
            for element in answer["body"]["content"][2]["paragraph"]["elements"]] == [
        "Lead-in ", "[INSIGHT]\n"]


def test_change_document_sends_the_requests_to_be_applied_only_at_the_revision_read(fake):
    fake.add_document("doc-1", "An issue", ["folder-1"], ["Dear [NAME],"])
    requests = [
        {"deleteContentRange": {"range": {"startIndex": 6, "endIndex": 12}}},
        {"insertText": {"location": {"index": 6}, "text": "reader"}},
    ]
    signed_in(fake).change_document("doc-1", requests, "revision-1")
    call = fake.calls[-1]
    assert (call["method"], call["host"], call["path"]) == (
        "POST", "docs.googleapis.com", "/v1/documents/doc-1:batchUpdate")
    assert json.loads(call["body"].decode("utf-8")) == {
        "requests": requests, "writeControl": {"requiredRevisionId": "revision-1"}}
    assert fake.paragraphs("doc-1") == [[("Dear reader,", {})]]


def test_comments_reads_every_page_a_hundred_at_a_time_naming_the_fields(fake):
    fake.add("doc", "Doc", DOC)
    fake.files["doc"]["comments"] = [{"id": "c%d" % n, "content": "n"} for n in range(205)]
    found = signed_in(fake).comments("doc")
    assert [c["id"] for c in found] == ["c%d" % n for n in range(205)]
    asked = [c for c in fake.calls if c["path"].endswith("/comments")]
    assert [c["query"].get("pageToken") for c in asked] == [None, ["100"], ["200"]]
    assert all(c["query"]["pageSize"] == ["100"] for c in asked)
    fields = asked[0]["query"]["fields"][0]
    for wanted in ("nextPageToken", "id", "author(displayName)", "content", "createdTime",
                   "resolved", "deleted", "quotedFileContent(value)", "assigneeEmailAddress",
                   "mentionedEmailAddresses", "replies(id,"):
        assert wanted in fields


def test_add_comment_sends_the_text_and_the_quoted_words_as_json_and_nothing_else(fake):
    fake.add("doc", "Doc", DOC)
    made = signed_in(fake).add_comment("doc", HOSTILE, "words " + HOSTILE)
    call = fake.calls[-1]
    assert (call["method"], call["raw_path"]) == ("POST", "/drive/v3/files/doc/comments")
    assert call["query"]["fields"] == ["id"]
    assert json.loads(call["body"].decode("utf-8")) == {
        "content": HOSTILE,
        "quotedFileContent": {"mimeType": "text/plain", "value": "words " + HOSTILE}}
    assert made == "comment-1"


def test_add_comment_with_no_quoted_words_sends_the_text_alone(fake):
    fake.add("doc", "Doc", DOC)
    made = signed_in(fake).add_comment("doc", HOSTILE)
    assert json.loads(fake.calls[-1]["body"].decode("utf-8")) == {"content": HOSTILE}
    assert made == "comment-1"
