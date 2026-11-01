"""Shared stand-ins. No test reaches Google: FakeGoogle answers in its place, in memory."""
import base64
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape

import pytest

from googledocstools import google

DOC = "application/vnd.google-apps.document"
FOLDER = "application/vnd.google-apps.folder"

# Invented values. Nothing here is, or looks like, a real credential or a real id.
CLIENT_ID = "client-id-for-tests"
CLIENT_SECRET = "client-secret-for-tests"
REFRESH_TOKEN = "refresh-token-for-tests"
ACCESS_TOKEN = "access-token-for-tests"
NEW_REFRESH_TOKEN = "1//new-refresh/token_for-tests"
SIGN_IN_CODE = "4/code-for-tests"

_MAIL_QUERY = re.compile(
    r'^subject:\("([^"]*)"\)(?: from:(\S+))? after:([0-9]{4})/([0-9]{2})/([0-9]{2})$')
_QUERY = re.compile(
    r"^'((?:[^'\\]|\\.)*)' in parents and name = '((?:[^'\\]|\\.)*)' and trashed = false$",
    re.DOTALL,
)


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def word_export(body):
    """An invented Word file, as a zip's bytes, holding the XML given as the body's content.

    Written as Google's export is laid out, with its text in word/document.xml; nothing here
    is from a real export. Use w_paragraphs() for ordinary paragraphs.
    """
    document = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="%s"><w:body>%s'
                "</w:body></w:document>" % (W, body))
    made = io.BytesIO()
    with zipfile.ZipFile(made, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
    return made.getvalue()


def w_paragraphs(*texts):
    """The XML of paragraphs of plain text, one run each; an empty text is an empty paragraph."""
    return "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % escape(text) if text else "<w:p/>"
                   for text in texts)


def _spec_text(spec):
    """The text of a paragraph given for described(), worked out here on its own terms."""
    if isinstance(spec, (Styled, RuleThen, Listed)):
        spec = spec.runs
    if spec is RULE:
        return ""
    if isinstance(spec, str):
        return spec
    return "".join(text for text, _ in spec).replace(PICTURE, "")


def _unescape(literal):
    return re.sub(r"\\(.)", r"\1", literal, flags=re.DOTALL)


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FakeGoogle:
    """Answers the calls the tools make, as PLAN.md believes Google does, and records them.

    Use it as the `send` function: fake(method, url, headers, body, timeout).
    """

    def __init__(self):
        self.files = {}
        self.calls = []
        self.account = "tools-user@example.org"
        self.unreachable = set()  # hosts that cannot be reached
        self.unreachable_after = None  # refuse every call after this many
        self.refused = 0  # how many calls were refused that way
        self.answers = {}  # (method, path) -> (status, dict) given instead of the real answer
        self.exchange_reply = {
            "access_token": ACCESS_TOKEN,
            "refresh_token": NEW_REFRESH_TOKEN,
            "expires_in": 3599,
            "token_type": "Bearer",
        }
        self.copies = 0
        self.report_occurrences = None  # lie about how many replacements were made
        self.edited_after_reading = False  # a person changes a document just after it is read
        self.edits_left = None  # ...this many times, then no more (None: every time)
        self.edit = None  # what that person does, given the document's entry (default: types "!")
        self.unfetchable = set()  # picture addresses the stand-in "cannot fetch"
        self.mail = {}  # message id -> the message, as add_mail() made it

    def add(self, file_id, name, kind=DOC, parents=(), text="", trashed=False):
        self.files[file_id] = {
            "id": file_id, "name": name, "mimeType": kind, "parents": list(parents),
            "text": text, "trashed": trashed,
        }

    def add_document(self, file_id, name, parents, paragraphs, revision="revision-1"):
        """A Google Doc held piece by piece: paragraphs of (text, style) runs, or plain strings."""
        characters = []
        for runs in paragraphs:
            if isinstance(runs, str):
                runs = [(runs, {})]
            for text, style in runs:
                characters.extend([character, dict(style)] for character in text)
            characters.append(["\n", dict(runs[-1][1])])
        self.add(file_id, name, DOC, parents)
        self.files[file_id]["characters"] = characters
        self.files[file_id]["revision"] = revision

    def add_described(self, file_id, name, parents, paragraphs):
        """A Google Doc that is only ever read: given as paragraphs for described()."""
        self.add(file_id, name, DOC, parents)
        self.files[file_id]["described"] = paragraphs

    def add_mail(self, mail_id, subject, sender="Keap <news@example.org>", when=None,
                 raw=b"Subject: x\r\n\r\nbody\r\n", size=None):
        """A message in the signed-in user's mailbox, with its headers and its raw bytes."""
        when = when or datetime(2026, 10, 12, 6, 30, tzinfo=timezone.utc)
        self.mail[mail_id] = {
            "id": mail_id, "subject": subject, "sender": sender, "when": when, "raw": raw,
            "size": len(raw) if size is None else size,
        }

    def calls_to_gmail_search(self):
        """The searches made of Gmail, in order."""
        return [c for c in self.calls if c["host"] == "gmail.googleapis.com"
                and c["path"] == "/gmail/v1/users/me/messages"]

    def mail_calls(self):
        """The calls made to Gmail, as (method, path, format asked for or None)."""
        return [(c["method"], c["path"], (c["query"].get("format") or [None])[0])
                for c in self.calls if c["host"] == "gmail.googleapis.com"]

    def export_of(self, file_id):
        """The bytes of Google's Word export that the stand-in serves for a document.

        One given as entry["docx"], else, for a document given to add_described(), an invented
        Word file with a paragraph for each paragraph that has text; for any other, bytes that
        are not a Word file at all.
        """
        entry = self.files[file_id]
        if "docx" in entry:
            return entry["docx"]
        if "described" in entry:
            texts = [_spec_text(spec) for spec in entry["described"]]
            return word_export(w_paragraphs(*texts))
        return b"PK\x03\x04 stand-in Word export of " + file_id.encode("utf-8")

    def paragraphs(self, file_id):
        """The document read back: paragraphs of (text, style) runs, like-styled text merged."""
        paragraphs, runs = [], []
        for character, style in self.files[file_id]["characters"]:
            if character == "\n":
                paragraphs.append(runs)
                runs = []
            elif runs and runs[-1][1] == style:
                runs[-1] = (runs[-1][0] + character, style)
            else:
                runs.append((character, dict(style)))
        return paragraphs

    def alignments(self, file_id):
        """Each paragraph's alignment, in order; None where none was ever set."""
        return [style.get("paragraph", {}).get("alignment")
                for character, style in self.files[file_id]["characters"] if character == "\n"]

    def writes(self):
        """The calls that change something at Google, as (method, path)."""
        return [(c["method"], c["path"]) for c in self.calls
                if c["method"] != "GET" and c["host"] != "oauth2.googleapis.com"]

    def __call__(self, method, url, headers, body, timeout):
        parts = urlsplit(url)
        call = {
            "method": method, "host": parts.netloc, "path": unquote(parts.path),
            "raw_path": parts.path, "query": parse_qs(parts.query, keep_blank_values=True),
            "headers": dict(headers), "body": body, "timeout": timeout, "url": url,
        }
        if self.unreachable_after is not None and len(self.calls) >= self.unreachable_after:
            self.refused += 1
            raise google.Unreachable("the stand-in is unplugged")
        self.calls.append(call)
        if parts.scheme != "https":
            raise AssertionError("not https: %s" % url)
        if parts.netloc in self.unreachable:
            raise google.Unreachable("no route to %s" % parts.netloc)
        forced = self.answers.get((method, call["path"]))
        if forced is not None:
            return forced[0], json.dumps(forced[1]).encode("utf-8")
        status, answer = self._answer(call)
        if isinstance(answer, bytes):
            return status, answer
        return status, json.dumps(answer).encode("utf-8")

    def _answer(self, call):
        if call["host"] == "oauth2.googleapis.com" and call["path"] == "/token":
            return self._token(call)
        if call["headers"].get("Authorization") != "Bearer " + ACCESS_TOKEN:
            return 401, {"error": {"code": 401, "message": "Invalid Credentials"}}
        method, host, path = call["method"], call["host"], call["path"]
        if host == "www.googleapis.com" and path == "/drive/v3/about" and method == "GET":
            return 200, {"user": {"emailAddress": self.account}}
        if host == "www.googleapis.com" and path == "/drive/v3/files" and method == "GET":
            return self._list(call)
        if host == "gmail.googleapis.com":
            return self._mail(call)
        # Matched on the address as sent, so an id with a slash in it is still one piece.
        raw = call["raw_path"]
        match = re.fullmatch(r"/drive/v3/files/([^/]+)/comments", raw)
        if host == "www.googleapis.com" and match:
            return self._comments(call, unquote(match.group(1)))
        match = re.fullmatch(r"/drive/v3/files/([^/]+)(/copy|/export)?", raw)
        if host == "www.googleapis.com" and match:
            return self._file(call, unquote(match.group(1)), match.group(2))
        match = re.fullmatch(r"/v1/documents/([^/]+):batchUpdate", raw)
        if host == "docs.googleapis.com" and match and method == "POST":
            return self._replace(call, unquote(match.group(1)))
        match = re.fullmatch(r"/v1/documents/([^/:]+)", raw)
        if host == "docs.googleapis.com" and match and method == "GET":
            return self._document(call, unquote(match.group(1)))
        return 404, {"error": {"code": 404, "message": "The stand-in has no such address"}}

    def _token(self, call):
        if call["method"] != "POST":
            return 405, {"error": "method_not_allowed"}
        if call["headers"].get("Content-Type") != "application/x-www-form-urlencoded":
            return 400, {"error": "invalid_request", "error_description": "not a form"}
        form = {k: v[0] for k, v in parse_qs(call["body"].decode("ascii")).items()}
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return 401, {"error": "invalid_client", "error_description": "Unauthorized"}
        if form.get("grant_type") == "refresh_token":
            if form.get("refresh_token") != REFRESH_TOKEN:
                return 400, {"error": "invalid_grant",
                             "error_description": "Token has been expired or revoked."}
            return 200, {"access_token": ACCESS_TOKEN, "expires_in": 3599,
                         "token_type": "Bearer"}
        if form.get("grant_type") == "authorization_code":
            if form.get("code") != SIGN_IN_CODE or not form.get("code_verifier"):
                return 400, {"error": "invalid_grant", "error_description": "Bad Request"}
            self.exchanged = form
            return 200, self.exchange_reply
        return 400, {"error": "unsupported_grant_type"}

    def _mail(self, call):
        """Gmail, read-only: the list of a search, and one message as metadata or raw."""
        if call["method"] != "GET":
            return 405, {"error": {"code": 405, "message": "The stand-in only lets mail be read"}}
        raw = call["raw_path"]
        if raw == "/gmail/v1/users/me/messages":
            return self._mail_list(call)
        match = re.fullmatch(r"/gmail/v1/users/me/messages/([^/]+)", raw)
        if match:
            return self._mail_message(call, unquote(match.group(1)))
        return 404, {"error": {"code": 404, "message": "The stand-in has no such address"}}

    def _mail_list(self, call):
        match = _MAIL_QUERY.match(call["query"].get("q", [""])[0])
        if not match:
            return 400, {"error": {"code": 400, "message": "Invalid query"}}
        phrase, sender = match.group(1).casefold(), (match.group(2) or "").casefold()
        after = datetime(int(match.group(3)), int(match.group(4)), int(match.group(5)),
                         tzinfo=timezone.utc)
        found = sorted((m for m in self.mail.values()
                        if phrase in " ".join(m["subject"].replace('"', " ").split()).casefold()
                        and sender in m["sender"].casefold()
                        and m["when"] >= after), key=lambda m: m["when"], reverse=True)
        limit = int(call["query"].get("maxResults", ["100"])[0])
        listed = [{"id": m["id"], "threadId": "thread-" + m["id"]} for m in found[:limit]]
        return 200, {"messages": listed, "resultSizeEstimate": len(listed)} if listed else {
            "resultSizeEstimate": 0}

    def _mail_message(self, call, mail_id):
        entry = self.mail.get(mail_id)
        if entry is None:
            return 404, {"error": {"code": 404, "message": "Requested entity was not found."}}
        kind = call["query"].get("format", [None])[0]
        if kind == "raw":
            encoded = base64.urlsafe_b64encode(entry["raw"]).decode("ascii").rstrip("=")
            return 200, {"id": mail_id, "raw": encoded, "sizeEstimate": entry["size"]}
        if kind != "metadata":
            raise AssertionError("the tools ask for a message as metadata or raw, never %r" % kind)
        wanted = {name.lower() for name in call["query"].get("metadataHeaders", [])}
        headers = [{"name": name, "value": value}
                   for name, value in (("From", entry["sender"]), ("Subject", entry["subject"]),
                                       ("Date", "Mon, 12 Oct 2026 07:30:00 +0100"),
                                       ("To", "a-reader@example.org"))
                   if name.lower() in wanted]
        return 200, {"id": mail_id, "threadId": "thread-" + mail_id,
                     "internalDate": str(int(entry["when"].timestamp()) * 1000),
                     "sizeEstimate": entry["size"], "payload": {"headers": headers}}

    def _list(self, call):
        match = _QUERY.match(call["query"].get("q", [""])[0])
        if not match:
            return 400, {"error": {"code": 400, "message": "Invalid Value"}}
        folder, name = _unescape(match.group(1)), _unescape(match.group(2))
        found = [
            {"id": f["id"], "name": f["name"], "webViewLink": self.link(f["id"])}
            for f in self.files.values()
            if folder in f["parents"] and f["name"] == name and not f["trashed"]
        ]
        return 200, {"files": found}

    def _file(self, call, file_id, action):
        entry = self.files.get(file_id)
        if entry is None:
            return 404, {"error": {"code": 404, "message": "File not found: %s." % file_id}}
        if action is None and call["method"] == "GET":
            described = {k: entry[k] for k in ("id", "name", "mimeType", "trashed")}
            if "webViewLink" in call["query"].get("fields", [""])[0]:
                described["webViewLink"] = self.link(file_id)
            return 200, described
        if action == "/export" and call["method"] == "GET":
            if call["query"].get("mimeType") == [DOCX]:
                if entry.get("export_refused"):
                    return 403, {"error": {"code": 403, "message": "This file is too large to "
                                           "be exported."}}
                return 200, self.export_of(file_id)
            if call["query"].get("mimeType") != ["text/plain"]:
                return 400, {"error": {"code": 400, "message": "Bad export type"}}
            text = entry["text"]
            if "characters" in entry:
                text = "".join(character for character, _ in entry["characters"])
            return 200, ("\ufeff" + text).encode("utf-8")
        if action == "/copy" and call["method"] == "POST":
            wanted = json.loads(call["body"].decode("utf-8"))
            self.copies += 1
            new_id = "copy-%d" % self.copies
            self.add(new_id, wanted.get("name", "Copy of " + entry["name"]), entry["mimeType"],
                     wanted.get("parents", ["root"]), entry["text"])
            return 200, {"id": new_id, "name": self.files[new_id]["name"],
                         "webViewLink": self.link(new_id)}
        return 405, {"error": {"code": 405, "message": "Method not allowed"}}

    def _document(self, call, doc_id):
        entry = self.files.get(doc_id)
        if entry is None or entry["mimeType"] != DOC:
            return 404, {"error": {"code": 404, "message": "Requested entity was not found."}}
        if call["query"].get("fields") == ["documentId"]:
            return 200, {"documentId": doc_id}
        if call["query"]:
            raise AssertionError("the tools ask for the id only, or for everything")
        if "described" in entry:
            answer = described(entry["described"])
            answer["documentId"] = doc_id
            answer["title"] = entry["name"]
            return 200, answer
        if "characters" not in entry:
            raise AssertionError("this stand-in document was not added piece by piece")
        answer = described(self.paragraphs(doc_id), entry["revision"])
        answer["documentId"] = doc_id
        answer["title"] = entry["name"]
        if self.edited_after_reading and self.edits_left != 0:
            # Someone types into the document between the tool reading it and writing to it.
            if self.edits_left is not None:
                self.edits_left -= 1
            if self.edit is None:
                entry["characters"].insert(0, ["!", {}])
            else:
                self.edit(entry)
            entry["revision"] = "revision-%d" % (int(entry["revision"].rsplit("-", 1)[1]) + 1)
        return 200, answer

    def _replace(self, call, doc_id):
        entry = self.files.get(doc_id)
        if entry is None:
            return 404, {"error": {"code": 404, "message": "Requested entity was not found."}}
        if "characters" in entry:
            return self._change(entry, doc_id, json.loads(call["body"].decode("utf-8")))
        replies = []
        for request in json.loads(call["body"].decode("utf-8"))["requests"]:
            wanted = request["replaceAllText"]
            find = wanted["containsText"]["text"]
            if not wanted["containsText"].get("matchCase"):
                raise AssertionError("the tools always match case")
            count = entry["text"].count(find)
            entry["text"] = entry["text"].replace(find, wanted["replaceText"])
            if self.report_occurrences is not None:
                count = self.report_occurrences
            replies.append({"replaceAllText": {"occurrencesChanged": count} if count else {}})
        return 200, {"documentId": doc_id, "replies": replies}

    def _change(self, entry, doc_id, body):
        """Apply every request or none, as the Docs API does, and only at the revision asked."""
        def refuse(message):
            return 400, {"error": {"code": 400, "message": message, "status": "INVALID_ARGUMENT"}}

        required = body.get("writeControl", {}).get("requiredRevisionId")
        if required is not None and required != entry["revision"]:
            return refuse("The required revision ID '%s' does not match the latest revision."
                          % required)
        characters = [[character, dict(style)] for character, style in entry["characters"]]

        def place(index):
            """The list position of a document index, or None if it is not a real position."""
            at = 1
            for position, (character, _) in enumerate(characters):
                if at == index:
                    return position
                at += _units(character)
            return len(characters) if at == index else None

        removed = {}  # where text was deleted in this change -> the look of its first character
        for number, request in enumerate(body["requests"]):
            (kind, wanted), = request.items()
            if kind == "deleteContentRange":
                first = place(wanted["range"]["startIndex"])
                last = place(wanted["range"]["endIndex"])
                if first is None or last is None or first >= last:
                    return refuse("Invalid requests[%d].deleteContentRange: bad range" % number)
                if any(character == "\n" for character, _ in characters[first:last]):
                    raise AssertionError("the tools never delete a paragraph's end")
                removed[first] = dict(characters[first][1])
                del characters[first:last]
            elif kind == "insertText":
                position = place(wanted["location"]["index"])
                if position is None or position >= len(characters):
                    return refuse("Invalid requests[%d].insertText: Index %d must be less than "
                                  "the end index of the referenced segment"
                                  % (number, wanted["location"]["index"]))
                # As seen at Google on 11 October 2026: text put where text was just taken
                # out has the whole look of the first character taken out. Otherwise, as its
                # page says, the look of the text just before (or after, at a paragraph's start).
                before = characters[position - 1] if position else None
                source = characters[position] if before is None or before[0] == "\n" else before
                look = dict(removed.get(position, source[1]))
                look.pop("picture", None)  # text after a picture is not itself a picture
                look.pop("paragraph", None)
                # As Google's page says: a line break put in makes a new paragraph with the
                # paragraph style of the place it is put.
                ending = next(style for character, style in characters[position:]
                              if character == "\n")
                added = []
                for character in wanted["text"]:
                    style = dict(look)
                    if character == "\n" and "paragraph" in ending:
                        style["paragraph"] = dict(ending["paragraph"])
                    added.append([character, style])
                characters[position:position] = added
            elif kind == "insertInlineImage":
                position = place(wanted["location"]["index"])
                if position is None or position >= len(characters):
                    return refuse("Invalid requests[%d].insertInlineImage: bad index" % number)
                if wanted["uri"] in self.unfetchable:
                    return refuse(
                        "Invalid requests[%d].insertInlineImage: There was a problem retrieving "
                        "the image. The provided image should be publicly accessible, within "
                        "size limit, and in supported formats." % number)
                # Believed: a picture, like text, has the look of what was taken out there.
                look = dict(removed.get(position, {}))
                look["picture"] = {"uri": wanted["uri"],
                                   "width": wanted["objectSize"]["width"]["magnitude"],
                                   "unit": wanted["objectSize"]["width"]["unit"],
                                   "height": wanted["objectSize"].get("height")}
                characters.insert(position, [PICTURE, look])
            elif kind == "updateParagraphStyle":
                first = place(wanted["range"]["startIndex"])
                last = place(wanted["range"]["endIndex"])
                if first is None or last is None or first >= last:
                    return refuse("Invalid requests[%d].updateParagraphStyle: bad range" % number)
                # Every paragraph the range touches: each ends at the first line break at or
                # after one of the range's characters.
                reached = first
                while reached < last:
                    ending = next(index for index in range(reached, len(characters))
                                  if characters[index][0] == "\n")
                    paragraph = dict(characters[ending][1].get("paragraph", {}))
                    for field in wanted["fields"].split(","):
                        if field in wanted["paragraphStyle"]:
                            paragraph[field] = wanted["paragraphStyle"][field]
                        else:
                            paragraph.pop(field, None)
                    characters[ending][1]["paragraph"] = paragraph
                    reached = ending + 1
            elif kind == "updateTextStyle":
                first = place(wanted["range"]["startIndex"])
                last = place(wanted["range"]["endIndex"])
                if first is None or last is None or first >= last:
                    return refuse("Invalid requests[%d].updateTextStyle: bad range" % number)
                for _, style in characters[first:last]:
                    for field in wanted["fields"].split(","):
                        if field in wanted["textStyle"]:
                            style[field] = wanted["textStyle"][field]
                        else:
                            style.pop(field, None)
            else:
                raise AssertionError("the stand-in does not know the request %r" % kind)
        entry["characters"] = characters
        entry["revision"] = "revision-%d" % (int(entry["revision"].rsplit("-", 1)[1]) + 1)
        return 200, {"documentId": doc_id, "replies": [{} for _ in body["requests"]],
                     "writeControl": {"requiredRevisionId": entry["revision"]}}

    def _comments(self, call, file_id):
        """A file's comments: listed a page at a time, or one added. Both must name fields."""
        entry = self.files.get(file_id)
        if entry is None:
            return 404, {"error": {"code": 404, "message": "File not found: %s." % file_id}}
        if not call["query"].get("fields"):
            return 400, {"error": {"code": 400, "message": "The 'fields' parameter is required "
                                   "for this operation."}}
        held = entry.setdefault("comments", [])
        if call["method"] == "GET":
            size = int(call["query"].get("pageSize", ["20"])[0])
            if not 1 <= size <= 100:
                return 400, {"error": {"code": 400, "message": "Invalid pageSize"}}
            start = int(call["query"].get("pageToken", ["0"])[0])
            shown = [c for c in held if not c.get("deleted")
                     or call["query"].get("includeDeleted") == ["true"]]
            answer = {"comments": shown[start:start + size]}
            if start + size < len(shown):
                answer["nextPageToken"] = str(start + size)
            return 200, answer
        if call["method"] == "POST":
            wanted = json.loads(call["body"].decode("utf-8"))
            if not wanted.get("content"):
                return 400, {"error": {"code": 400, "message": "Required parameter: content"}}
            made = dict(wanted, id="comment-%d" % (len(held) + 1), resolved=False,
                        createdTime="2026-10-19T12:00:00.000Z",
                        author={"displayName": "Tools User"})
            held.append(made)
            return 200, made
        return 405, {"error": {"code": 405, "message": "Method not allowed"}}

    @staticmethod
    def link(file_id):
        return "https://docs.example.org/document/d/%s/edit" % file_id


@pytest.fixture
def fake():
    return FakeGoogle()


def _units(text):
    # Counted here on its own terms, not with the code under test.
    return sum(2 if ord(character) > 0xFFFF else 1 for character in text)


class Styled:
    """A paragraph of another kind for described(): Styled("HEADING_1", "A heading").

    With alignment="CENTER" its paragraph style says so, as Google's does; without, it says
    nothing, as Google's does for a paragraph never aligned.
    """

    def __init__(self, kind, runs, alignment=None):
        self.kind, self.runs, self.alignment = kind, runs, alignment


class Listed:
    """A list item for described(): Listed("An item", "list-1", level=1), numbered=True for a
    level that counts, start=N for one that does not count from 1.

    Believed from Google's page for the Docs API, not yet seen: the paragraph has a bullet with
    the list's id and its level, left out at level 0; the document's lists say, level by level,
    a glyphSymbol for a bullet or a glyphType for a number. Google's lists have nine levels.
    """

    def __init__(self, runs, list_id="list-1", level=0, numbered=False, start=None):
        self.runs, self.list_id, self.level = runs, list_id, level
        self.numbered, self.start = numbered, start


RULE = object()  # a horizontal rule, as a paragraph for described()


class RuleThen:
    """A paragraph for described() that starts with a horizontal rule and goes on with text, as
    two of the 12 October 2026 issue's headings do at Google: RuleThen([("Briefly…", {...})])."""

    def __init__(self, runs):
        self.runs = [(runs, {})] if isinstance(runs, str) else runs


PICTURE = "\ufffc"  # how the stand-in holds a picture: one character with the picture as its look


def described(paragraphs, revision="revision-1"):
    """A document as the Docs API describes it, built from paragraphs of (text, style) runs.

    A paragraph may be given as one plain string. As at Google, the body starts with a section
    break that takes index 0, the text starts at 1, and each paragraph ends with a newline.
    """
    index = 1
    content = [{"endIndex": 1, "sectionBreak": {"sectionStyle": {}}}]
    objects = {}  # the pictures that say where they came from, as Google keeps them
    lists = {}  # the lists, as Google keeps them
    for runs in paragraphs:
        kind, alignment, bullet = "NORMAL_TEXT", None, None
        if isinstance(runs, Listed):
            bullet = {"listId": runs.list_id}
            if runs.level:
                bullet["nestingLevel"] = runs.level
            levels = lists.setdefault(runs.list_id, {"listProperties": {"nestingLevels": [
                {"glyphSymbol": "\u25cf"} for _ in range(9)]}})["listProperties"]["nestingLevels"]
            if runs.numbered:
                levels[runs.level] = {"glyphType": "DECIMAL", "glyphFormat": "%%%d." % runs.level}
                if runs.start is not None:
                    levels[runs.level]["startNumber"] = runs.start
            runs = runs.runs
        if isinstance(runs, Styled):
            kind, alignment, runs = runs.kind, runs.alignment, runs.runs
        if isinstance(runs, str):
            runs = [(runs, {})]
        elements = []
        start = index
        if isinstance(runs, RuleThen):
            elements.append({"startIndex": index, "endIndex": index + 1, "horizontalRule": {}})
            index += 1
            runs = runs.runs
        elif runs is RULE:
            # As at Google: a rule is an element of its own, one position wide, in a paragraph.
            elements.append({"startIndex": index, "endIndex": index + 1, "horizontalRule": {}})
            index += 1
            runs = [("", {})]
        for position, (text, style) in enumerate(runs):
            if position == len(runs) - 1:
                text += "\n"
            if text.startswith(PICTURE):
                # As at Google: a picture is an element of its own, one position wide.
                source = style.get("source")  # given as the picture's style: {"source": address}
                size = style.get("size")  # and its size in points: {"size": (width, height)}
                object_id = "picture" if source is None else "picture:" + source
                if size is not None:
                    object_id += "@%gx%g" % size
                if source is not None or size is not None:
                    embedded = {}
                    if source is not None:
                        embedded["imageProperties"] = {"sourceUri": source}
                    if size is not None:
                        embedded["size"] = {
                            "width": {"magnitude": size[0], "unit": "PT"},
                            "height": {"magnitude": size[1], "unit": "PT"}}
                    objects[object_id] = {"inlineObjectProperties": {"embeddedObject": embedded}}
                element = {"inlineObjectId": object_id}
                if "link" in style:
                    # As at Google (seen 26 October 2026): a picture's link is in the picture
                    # element's own textStyle.
                    element["textStyle"] = {"link": dict(style["link"])}
                elements.append({"startIndex": index, "endIndex": index + 1,
                                 "inlineObjectElement": element})
                index += 1
                text = text[1:]
                if not text:
                    continue
            end = index + _units(text)
            elements.append({"startIndex": index, "endIndex": end,
                             "textRun": {"content": text, "textStyle": dict(style)}})
            index = end
        style = {"namedStyleType": kind}
        if alignment:
            style["alignment"] = alignment
        paragraph = {"elements": elements, "paragraphStyle": style}
        if bullet:
            paragraph["bullet"] = bullet
        content.append({"startIndex": start, "endIndex": index, "paragraph": paragraph})
    answer = {"documentId": "a-document", "revisionId": revision, "body": {"content": content}}
    if objects:
        answer["inlineObjects"] = objects
    if lists:
        answer["lists"] = lists
    return answer


@pytest.fixture
def wiki():
    """A stand-in for Wikimedia Commons: no test reaches the real one."""
    from tests.invented_commons import FakeCommons

    return FakeCommons()
