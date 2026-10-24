"""HTTP API tests with a fake pipeline (no models) and an in-memory fake DB."""
import asyncio
import importlib
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import attendance
import config
import database
import pipeline.engine as engine
from fakes import FakeDB, FakePipeline, frame, photos, utc, vec


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.install(monkeypatch)
    empty = database.rows_to_matrix([])
    database.embedding_cache.replace(*empty)
    database.dedup_index.replace(*empty)
    return fake


@pytest.fixture
def app_module(db, monkeypatch):
    """A freshly imported `main` wired to FakePipeline + FakeDB."""
    monkeypatch.setattr(engine, 'Pipeline', FakePipeline)
    import main
    return importlib.reload(main)


def _post_frame(client, data: bytes, **kw):
    return client.post('/api/camera/process-frame', files={'file': ('f.jpg', data, 'image/jpeg')}, **kw)


def _register(client, reg: str, ids):
    return client.post('/api/register/lms', data={'registration_number': reg}, files=photos(*ids))


# ─── Status / readiness ──────────────────────────────────────────────────────

def test_status_reports_loaded_students(app_module, db):
    db.seed('A', vec(0))
    db.seed('B', vec(1))
    db.seed('OLD', vec(2), model='w600k_mbf')  # made by the other model: ignored
    with TestClient(app_module.app) as client:
        s = client.get('/api/status').json()
        assert client.get('/healthz').json() == {'status': 'ok'}
    assert s['ready'] is True and s['db_ok'] is True
    assert s['registered_total'] == 2
    assert s['students_pending'] == 2
    assert s['ignored_other_model'] == 1
    assert s['model'] == 'w600k_r50'


def test_not_ready_returns_503_until_db_recovers(app_module, db):
    db.seed('A', vec(0))
    db.fail = True
    with TestClient(app_module.app) as client:
        assert client.get('/api/status').json()['ready'] is False
        assert _post_frame(client, frame(0)).status_code == 503
        assert _register(client, 'R1', [3] * 15).status_code == 503

        db.fail = False
        assert client.post('/api/cache/reload').status_code == 200
        assert client.get('/api/status').json()['ready'] is True
        assert _post_frame(client, frame(0)).json()['results'][0]['status'] == 'notified'


# ─── Attendance ──────────────────────────────────────────────────────────────

def test_frame_marks_once_and_returns_bboxes(app_module, db):
    db.seed('A', vec(0))
    with TestClient(app_module.app) as client:
        body = _post_frame(client, frame(0, 5, -1)).json()
        again = _post_frame(client, frame(0)).json()
    first, stranger, unusable = body['results']
    assert first['status'] == 'notified' and first['registration_number'] == 'A'
    assert first['bbox'] == [0, 0, 9, 9]
    assert stranger == {'status': 'unknown', 'bbox': [10, 0, 19, 9]}
    assert unusable['status'] == 'unknown'
    assert again['results'][0] == {'registration_number': 'A', 'status': 'already_marked',
                                   'bbox': [0, 0, 9, 9]}
    assert len(db.events) == 1
    assert db.events[0]['source'] == 'api'
    assert db.events[0]['lms_status'] == 'skipped'  # LMS_API_URL is empty in tests


def test_restart_does_not_renotify(app_module, db):
    db.seed('A', vec(0))
    db.insert_event('A', attendance.today(), utc(2026, 1, 1), 'api', 0.9, 'sent')
    with TestClient(app_module.app) as client:
        assert client.get('/api/status').json()['students_pending'] == 0
        assert _post_frame(client, frame(0)).json()['results'][0]['status'] == 'already_marked'
    assert len(db.events) == 1


def test_failed_recording_keeps_student_pending(app_module, db, monkeypatch):
    db.seed('A', vec(0))
    with TestClient(app_module.app) as client:
        real_insert = database.insert_event

        def broken(*a, **kw):
            raise database.StorageError('disk full (fake)')

        monkeypatch.setattr(database, 'insert_event', broken)
        assert _post_frame(client, frame(0)).json()['results'][0]['status'] == 'error'
        assert client.get('/api/status').json()['students_pending'] == 1  # claim undone

        monkeypatch.setattr(database, 'insert_event', real_insert)
        assert _post_frame(client, frame(0)).json()['results'][0]['status'] == 'notified'


def test_invalid_image_is_400(app_module, db):
    with TestClient(app_module.app) as client:
        assert _post_frame(client, b'definitely not an image').status_code == 400


def test_oversized_upload_is_413(app_module, db, monkeypatch):
    monkeypatch.setattr(app_module, 'MAX_UPLOAD_BYTES', 16)
    with TestClient(app_module.app) as client:
        assert _post_frame(client, frame(*range(20))).status_code == 413


def test_list_attendance(app_module, db):
    db.seed('A', vec(0))
    with TestClient(app_module.app) as client:
        _post_frame(client, frame(0))
        today = client.get('/api/attendance').json()
        other = client.get('/api/attendance', params={'date': '2000-01-01'}).json()
    assert today['count'] == 1 and today['events'][0]['registration_number'] == 'A'
    assert other == {'date': '2000-01-01', 'count': 0, 'events': []}


# ─── Auth ────────────────────────────────────────────────────────────────────

def test_api_key_rotation(app_module, db, monkeypatch):
    monkeypatch.setattr(config, 'API_KEYS', ['old-key', 'new-key'])
    with TestClient(app_module.app) as client:
        assert _post_frame(client, frame()).status_code == 401
        assert _post_frame(client, frame(), headers={'X-API-Key': 'wrong'}).status_code == 401
        assert _post_frame(client, frame(), headers={'X-API-Key': 'old-key'}).status_code == 200
        assert _post_frame(client, frame(), headers={'X-API-Key': 'new-key'}).status_code == 200
        assert client.get('/api/attendance').status_code == 401
        assert client.get('/api/status').status_code == 200  # health stays open


# ─── Registration ────────────────────────────────────────────────────────────

def test_register_then_recognise(app_module, db):
    with TestClient(app_module.app) as client:
        r = _register(client, ' R1 ', [3] * 15).json()
        assert r == {'success': True, 'status': 1, 'message': 'Face registered successfully'}
        assert 'R1' in db.embeddings  # whitespace stripped
        assert _post_frame(client, frame(3)).json()['results'][0]['registration_number'] == 'R1'


def test_register_rejects_duplicates(app_module, db, monkeypatch):
    with TestClient(app_module.app) as client:
        assert _register(client, 'R1', [3] * 15).json()['status'] == 1
        same_number = _register(client, 'R1', [4] * 15).json()
        same_face = _register(client, 'R2', [3] * 15).json()
        monkeypatch.setattr(attendance, 'REVEAL_DUPLICATE_MATCH', True)
        revealed = _register(client, 'R3', [3] * 15).json()
    assert same_number['status'] == 0 and 'already registered' in same_number['message']
    assert same_face['status'] == 0 and 'R1' not in same_face['message']  # no identity leak
    assert 'R1' in revealed['message']
    assert set(db.embeddings) == {'R1'}


@pytest.mark.parametrize('reg, expected', [
    ('   ', 'required'),
    ('x' * 101, 'at most 100'),
    ('AB\x07C', 'invalid characters'),
])
def test_register_validates_number(app_module, db, reg, expected):
    with TestClient(app_module.app) as client:
        r = _register(client, reg, [3] * 15).json()
    assert r['status'] == 0 and expected in r['message']
    assert not db.embeddings


def test_register_needs_exact_photo_count(app_module, db):
    with TestClient(app_module.app) as client:
        r = _register(client, 'R1', [3] * 14).json()
    assert r['status'] == 0 and 'Exactly 15' in r['message']


def test_register_rejects_inconsistent_photo_set(app_module, db):
    with TestClient(app_module.app) as client:
        r = _register(client, 'R1', [3] * 6 + [4] * 5 + [5] * 4).json()
    assert r['status'] == 0 and 'consistently show the same person' in r['message']


def test_register_majority_person_wins_mixed_set(app_module, db):
    # 8 photos of one person + 7 of another: the minority is dropped as outliers.
    with TestClient(app_module.app) as client:
        assert _register(client, 'R1', [3] * 8 + [4] * 7).json()['status'] == 1
        assert _post_frame(client, frame(3)).json()['results'][0]['status'] == 'notified'


def test_concurrent_registrations_of_same_face(db):
    """Two simultaneous registrations of one face: exactly one may succeed."""

    class SlowPipeline(FakePipeline):
        def embed_photos(self, blobs):
            import time
            time.sleep(0.05)  # both requests are past the "number exists?" check
            return super().embed_photos(blobs)

    svc = attendance.AttendanceService(SlowPipeline())
    svc.ready = True
    blobs = [json.dumps(3).encode()] * 15

    async def both():
        return await asyncio.gather(svc.register('R1', blobs), svc.register('R2', blobs))

    results = asyncio.run(both())
    assert sorted(r['status'] for r in results) == [0, 1]
    assert len(db.embeddings) == 1


# ─── Student management / day rollover ──────────────────────────────────────

def test_delete_student(app_module, db):
    db.seed('S/2024/1', vec(0))
    with TestClient(app_module.app) as client:
        assert client.delete('/api/students/S/2024/1').json() == {
            'deleted': True, 'registration_number': 'S/2024/1'}
        assert client.delete('/api/students/S/2024/1').status_code == 404
        s = client.get('/api/status').json()
        assert _post_frame(client, frame(0)).json()['results'][0]['status'] == 'unknown'
    assert s['registered_total'] == 0 and s['students_pending'] == 0


def test_new_day_reloads_everyone(db, monkeypatch):
    db.seed('A', vec(0))
    db.seed('B', vec(1))
    day1, day2 = date(2026, 3, 2), date(2026, 3, 3)
    db.insert_event('A', day1, utc(2026, 3, 2), 'api', 0.9, 'sent')

    monkeypatch.setattr(attendance, 'today', lambda: day1)
    svc = attendance.AttendanceService(FakePipeline())
    assert svc.startup_load() == 1             # only B pending on day 1
    assert 'A' not in database.embedding_cache

    monkeypatch.setattr(attendance, 'today', lambda: day2)
    assert svc.reload() == 2                   # everyone pending again on day 2
    assert svc.loaded_day == day2
