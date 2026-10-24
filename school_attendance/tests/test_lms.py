"""LMS outbox: delivery, retries with backoff, giving up, payload shape."""
import asyncio
import json

import httpx
import pytest

import lms
from fakes import FakeDB, utc


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.install(monkeypatch)
    monkeypatch.setattr(lms, 'LMS_API_URL', 'http://lms.test/attendance')
    return fake


def _outbox(responses: list):
    """Outbox whose HTTP client replies with `responses` in order
    (an int status code, or an exception instance to raise)."""
    sent = []

    def handler(request: httpx.Request):
        sent.append(json.loads(request.content))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return lms.LmsOutbox(client=client), sent


def test_retry_delay_backs_off_and_caps():
    assert [lms.retry_delay(n) for n in (1, 2, 3, 4)] == [5, 10, 20, 40]
    assert lms.retry_delay(50) == 600


def test_failed_delivery_is_retried_then_sent(db):
    db.insert_event('A', utc(2026, 3, 2).date(), utc(2026, 3, 2), 'api', 0.9, 'pending')
    outbox, sent = _outbox([500, 200])

    asyncio.run(outbox.drain_once())
    e = db.events[0]
    assert e['lms_status'] == 'pending' and e['lms_attempts'] == 1
    assert e['lms_last_error'] == 'HTTP 500'

    asyncio.run(outbox.drain_once())
    assert e['lms_status'] == 'sent' and e['lms_attempts'] == 2
    assert sent[-1] == {'registration_number': 'A', 'detected_at': '2026-03-02T08:00:00+00:00'}


def test_payload_time_is_always_utc(db):
    from datetime import datetime, timedelta, timezone
    pkt = timezone(timedelta(hours=5))  # what Postgres returns in a +05:00 session
    detected = datetime(2026, 3, 2, 13, 0, tzinfo=pkt)
    db.insert_event('A', detected.date(), detected, 'api', 0.9, 'pending')
    outbox, sent = _outbox([200])
    asyncio.run(outbox.drain_once())
    assert sent[0]['detected_at'] == '2026-03-02T08:00:00+00:00'


def test_network_errors_are_retried(db):
    db.insert_event('A', utc(2026, 3, 2).date(), utc(2026, 3, 2), 'api', 0.9, 'pending')
    outbox, _ = _outbox([httpx.ConnectError('refused')])
    asyncio.run(outbox.drain_once())
    assert db.events[0]['lms_status'] == 'pending'
    assert 'ConnectError' in db.events[0]['lms_last_error']


def test_gives_up_after_max_attempts(db, monkeypatch):
    monkeypatch.setattr(lms, 'LMS_MAX_ATTEMPTS', 2)
    db.insert_event('A', utc(2026, 3, 2).date(), utc(2026, 3, 2), 'api', 0.9, 'pending')
    outbox, _ = _outbox([503, 503])
    asyncio.run(outbox.drain_once())
    asyncio.run(outbox.drain_once())
    assert db.events[0]['lms_status'] == 'failed' and db.events[0]['lms_attempts'] == 2
