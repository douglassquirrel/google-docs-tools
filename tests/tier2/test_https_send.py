"""The real transport, against a stand-in server on this machine only. No outside network."""
import http.server
import threading

import pytest

from googledocstools import google


class _Handler(http.server.BaseHTTPRequestHandler):
    def _reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.server.seen.append({
            "method": self.command, "path": self.path, "body": self.rfile.read(length),
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
        })
        status, body = self.server.reply
        self.send_response(status)
        if status == 302:
            self.send_header("Location", "http://127.0.0.1:%d/elsewhere" % self.server.server_port)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _reply

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    httpd.seen = []
    httpd.reply = (200, b"{}")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def address(server, path):
    return "http://127.0.0.1:%d%s" % (server.server_address[1], path)


def test_sends_the_method_headers_and_body_and_returns_status_and_bytes(server):
    server.reply = (200, b'{"ok": true}')
    status, body = google.https_send(
        "POST", address(server, "/v1/thing?a=1"),
        {"Authorization": "Bearer t", "Content-Type": "application/json; charset=utf-8"},
        b'{"name": "x"}', 5,
    )
    assert (status, body) == (200, b'{"ok": true}')
    assert server.seen == [{
        "method": "POST", "path": "/v1/thing?a=1", "body": b'{"name": "x"}',
        "authorization": "Bearer t", "content_type": "application/json; charset=utf-8",
    }]


def test_a_get_sends_no_body(server):
    google.https_send("GET", address(server, "/x"), {}, None, 5)
    assert (server.seen[0]["method"], server.seen[0]["body"]) == ("GET", b"")


def test_an_error_status_is_returned_with_its_body_not_raised(server):
    server.reply = (404, b'{"error": {"message": "File not found"}}')
    status, body = google.https_send("GET", address(server, "/x"), {}, None, 5)
    assert (status, body) == (404, b'{"error": {"message": "File not found"}}')


def test_a_redirect_is_returned_not_followed_so_the_token_goes_nowhere_else(server):
    server.reply = (302, b"")
    status, _ = google.https_send(
        "GET", address(server, "/x"), {"Authorization": "Bearer t"}, None, 5)
    assert status == 302
    assert [seen["path"] for seen in server.seen] == ["/x"]


def test_nothing_listening_is_unreachable(server):
    port = server.server_address[1]
    server.shutdown()
    server.server_close()
    with pytest.raises(google.Unreachable):
        google.https_send("GET", "http://127.0.0.1:%d/x" % port, {}, None, 5)


def test_an_answer_slower_than_the_timeout_is_unreachable():
    import socket

    silent = socket.socket()
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)
    try:
        with pytest.raises(google.Unreachable):
            google.https_send(
                "GET", "http://127.0.0.1:%d/x" % silent.getsockname()[1], {}, None, 0.2)
    finally:
        silent.close()
