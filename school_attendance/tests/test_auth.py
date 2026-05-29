import asyncio

import pytest
from fastapi import HTTPException

import auth


def _run(coro):
    return asyncio.run(coro)


def test_no_key_set_allows_everything(monkeypatch):
    monkeypatch.setattr(auth, 'API_KEY', '')
    _run(auth.require_api_key(x_api_key=None))
    _run(auth.require_api_key(x_api_key='anything'))


def test_key_set_enforces_header(monkeypatch):
    monkeypatch.setattr(auth, 'API_KEY', 'secret')

    with pytest.raises(HTTPException) as exc:
        _run(auth.require_api_key(x_api_key=None))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException):
        _run(auth.require_api_key(x_api_key='wrong'))

    # Correct key passes (no exception).
    _run(auth.require_api_key(x_api_key='secret'))
