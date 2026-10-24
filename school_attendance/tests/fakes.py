"""Test doubles: an in-memory stand-in for the database module's queries and a
pipeline that needs no ONNX models.

Fake "images" are JSON: a frame is a list of face ids (each id i becomes the
unit vector e_i; -1 = a face with no usable embedding), and a registration
photo is a single face id.
"""
import json
from datetime import date, datetime

import numpy as np

import database
from pipeline.engine import InvalidImage

MODEL = 'w600k_r50'


def vec(i: int) -> np.ndarray:
    v = np.zeros(database.EMBED_DIM, dtype=np.float32)
    v[i] = 1.0
    return v


def frame(*ids: int) -> bytes:
    return json.dumps(list(ids)).encode()


def photos(*ids: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [('photos[]', (f'p{n}.jpg', json.dumps(i).encode(), 'image/jpeg')) for n, i in enumerate(ids)]


class FakePipeline:
    model_name = MODEL

    def __init__(self, *args, **kwargs):
        pass

    def embed_frame(self, data: bytes):
        try:
            ids = json.loads(data)
        except ValueError:
            raise InvalidImage('invalid image data')
        return [([10 * n, 0, 10 * n + 9, 9], None if i < 0 else vec(i)) for n, i in enumerate(ids)]

    def embed_image(self, img):
        return []

    def embed_photos(self, blobs):
        out = []
        for b in blobs:
            i = json.loads(b)
            if i >= 0:
                out.append(vec(i))
        return out


class FakeDB:
    """Implements the query functions of `database` against plain dicts."""

    def __init__(self):
        self.embeddings: dict[str, tuple[bytes, str]] = {}
        self.events: list[dict] = []
        self.fail = False  # make every query raise StorageError

    def _check(self):
        if self.fail:
            raise database.StorageError('database is down (fake)')

    # registration
    def seed(self, reg: str, v: np.ndarray, model: str = MODEL):
        self.embeddings[reg] = (v.astype(np.float32).tobytes(), model)

    def apply_migrations(self):
        self._check()
        return ['001_init.sql', '002_attendance.sql']

    def ping(self):
        return not self.fail

    def fetch_embeddings(self, model):
        self._check()
        return [(r, b) for r, (b, m) in self.embeddings.items() if m == model]

    def count_other_models(self, model):
        self._check()
        return sum(1 for _, m in self.embeddings.values() if m != model)

    def insert_embedding(self, reg, emb, sample_count, model):
        self._check()
        if reg in self.embeddings:
            return False
        self.seed(reg, emb, model)
        return True

    def registration_exists(self, reg):
        self._check()
        return reg in self.embeddings

    def delete_embedding(self, reg):
        self._check()
        return self.embeddings.pop(reg, None) is not None

    # events
    def fetch_marked_on(self, day: date):
        self._check()
        return {e['registration_number'] for e in self.events if e['attendance_date'] == day}

    def insert_event(self, reg, day, detected_at, source, score, lms_status):
        self._check()
        if any(e['registration_number'] == reg and e['attendance_date'] == day for e in self.events):
            return None
        event = {
            'id': len(self.events) + 1, 'registration_number': reg, 'attendance_date': day,
            'detected_at': detected_at, 'source': source, 'score': score,
            'lms_status': lms_status, 'lms_attempts': 0, 'lms_last_error': None,
        }
        self.events.append(event)
        return event['id']

    def fetch_due_events(self, limit=50):
        self._check()
        due = [e for e in self.events if e['lms_status'] == 'pending']
        return [(e['id'], e['registration_number'], e['detected_at'], e['lms_attempts']) for e in due[:limit]]

    def mark_event_sent(self, event_id, attempts):
        e = self.events[event_id - 1]
        e.update(lms_status='sent', lms_attempts=attempts, lms_last_error=None)

    def mark_event_retry(self, event_id, attempts, error, retry_in_seconds, give_up):
        e = self.events[event_id - 1]
        e.update(lms_status='failed' if give_up else 'pending', lms_attempts=attempts,
                 lms_last_error=error, retry_in=retry_in_seconds)

    def count_pending(self):
        self._check()
        return sum(1 for e in self.events if e['lms_status'] == 'pending')

    def list_events(self, day):
        self._check()
        return [
            {'registration_number': e['registration_number'],
             'detected_at': e['detected_at'].isoformat(timespec='seconds'),
             'source': e['source'], 'lms_status': e['lms_status']}
            for e in self.events if e['attendance_date'] == day
        ]

    def install(self, monkeypatch):
        for name in ('apply_migrations', 'ping', 'fetch_embeddings', 'count_other_models',
                     'insert_embedding', 'registration_exists', 'delete_embedding',
                     'fetch_marked_on', 'insert_event', 'fetch_due_events', 'mark_event_sent',
                     'mark_event_retry', 'count_pending', 'list_events'):
            monkeypatch.setattr(database, name, getattr(self, name))


def utc(y, m, d, hh=8) -> datetime:
    from datetime import UTC
    return datetime(y, m, d, hh, tzinfo=UTC)
