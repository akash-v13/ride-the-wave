from ridethewave.clients import with_timeouts


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
