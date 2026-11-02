from email.message import Message

import pytest

from radar import http


def _resp(status: int) -> http.Response:
    return http.Response("https://x.test/", status, Message(), b"")


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda s: None)


def _serve(monkeypatch, outcomes):
    calls = []

    def fake_get(url, headers=None, timeout=30):
        calls.append(url)
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return _resp(out)
    monkeypatch.setattr(http, "get", fake_get)
    return calls


def test_retries_transient_network_error_then_succeeds(monkeypatch, no_sleep):
    calls = _serve(monkeypatch, [http.HTTPError("TimeoutError"), 200])
    assert http.Fetcher({"user_agent": "t"}).get("https://x.test/").status_code == 200
    assert len(calls) == 2


def test_retries_bad_gateway_and_rate_limit(monkeypatch, no_sleep):
    _serve(monkeypatch, [502, 429, 200])
    assert http.Fetcher({"user_agent": "t"}).get("https://x.test/").status_code == 200


def test_gives_up_after_retries(monkeypatch, no_sleep):
    calls = _serve(monkeypatch, [http.HTTPError("reset")] * 3)
    with pytest.raises(http.HTTPError):
        http.Fetcher({"user_agent": "t"}).get("https://x.test/")
    assert len(calls) == 3


def test_client_errors_are_not_retried(monkeypatch, no_sleep):
    calls = _serve(monkeypatch, [404])
    assert http.Fetcher({"user_agent": "t"}).get("https://x.test/").status_code == 404
    assert len(calls) == 1
