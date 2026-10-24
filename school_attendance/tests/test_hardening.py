"""Security/robustness units: body-size limit, decompression bombs, DB error
handling, config validation, camera URL handling, registration helpers."""
import cv2
import numpy as np
import psycopg2
import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

import attendance
import config
import database
from camera_worker import mask_source, normalize_source
from limits import BodySizeLimitMiddleware
from pipeline.engine import InvalidImage, best_registration_face, decode_image
from pipeline.scrfd import Face


# ─── Request body limit ──────────────────────────────────────────────────────

def _limited_app(max_bytes: int):
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)

    @app.post('/up')
    async def up(file: UploadFile = File(...)):
        return {'size': len(await file.read())}

    return app


def test_body_limit_by_content_length():
    client = TestClient(_limited_app(200))
    assert client.post('/up', files={'file': ('a', b'x' * 10)}).status_code == 200
    assert client.post('/up', files={'file': ('a', b'x' * 500)}).status_code == 413


def test_body_limit_when_streamed_without_content_length():
    def chunks():
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a"\r\n\r\n'
        for _ in range(10):
            yield b'x' * 100
        yield b'\r\n--b--\r\n'

    client = TestClient(_limited_app(200))
    r = client.post('/up', content=chunks(), headers={'content-type': 'multipart/form-data; boundary=b'})
    assert r.status_code == 413


# ─── Image decoding ──────────────────────────────────────────────────────────

def test_decompression_bomb_is_rejected():
    assert config.MAX_IMAGE_PIXELS == 40_000_000
    side = 7000  # 49 MP: a small PNG that would decode to ~147 MB
    ok, png = cv2.imencode('.png', np.zeros((side, side), np.uint8))
    assert ok and len(png) < 1_000_000
    with pytest.raises(InvalidImage):
        decode_image(png.tobytes())


def test_garbage_is_invalid_image():
    with pytest.raises(InvalidImage):
        decode_image(b'not an image')


def test_registration_face_is_largest_confident_one():
    small = Face(np.array([0, 0, 80, 80.0]), None, 0.99)
    big = Face(np.array([100, 100, 300, 300.0]), None, 0.70)
    tiny = Face(np.array([0, 0, 30, 30.0]), None, 0.99)       # under REG_MIN_FACE_PX
    unsure = Face(np.array([0, 0, 400, 400.0]), None, 0.40)   # under REG_MIN_DET_SCORE
    assert best_registration_face([small, big, tiny, unsure]) is big
    assert best_registration_face([tiny, unsure]) is None


def test_build_template_normalises():
    v = np.zeros(512, np.float32)
    v[0] = 1
    t, kept = attendance.build_template([v, v, v])
    assert kept == 3 and np.isclose(np.linalg.norm(t), 1.0)
    assert attendance.build_template([]) == (None, 0)


# ─── Database connection handling ────────────────────────────────────────────

class _Conn:
    def __init__(self, rollback_error=None):
        self.closed = 0
        self.rollback_error = rollback_error
        self.rolled_back = False

    def rollback(self):
        if self.rollback_error:
            self.closed = 2
            raise self.rollback_error
        self.rolled_back = True


class _Pool:
    def __init__(self, conn):
        self.conn = conn
        self.returned = None

    def getconn(self):
        return self.conn

    def putconn(self, conn, close=False):
        self.returned = (conn, close)


def test_dead_connection_becomes_storage_error_and_is_discarded(monkeypatch):
    pool = _Pool(_Conn(rollback_error=psycopg2.InterfaceError('connection already closed')))
    monkeypatch.setattr(database, '_get_pool', lambda: pool)
    with pytest.raises(database.StorageError):
        with database.get_conn():
            raise psycopg2.OperationalError('server closed the connection unexpectedly')
    assert pool.returned[1] is True  # closed, not reused


def test_non_db_error_rolls_back_and_keeps_connection(monkeypatch):
    conn = _Conn()
    pool = _Pool(conn)
    monkeypatch.setattr(database, '_get_pool', lambda: pool)
    with pytest.raises(ValueError):
        with database.get_conn():
            raise ValueError('bug in caller')
    assert conn.rolled_back and pool.returned == (conn, False)


# ─── Config validation ───────────────────────────────────────────────────────

def test_config_normalises_and_validates():
    assert config.Settings(MODE=' Heavy ').MODE == 'heavy'
    with pytest.raises(ValueError):
        config.Settings(MODE='medium')
    with pytest.raises(ValueError):
        config.Settings(REQUIRED_UPLOAD=5, REQUIRED_VALID=7)
    with pytest.raises(ValueError):
        config.Settings(ATTENDANCE_TZ='Mars/Olympus')
    assert config.Settings(ATTENDANCE_TZ='Asia/Karachi').ATTENDANCE_TZ == 'Asia/Karachi'


# ─── Camera source handling ──────────────────────────────────────────────────

@pytest.mark.parametrize('raw, expected', [
    ('0', 0),
    ('  2  ', 2),
    ('0rtsp://me@mail.com:p@ss!@10.0.0.5:554/Streaming/Channels/101',
     'rtsp://me%40mail.com:p%40ss%21@10.0.0.5:554/Streaming/Channels/101'),
    ('rtsp://admin:Pass123@10.0.0.5:554/Streaming/Channels/101',
     'rtsp://admin:Pass123@10.0.0.5:554/Streaming/Channels/101'),
    ('rtsp://me%40mail.com:abc@10.0.0.5/x', 'rtsp://me%40mail.com:abc@10.0.0.5/x'),  # already encoded
    ('rtsp://10.0.0.5:554/Streaming/Channels/101', 'rtsp://10.0.0.5:554/Streaming/Channels/101'),
    ('C:/videos/test.mp4', 'C:/videos/test.mp4'),
])
def test_normalize_source(raw, expected):
    assert normalize_source(raw) == expected


def test_mask_source_hides_credentials():
    assert mask_source('rtsp://admin:secret@10.0.0.5:554/x') == 'rtsp://***:***@10.0.0.5:554/x'
    assert mask_source(0) == 'webcam 0'
