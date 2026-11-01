"""The calls the tools make to Google, over HTTPS with the standard library and nothing else.

From online-publishing-tools (its publishingtools/google.py as of 1 November 2026), without the mail calls.

Every call goes through one `send(method, url, headers, body, timeout)` function, which
returns (status, body bytes) or raises Unreachable. The commands use `https_send`; the tests
put a stand-in in its place. Ids, names and text are data: they are percent-encoded into an
address, quoted into a query or JSON-encoded into a body, never pasted in as they are.
"""
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# Google Docs, and the whole of the account's Drive: the narrower drive.file reaches only
# files this client made itself (found by online-publishing-tools, October 2026). No mail.
SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
)
DRIVE = "https://www.googleapis.com/drive/v3"
DOCS = "https://docs.googleapis.com/v1"
DOC_TYPE = "application/vnd.google-apps.document"
FOLDER_TYPE = "application/vnd.google-apps.folder"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Unreachable(Exception):
    """Google could not be reached, or did not answer in time."""


class Answered(Exception):
    """Google answered with an error. Carries its status and its own message."""

    def __init__(self, status, message):
        super().__init__("%d: %s" % (status, message))
        self.status = status
        self.message = message


class SignInRefused(Exception):
    """Google refused the client or the token."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer, not somewhere to follow with the access token."""

    def redirect_request(self, *args, **kwargs):
        return None


def https_send(method, url, headers, body, timeout):
    """Send one request. Returns (status, body); an error status is returned, not raised."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, OSError) as error:
        raise Unreachable(str(getattr(error, "reason", error)))


def query_literal(text):
    """Text as a quoted value in a Drive search, so that it can only ever be a value."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _json(status, body):
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def _message(answer):
    """Google's own words for an error, from either of the two shapes it uses."""
    error = answer.get("error") if isinstance(answer, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    if isinstance(error, str):
        described = answer.get("error_description")
        return "%s (%s)" % (error, described) if isinstance(described, str) else error
    return "no message"


class Google:
    """One signed-in conversation with Google."""

    def __init__(self, send, timeout):
        self.send = send
        self.timeout = timeout
        self.token = None

    def _token_call(self, form):
        status, body = self.send(
            "POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
            urlencode(form).encode("ascii"), self.timeout,
        )
        answer = _json(status, body)
        if status in (400, 401):
            raise SignInRefused(_message(answer))
        if status != 200 or not isinstance(answer, dict) or not answer.get("access_token"):
            raise Answered(status, _message(answer))
        return answer

    def refresh(self, client_id, client_secret, refresh_token):
        """Trade the refresh token for an access token, kept for the calls that follow."""
        answer = self._token_call({
            "client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        })
        self.token = answer["access_token"]

    def exchange(self, client_id, client_secret, code, verifier, redirect_uri):
        """Trade a browser sign-in's code for tokens. Returns Google's answer, tokens and all."""
        answer = self._token_call({
            "client_id": client_id, "client_secret": client_secret, "code": code,
            "code_verifier": verifier, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })
        self.token = answer["access_token"]
        return answer

    def _call(self, method, url, query=None, body=None, missing_is_none=False, raw=False):
        headers = {"Authorization": "Bearer %s" % self.token}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            data = json.dumps(body).encode("utf-8")
        if query:
            url = url + "?" + urlencode(query)
        status, answered = self.send(method, url, headers, data, self.timeout)
        if status == 404 and missing_is_none:
            return None
        if status != 200:
            raise Answered(status, _message(_json(status, answered)))
        if raw:
            return answered
        answer = _json(status, answered)
        if not isinstance(answer, dict):
            raise Answered(status, "an answer that is not JSON")
        return answer

    def describe(self, file_id):
        """A file's id, name, kind, whether it is in the bin and its link; None if Google has no
        such file."""
        return self._call(
            "GET", "%s/files/%s" % (DRIVE, quote(file_id, safe="")),
            {"fields": "id,name,mimeType,trashed,webViewLink"}, missing_is_none=True,
        )

    def named_in_folder(self, folder_id, name):
        """The files with exactly this name in this folder and not in the bin."""
        wanted = "%s in parents and name = %s and trashed = false" % (
            query_literal(folder_id), query_literal(name))
        answer = self._call(
            "GET", DRIVE + "/files", {"q": wanted, "fields": "files(id,name,webViewLink)"})
        return answer.get("files", [])

    def text_of(self, file_id):
        """A Google Doc's text, as plain text."""
        answered = self._call(
            "GET", "%s/files/%s/export" % (DRIVE, quote(file_id, safe="")),
            {"mimeType": "text/plain"}, raw=True,
        )
        return answered.decode("utf-8", errors="replace").lstrip("\ufeff")

    def docx_of(self, file_id):
        """A Google Doc as Google's own Word export gives it: the file's bytes, whole."""
        return self._call(
            "GET", "%s/files/%s/export" % (DRIVE, quote(file_id, safe="")),
            {"mimeType": DOCX_TYPE}, raw=True,
        )

    def copy_into(self, file_id, name, folder_id):
        """Copy a file into a folder under a new name. The folder is always named."""
        return self._call(
            "POST", "%s/files/%s/copy" % (DRIVE, quote(file_id, safe="")),
            {"fields": "id,name,webViewLink"}, body={"name": name, "parents": [folder_id]},
        )

    def document_id(self, document_id):
        """Ask the Docs API (not Drive) for a document: its id, as the Docs API gives it."""
        answer = self._call(
            "GET", "%s/documents/%s" % (DOCS, quote(document_id, safe="")),
            {"fields": "documentId"},
        )
        return answer.get("documentId")

    def document(self, document_id):
        """A document as the Docs API describes it: its revision and every piece of its body."""
        return self._call("GET", "%s/documents/%s" % (DOCS, quote(document_id, safe="")))

    def change_document(self, document_id, requests, revision):
        """Apply requests to a document, all or none, and only if it is still at this revision."""
        return self._call(
            "POST", "%s/documents/%s:batchUpdate" % (DOCS, quote(document_id, safe="")),
            body={"requests": requests, "writeControl": {"requiredRevisionId": revision}},
        )

    def replace_text(self, document_id, find, replacement):
        """Replace every exact occurrence of some text in a document; how many were changed."""
        answer = self._call(
            "POST", "%s/documents/%s:batchUpdate" % (DOCS, quote(document_id, safe="")),
            body={"requests": [{"replaceAllText": {
                "containsText": {"text": find, "matchCase": True}, "replaceText": replacement,
            }}]},
        )
        replies = answer.get("replies") or [{}]
        return int((replies[0].get("replaceAllText") or {}).get("occurrencesChanged", 0))

    def comments(self, file_id):
        """Every comment on a file that is not deleted, replies and all, reading every page."""
        wanted = {
            "pageSize": 100,
            "fields": "nextPageToken,comments(id,author(displayName),content,createdTime,"
                      "resolved,deleted,quotedFileContent(value),assigneeEmailAddress,"
                      "mentionedEmailAddresses,replies(id,author(displayName),content,"
                      "createdTime,deleted,action))",
        }
        found = []
        while True:
            answer = self._call(
                "GET", "%s/files/%s/comments" % (DRIVE, quote(file_id, safe="")), wanted)
            found += answer.get("comments", [])
            if not answer.get("nextPageToken"):
                return found
            wanted = dict(wanted, pageToken=answer["nextPageToken"])

    def add_comment(self, file_id, text, quoted=None):
        """Add one comment to a file, about the quoted words if any; its id. Asked once, never
        again."""
        body = {"content": text}
        if quoted is not None:
            body["quotedFileContent"] = {"mimeType": "text/plain", "value": quoted}
        answer = self._call(
            "POST", "%s/files/%s/comments" % (DRIVE, quote(file_id, safe="")), {"fields": "id"},
            body=body,
        )
        return answer.get("id")

    def account(self):
        """The address of the Google account the access token belongs to."""
        answer = self._call("GET", DRIVE + "/about", {"fields": "user(emailAddress)"})
        return (answer.get("user") or {}).get("emailAddress", "")
