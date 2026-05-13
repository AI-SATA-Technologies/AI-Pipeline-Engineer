"""
Pytest integration tests for the School Attendance API.

Run:
    cd school_attendance
    pytest tests/ -v

Requirements:
    pip install pytest psycopg2-binary

Uses FastAPI's TestClient (no live server needed).
PostgreSQL must be running with the school_attendance database.
All test rows use roll_number prefixed with 'TEST_' and camera_id='pytest'
so they are cleaned up without touching real data.
"""
import sys
import os

import cv2
import numpy as np
import pytest
import psycopg2
import psycopg2.extras
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import get_db_connection

client = TestClient(app)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _blank_jpeg(width: int = 200, height: int = 200) -> bytes:
    """Random-noise JPEG — no detectable face."""
    img = np.random.randint(100, 200, (height, width, 3), dtype=np.uint8)
    _, buf = cv2.imencode('.jpg', img)
    return buf.tobytes()


def _db_exec(sql: str, params=()) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    cursor.close()
    conn.close()


def _db_query(sql: str, params=()) -> list:
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return rows


# ─── Session fixture: purge test rows before + after ──────────────────────────

@pytest.fixture(scope='session', autouse=True)
def cleanup_test_data():
    _purge()
    yield
    _purge()


def _purge():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Delete attendance rows for TEST_ students
    cursor.execute(
        "DELETE FROM attendance WHERE student_id IN "
        "(SELECT id FROM students WHERE roll_number LIKE 'TEST_%')"
    )
    # Delete attendance rows tagged with pytest camera
    cursor.execute("DELETE FROM attendance WHERE camera_id = 'pytest'")
    # Delete embeddings for TEST_ students
    cursor.execute(
        "DELETE FROM embeddings WHERE student_id IN "
        "(SELECT id FROM students WHERE roll_number LIKE 'TEST_%')"
    )
    cursor.execute("DELETE FROM students WHERE roll_number LIKE 'TEST_%'")
    conn.commit()
    cursor.close()
    conn.close()


# ─── Status ───────────────────────────────────────────────────────────────────

class TestStatus:
    def test_returns_running(self):
        r = client.get('/api/status')
        assert r.status_code == 200
        assert r.json()['status'] == 'running'

    def test_has_required_fields(self):
        body = client.get('/api/status').json()
        assert 'mode' in body
        assert 'liveness_enabled' in body
        assert 'students_in_db' in body
        assert isinstance(body['students_in_db'], int)


# ─── Students ─────────────────────────────────────────────────────────────────

class TestStudents:
    def test_list_returns_list(self):
        r = client.get('/api/students')
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_filter_nonexistent_class(self):
        r = client.get('/api/students?class_name=__none__')
        assert r.status_code == 200
        assert r.json() == []

    def test_delete_nonexistent_returns_404(self):
        r = client.delete('/api/students/999999999')
        assert r.status_code == 404

    def test_delete_student(self):
        _db_exec(
            "INSERT INTO students (name, roll_number, class_name) VALUES (%s,%s,%s)",
            ('Del Test', 'TEST_DEL_001', '10A'),
        )
        sid = _db_query("SELECT id FROM students WHERE roll_number='TEST_DEL_001'")[0]['id']
        r = client.delete(f'/api/students/{sid}')
        assert r.status_code == 200
        assert r.json()['success'] is True
        row = _db_query("SELECT is_active FROM students WHERE id=%s", (sid,))
        assert row[0]['is_active'] is False


# ─── Register ─────────────────────────────────────────────────────────────────

class TestRegister:
    def test_no_faces_fails_gracefully(self):
        blank = _blank_jpeg()
        files = [('photos', ('p.jpg', blank, 'image/jpeg'))] * 6
        r = client.post(
            '/api/register',
            data={'name': 'No Face', 'roll_number': 'TEST_REG_NF', 'class_name': '10A'},
            files=files,
        )
        assert r.status_code == 200
        body = r.json()
        assert body['success'] is False
        assert 'samples' in body['error'].lower() or 'face' in body['error'].lower()

    def test_duplicate_roll_number(self):
        _db_exec(
            "INSERT INTO students (name, roll_number, class_name) VALUES (%s,%s,%s)",
            ('Dup Student', 'TEST_REG_DUP', '10A'),
        )
        blank = _blank_jpeg()
        r = client.post(
            '/api/register',
            data={'name': 'Dup Student', 'roll_number': 'TEST_REG_DUP', 'class_name': '10A'},
            files=[('photos', ('p.jpg', blank, 'image/jpeg'))],
        )
        assert r.status_code == 200
        assert r.json()['success'] is False
        assert 'already registered' in r.json()['error'].lower()


# ─── Process frame ────────────────────────────────────────────────────────────

class TestProcessFrame:
    def test_no_face_detected(self):
        r = client.post(
            '/api/camera/process-frame',
            data={'camera_id': 'pytest'},
            files={'file': ('f.jpg', _blank_jpeg(), 'image/jpeg')},
        )
        assert r.status_code == 200
        body = r.json()
        assert body['faces_detected'] == 0
        assert body['results'] == []

    def test_invalid_image_data(self):
        r = client.post(
            '/api/camera/process-frame',
            data={'camera_id': 'pytest'},
            files={'file': ('f.jpg', b'not_an_image', 'image/jpeg')},
        )
        assert r.status_code == 400

    def test_default_camera_id_accepted(self):
        r = client.post(
            '/api/camera/process-frame',
            files={'file': ('f.jpg', _blank_jpeg(), 'image/jpeg')},
        )
        assert r.status_code == 200


# ─── Attendance ───────────────────────────────────────────────────────────────

@pytest.fixture(scope='class')
def seeded_attendance():
    from datetime import date
    _db_exec(
        "INSERT INTO students (name, roll_number, class_name, section) VALUES (%s,%s,%s,%s)",
        ('Att Test', 'TEST_ATT_001', '10B', 'B'),
    )
    sid = _db_query("SELECT id FROM students WHERE roll_number='TEST_ATT_001'")[0]['id']
    _db_exec(
        "INSERT INTO attendance (student_id, date, confidence, camera_id) VALUES (%s,%s,%s,%s)",
        (sid, date.today(), 0.92, 'pytest'),
    )
    yield {'student_id': sid, 'roll_number': 'TEST_ATT_001', 'class_name': '10B'}


class TestAttendance:
    def test_returns_list(self):
        r = client.get('/api/attendance')
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_seeded_record_appears(self, seeded_attendance):
        r = client.get('/api/attendance')
        rolls = [row['roll_number'] for row in r.json()]
        assert seeded_attendance['roll_number'] in rolls

    def test_filter_by_date_today(self):
        from datetime import date
        r = client.get(f'/api/attendance?date_str={date.today()}')
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_filter_by_class(self, seeded_attendance):
        r = client.get('/api/attendance?class_name=10B')
        assert r.status_code == 200
        for row in r.json():
            assert row['class_name'] == '10B'

    def test_filter_nonexistent_class(self):
        r = client.get('/api/attendance?class_name=__none__')
        assert r.status_code == 200
        assert r.json() == []

    def test_csv_export(self, seeded_attendance):
        from datetime import date
        r = client.get(f'/api/attendance/export?date_str={date.today()}')
        assert r.status_code == 200
        assert 'text/csv' in r.headers['content-type']
        assert 'name' in r.text.lower()

    def test_row_has_expected_fields(self, seeded_attendance):
        rows = client.get('/api/attendance').json()
        if rows:
            required = {'name', 'roll_number', 'class_name', 'date', 'marked_at', 'confidence'}
            assert required.issubset(rows[0].keys())


# ─── Statistics ───────────────────────────────────────────────────────────────

class TestStats:
    def test_today_valid_shape(self):
        r = client.get('/api/stats')
        assert r.status_code == 200
        body = r.json()
        for key in ('date', 'total_students', 'present', 'absent', 'attendance_rate', 'by_class'):
            assert key in body

    def test_present_plus_absent_equals_total(self, seeded_attendance):
        body = client.get('/api/stats').json()
        assert body['present'] + body['absent'] == body['total_students']

    def test_rate_in_range(self):
        body = client.get('/api/stats').json()
        assert 0.0 <= body['attendance_rate'] <= 100.0

    def test_by_class_is_list(self):
        assert isinstance(client.get('/api/stats').json()['by_class'], list)

    def test_filter_by_class(self, seeded_attendance):
        body = client.get('/api/stats?class_name=10B').json()
        assert body['total_students'] >= 1
        assert body['present'] >= 1

    def test_old_date_has_zero_present(self):
        body = client.get('/api/stats?date_str=2020-01-01').json()
        assert body['date'] == '2020-01-01'
        assert body['present'] == 0

    def test_zero_students_gives_zero_rate(self):
        body = client.get('/api/stats?class_name=__none__&date_str=2020-01-01').json()
        assert body['attendance_rate'] == 0.0
