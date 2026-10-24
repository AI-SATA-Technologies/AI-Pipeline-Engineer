"""PostgreSQL access + the in-memory vector stores.

PostgreSQL is the source of truth. Two in-memory stores serve every match with
zero DB I/O (both stored vectors and queries are L2-normalised, so cosine
similarity is a dot product):
    embedding_cache — students not yet marked today (evicted on detection)
    dedup_index     — every registered face (never evicted; duplicate checks)
Loading/refreshing them is orchestrated by attendance.AttendanceService.
"""
import glob
import logging
import os
import threading
from contextlib import contextmanager
from datetime import date, datetime

import numpy as np
import psycopg2
from psycopg2 import pool

from config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME,
    DB_POOL_MIN, DB_POOL_MAX, SIMILARITY_THRESHOLD, DEDUP_THRESHOLD,
)

logger = logging.getLogger('attendance.db')

EMBED_DIM = 512
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')


class StorageError(RuntimeError):
    """Raised when the database is unavailable or a query fails."""


# ─── Connection pool ────────────────────────────────────────────────────────

_pool: pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = pool.ThreadedConnectionPool(
                        DB_POOL_MIN, DB_POOL_MAX,
                        host=DB_HOST, port=DB_PORT,
                        user=DB_USER, password=DB_PASS, dbname=DB_NAME,
                        connect_timeout=5,
                    )
                    logger.info('PostgreSQL pool ready (%s-%s connections)', DB_POOL_MIN, DB_POOL_MAX)
                except psycopg2.Error as exc:
                    raise StorageError(f'cannot connect to PostgreSQL: {exc}'.strip()) from exc
    return _pool


@contextmanager
def get_conn():
    """Borrow a pooled connection.

    Rolls back on error and wraps every DB error as StorageError. A connection
    that died (server restart, network drop) is closed instead of being returned
    to the pool, so the next request gets a fresh one.
    """
    pool_ = _get_pool()
    try:
        conn = pool_.getconn()
    except psycopg2.Error as exc:  # includes PoolError (pool exhausted)
        raise StorageError(f'no database connection available: {exc}'.strip()) from exc

    broken = False
    try:
        yield conn
    except BaseException as exc:
        if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            broken = True
        if not conn.closed:
            try:
                conn.rollback()
            except psycopg2.Error:
                broken = True
        if isinstance(exc, psycopg2.Error):
            raise StorageError(str(exc).strip()) from exc
        raise
    finally:
        pool_.putconn(conn, close=broken or bool(conn.closed))


def ping() -> bool:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')
            return True
    except StorageError:
        return False


def apply_migrations() -> list[str]:
    """Apply migrations/*.sql in order (each is idempotent). Returns file names."""
    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, '*.sql')))
    with get_conn() as conn, conn.cursor() as cur:
        for path in files:
            with open(path, encoding='utf-8') as f:
                cur.execute(f.read())
        conn.commit()
    return [os.path.basename(p) for p in files]


# ─── Embeddings ─────────────────────────────────────────────────────────────

def fetch_embeddings(model: str) -> list[tuple[str, memoryview]]:
    """All (registration_number, vector) rows produced by `model`."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            'SELECT registration_number, vector FROM student_face_embeddings WHERE model = %s',
            (model,),
        )
        return cur.fetchall()


def count_other_models(model: str) -> int:
    """Embeddings made by a different model (unusable in the current MODE)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM student_face_embeddings WHERE model <> %s', (model,))
        return cur.fetchone()[0]


def insert_embedding(registration_number: str, embedding: np.ndarray,
                     sample_count: int, model: str) -> bool:
    """Persist a new student's embedding. Returns False if the number is taken.

    Only the 512-dim float32 vector + registration number are written; source
    images are processed in memory and never stored. Never overwrites an
    existing student (delete first to re-register).
    """
    vec_bytes = embedding.astype(np.float32).tobytes()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            '''INSERT INTO student_face_embeddings (registration_number, sample_count, vector, model)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (registration_number) DO NOTHING
               RETURNING registration_number''',
            (registration_number, sample_count, psycopg2.Binary(vec_bytes), model),
        )
        inserted = cur.fetchone() is not None
        conn.commit()
    return inserted


def registration_exists(registration_number: str) -> bool:
    """True if a student is already registered under this registration number."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            'SELECT 1 FROM student_face_embeddings WHERE registration_number = %s',
            (registration_number,),
        )
        return cur.fetchone() is not None


def delete_embedding(registration_number: str) -> bool:
    """Delete a student's face data. Attendance history is kept. Returns True if deleted."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            'DELETE FROM student_face_embeddings WHERE registration_number = %s',
            (registration_number,),
        )
        deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def rows_to_matrix(rows) -> tuple[list[str], np.ndarray]:
    ids, vecs = [], []
    for reg, vec_bytes in rows:
        vec = np.frombuffer(bytes(vec_bytes), dtype=np.float32)
        if vec.shape != (EMBED_DIM,):
            logger.warning('skipping malformed embedding for %s (%d values)', reg, vec.size)
            continue
        ids.append(reg)
        vecs.append(vec.copy())
    matrix = (
        np.stack(vecs).astype(np.float32) if vecs
        else np.empty((0, EMBED_DIM), dtype=np.float32)
    )
    return ids, matrix


# ─── Attendance events (also the LMS outbox) ────────────────────────────────

def fetch_marked_on(day: date) -> set[str]:
    """Registration numbers that already have an attendance event on `day`."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            'SELECT registration_number FROM attendance_events WHERE attendance_date = %s',
            (day,),
        )
        return {r[0] for r in cur.fetchall()}


def insert_event(registration_number: str, day: date, detected_at: datetime,
                 source: str, score: float | None, lms_status: str) -> int | None:
    """Record attendance. Returns the event id, or None if already marked that day."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            '''INSERT INTO attendance_events
                   (registration_number, attendance_date, detected_at, source, score, lms_status)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (registration_number, attendance_date) DO NOTHING
               RETURNING id''',
            (registration_number, day, detected_at, source, score, lms_status),
        )
        row = cur.fetchone()
        conn.commit()
    return row[0] if row else None


def fetch_due_events(limit: int = 50) -> list[tuple[int, str, datetime, int]]:
    """Pending events whose next delivery attempt is due: (id, reg, detected_at, attempts)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            '''SELECT id, registration_number, detected_at, lms_attempts
               FROM attendance_events
               WHERE lms_status = 'pending' AND next_attempt_at <= NOW()
               ORDER BY next_attempt_at, id
               LIMIT %s''',
            (limit,),
        )
        return cur.fetchall()


def mark_event_sent(event_id: int, attempts: int) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            '''UPDATE attendance_events
               SET lms_status = 'sent', lms_attempts = %s, lms_last_error = NULL
               WHERE id = %s''',
            (attempts, event_id),
        )
        conn.commit()


def mark_event_retry(event_id: int, attempts: int, error: str,
                     retry_in_seconds: float, give_up: bool) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            '''UPDATE attendance_events
               SET lms_status = %s, lms_attempts = %s, lms_last_error = %s,
                   next_attempt_at = NOW() + make_interval(secs => %s)
               WHERE id = %s''',
            ('failed' if give_up else 'pending', attempts, error[:500], retry_in_seconds, event_id),
        )
        conn.commit()


def count_pending() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM attendance_events WHERE lms_status = 'pending'")
        return cur.fetchone()[0]


def list_events(day: date) -> list[dict]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            '''SELECT registration_number, detected_at, source, score,
                      lms_status, lms_attempts, lms_last_error
               FROM attendance_events WHERE attendance_date = %s ORDER BY detected_at''',
            (day,),
        )
        rows = cur.fetchall()
    return [
        {
            'registration_number': r[0],
            'detected_at': r[1].isoformat(timespec='seconds'),
            'source': r[2],
            'score': round(r[3], 4) if r[3] is not None else None,
            'lms_status': r[4],
            'lms_attempts': r[5],
            'lms_last_error': r[6],
        }
        for r in rows
    ]


# ─── In-memory vector stores ──────────────────────────────────────────────────

class _VectorStore:
    """Thread-safe in-memory (N, 512) float32 store keyed by registration_number."""

    def __init__(self):
        self._ids: list[str] = []
        self._matrix = np.empty((0, EMBED_DIM), dtype=np.float32)
        self._lock = threading.Lock()

    def replace(self, ids: list[str], matrix: np.ndarray) -> None:
        """Swap in a freshly loaded set of embeddings."""
        with self._lock:
            self._ids, self._matrix = list(ids), matrix

    def add(self, registration_number: str, embedding: np.ndarray) -> None:
        """Insert or update an L2-normalised embedding."""
        vec = embedding.astype(np.float32).reshape(1, EMBED_DIM)
        with self._lock:
            if registration_number in self._ids:
                self._matrix[self._ids.index(registration_number)] = vec[0]
            else:
                self._ids.append(registration_number)
                self._matrix = np.vstack([self._matrix, vec]) if self._matrix.shape[0] else vec

    def remove(self, registration_number: str) -> bool:
        with self._lock:
            if registration_number not in self._ids:
                return False
            idx = self._ids.index(registration_number)
            self._ids.pop(idx)
            self._matrix = np.delete(self._matrix, idx, axis=0)
            return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)

    def __contains__(self, registration_number: str) -> bool:
        with self._lock:
            return registration_number in self._ids


class EmbeddingCache(_VectorStore):
    """Attendance cache: students not yet marked today. Students are evicted on
    detection (detect-once), so each is reported to the LMS at most once a day."""

    def claim(self, query: np.ndarray,
              threshold: float = SIMILARITY_THRESHOLD) -> tuple[str, float, np.ndarray] | None:
        """Atomically find the best match >= threshold and evict it.

        Returns (registration_number, score, embedding) if a student was claimed,
        else None. Matching and eviction under one lock guarantee concurrent
        frames cannot both claim (and double-notify) the same student. The
        embedding is returned so the claim can be undone if recording it fails.
        """
        q = query.astype(np.float32)
        with self._lock:
            if self._matrix.shape[0] == 0:
                return None
            scores = self._matrix @ q
            best_idx = int(np.argmax(scores))
            score = float(scores[best_idx])
            if score < threshold:
                return None
            reg = self._ids.pop(best_idx)
            vec = self._matrix[best_idx].copy()
            self._matrix = np.delete(self._matrix, best_idx, axis=0)
            return reg, score, vec


class DedupIndex(_VectorStore):
    """Permanent index of every registered face (never evicted). Used to reject
    duplicate-face registrations without re-scanning the database each time."""

    def find_match(self, embedding: np.ndarray,
                   threshold: float = DEDUP_THRESHOLD) -> tuple[str | None, float]:
        """Return (registration_number, score) of the best match >= threshold,
        or (None, score) if no stored face matches."""
        q = embedding.astype(np.float32)
        with self._lock:
            if self._matrix.shape[0] == 0:
                return None, 0.0
            scores = self._matrix @ q
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])
            best_id = self._ids[best_idx]
        return (best_id, best_score) if best_score >= threshold else (None, best_score)


embedding_cache = EmbeddingCache()
dedup_index = DedupIndex()
