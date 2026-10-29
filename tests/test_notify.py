"""Phone pushes through ntfy. requests.post is replaced: no network."""

from __future__ import annotations

import base64

import pytest
import requests

from ridethewave.operator import notify as nt


class _Resp:
    def __init__(self, status):
        self.status_code = status


@pytest.fixture
def posts(monkeypatch):
    sent = []
    status = {"code": 200}

    def fake_post(url, data=None, headers=None, timeout=None):
        sent.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return _Resp(status["code"])

    monkeypatch.setattr(nt.requests, "post", fake_post)
    monkeypatch.setattr(nt, "_desktop", lambda title, message: None)  # no macOS banners from the test run
    return sent, status


def test_push_posts_to_the_topic(posts):
    sent, _ = posts
    assert nt.push("Ride The Wave ALERT", "heartbeat stale: 4.0 min", "rtw-abc123", "https://ntfy.sh/") is True
    (p,) = sent
    assert p["url"] == "https://ntfy.sh/rtw-abc123"
    assert p["data"] == b"heartbeat stale: 4.0 min"
    assert p["headers"] == {"Title": "Ride The Wave ALERT", "Priority": "high", "Tags": "warning"}
    assert p["timeout"] == 10


def test_push_non_2xx_is_false(posts):
    _, status = posts
    status["code"] = 429
    assert nt.push("t", "m", "topic") is False


def test_push_exception_is_false_and_does_not_raise(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("https://ntfy.sh/secret-topic unreachable")

    monkeypatch.setattr(nt.requests, "post", boom)
    assert nt.push("t", "m", "secret-topic") is False


def test_push_without_topic_sends_nothing(posts):
    sent, _ = posts
    assert nt.push("t", "m", None) is False
    assert nt.push("t", "m", "") is False
    assert sent == []


def test_non_ascii_title_is_encoded(posts):
    sent, _ = posts
    nt.push("Wave ↑ up", "mé", "topic")
    title = sent[0]["headers"]["Title"]
    assert title.startswith("=?UTF-8?B?") and title.endswith("?=")
    assert base64.b64decode(title[10:-2]).decode("utf-8") == "Wave ↑ up"
    assert sent[0]["data"] == "mé".encode()


def test_notify_with_topic_pushes(posts):
    sent, _ = posts
    nt.notify("Ride The Wave", "close report ready", True, topic="topic", priority="default", tags="memo")
    assert len(sent) == 1
    assert sent[0]["headers"]["Priority"] == "default" and sent[0]["headers"]["Tags"] == "memo"


def test_notify_without_topic_or_disabled_does_not_push(posts):
    sent, _ = posts
    nt.notify("Ride The Wave", "x")  # existing call shape still works
    nt.notify("Ride The Wave", "x", False, topic="topic")
    assert sent == []
