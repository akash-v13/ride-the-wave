import socket
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from ridethewave.clients import with_retries, with_timeouts


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return "ok"


class _Client:
    def __init__(self):
        self._session = _Session()


def test_every_request_carries_a_timeout_unless_given():
    c = with_timeouts(_Client(), connect=3, read=7)
    assert c._session.request("GET", "u") == "ok"
    c._session.request("GET", "v", timeout=1)
    assert c._session.calls[0][2]["timeout"] == (3, 7) and c._session.calls[1][2]["timeout"] == 1
    with_timeouts(c)  # idempotent: not wrapped twice
    c._session.request("GET", "w")
    assert c._session.calls[2][2]["timeout"] == (3, 7)


# ---- retries on a dropped connection (the October 2026 sleep/wake failure) ----


class _DropFirst(BaseHTTPRequestHandler):
    """Hangs up on the first request of each method without answering, then answers normally."""

    seen: dict[str, int] = {}

    def _serve(self):
        n = _DropFirst.seen[self.command] = _DropFirst.seen.get(self.command, 0) + 1
        if n == 1:
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = _serve
    do_POST = _serve

    def log_message(self, *args):
        pass


@pytest.fixture
def drop_first_server():
    _DropFirst.seen = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _DropFirst)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_get_survives_a_dropped_connection(drop_first_server):
    plain = requests.Session()
    with pytest.raises(requests.ConnectionError):
        plain.get(drop_first_server + "/assets", timeout=5)  # what alpaca-py did in October
    _DropFirst.seen = {}
    client = with_retries(types.SimpleNamespace(_session=requests.Session()), backoff=0)
    r = client._session.get(drop_first_server + "/assets", timeout=5)
    assert r.text == "ok" and _DropFirst.seen["GET"] == 2


def test_post_is_never_sent_twice(drop_first_server):
    client = with_retries(types.SimpleNamespace(_session=requests.Session()), backoff=0)
    with pytest.raises(requests.ConnectionError):
        client._session.post(drop_first_server + "/orders", data="{}", timeout=5)
    assert _DropFirst.seen["POST"] == 1


def test_with_retries_is_idempotent_and_skips_clients_without_a_session():
    s = requests.Session()
    c = with_retries(types.SimpleNamespace(_session=s))
    adapter = s.get_adapter("https://data.alpaca.markets")
    assert with_retries(c)._session.get_adapter("https://data.alpaca.markets") is adapter
    assert adapter.max_retries.total == 4
    bare = types.SimpleNamespace()
    assert with_retries(bare) is bare
