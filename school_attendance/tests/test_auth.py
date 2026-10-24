import asyncio

import pytest
from fastapi import HTTPException

import auth
import config


def _run(coro):
    return asyncio.run(coro)


def test_no_key_set_allows_everything(monkeypatch):
    monkeypatch.setattr(config, 'API_KEYS', [])
    _run(auth.require_api_key(x_api_key=None))
    _run(auth.require_api_key(x_api_key='anything'))


def test_key_set_enforces_header(monkeypatch):
    monkeypatch.setattr(config, 'API_KEYS', ['secret'])

    with pytest.raises(HTTPException) as exc:
        _run(auth.require_api_key(x_api_key=None))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException):
        _run(auth.require_api_key(x_api_key='wrong'))

    # Correct key passes (no exception).
    _run(auth.require_api_key(x_api_key='secret'))


def test_any_configured_key_is_accepted(monkeypatch):
    monkeypatch.setattr(config, 'API_KEYS', ['old', 'new'])
    _run(auth.require_api_key(x_api_key='old'))
    _run(auth.require_api_key(x_api_key='new'))
    with pytest.raises(HTTPException):
        _run(auth.require_api_key(x_api_key='newer'))
