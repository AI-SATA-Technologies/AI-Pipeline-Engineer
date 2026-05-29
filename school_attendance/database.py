import logging
import threading
from contextlib import contextmanager

import numpy as np
import psycopg2
from psycopg2 import pool

from config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME,
    DB_POOL_MIN, DB_POOL_MAX, SIMILARITY_THRESHOLD,
)

logger = logging.getLogger('attendance.db')

EMBED_DIM = 512


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
                    )
                    logger.info('PostgreSQL pool ready (%s-%s connections)', DB_POOL_MIN, DB_POOL_MAX)
                except psycopg2.Error as exc:
                    raise StorageError(f'cannot connect to PostgreSQL: {exc}') from exc
    return _pool


@contextmanager
def get_conn():
    """Borrow a pooled connection; rolls back and wraps DB errors as StorageError."""
    pool_ = _get_pool()
    conn = None
    try:
        conn = pool_.getconn()
        yield conn
    except psycopg2.Error as exc:
        if conn is not None:
            conn.rollback()
        raise StorageError(str(exc)) from exc
    finally:
        if conn is not None:
            pool_.putconn(conn)


# ─── Embedding (de)serialization ────────────────────────────────────────────

def _fetch_all_embeddings() -> list[tuple[str, memoryview]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT registration_number, vector FROM student_face_embeddings')
        rows = cur.fetchall()
        cur.close()
    return rows


def _rows_to_matrix(rows) -> tuple[list[str], np.ndarray]:
    ids, vecs = [], []
    for reg, vec_bytes in rows:
        ids.append(reg)
        vecs.append(np.frombuffer(bytes(vec_bytes), dtype=np.float32).copy())
    matrix = (
        np.stack(vecs).astype(np.float32) if vecs
        else np.empty((0, EMBED_DIM), dtype=np.float32)
    )
    return ids, matrix


# ─── In-memory vector stores ──────────────────────────────────────────────────

class _VectorStore:
    """Thread-safe in-memory (N, 512) float32 store keyed by registration_number.

    PostgreSQL is the source of truth; both stored vectors and queries are
    L2-normalised, so cosine similarity reduces to a dot product.
    """

    def __init__(self):
        self._ids: list[str] = []
        self._matrix = np.empty((0, EMBED_DIM), dtype=np.float32)
        self._lock = threading.Lock()

    def load(self) -> int:
        """Load (or reload) all embeddings from PostgreSQL. Returns record count."""
        ids, matrix = _rows_to_matrix(_fetch_all_embeddings())
        with self._lock:
            self._ids, self._matrix = ids, matrix
        return len(ids)

    def add(self, registration_number: str, embedding: np.ndarray) -> None:
        """Insert or update an L2-normalised embedding."""
        vec = embedding.astype(np.float32)
        with self._lock:
            if registration_number in self._ids:
                self._matrix[self._ids.index(registration_number)] = vec
            else:
                self._ids.append(registration_number)
                self._matrix = (
                    np.vstack([self._matrix, vec.reshape(1, EMBED_DIM)])
                    if self._matrix.shape[0] else vec.reshape(1, EMBED_DIM)
                )

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)


class EmbeddingCache(_VectorStore):
    """Attendance cache. Students are evicted on detection (detect-once), so the
    same person is reported to the LMS at most once per loaded session."""

    def claim(self, query: np.ndarray) -> str | None:
        """Atomically find the best match >= threshold and evict it.

        Returns the registration_number if a student was claimed, else None.
        Doing the match and eviction under one lock guarantees concurrent frames
        cannot both claim (and double-notify) the same student.
        """
        q = query.astype(np.float32)
        with self._lock:
            if self._matrix.shape[0] == 0:
                return None
            scores = self._matrix @ q
            best_idx = int(np.argmax(scores))
            if float(scores[best_idx]) < SIMILARITY_THRESHOLD:
                return None
            best_id = self._ids.pop(best_idx)
            self._matrix = np.delete(self._matrix, best_idx, axis=0)
            return best_id


class DedupIndex(_VectorStore):
    """Permanent index of every registered face (never evicted). Used to reject
    duplicate-face registrations without re-scanning the database each time."""

    def find_match(self, embedding: np.ndarray) -> tuple[str | None, float]:
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
        return (best_id, best_score) if best_score >= SIMILARITY_THRESHOLD else (None, best_score)


embedding_cache = EmbeddingCache()
dedup_index = DedupIndex()


# ─── Persistence ──────────────────────────────────────────────────────────────

def store_lms_embedding(registration_number: str, embedding: np.ndarray, sample_count: int) -> None:
    """Persist an embedding to PostgreSQL.

    Only the 512-dim float32 vector + registration number are written. Source
    images are processed in memory and never stored. Update the in-memory stores
    (embedding_cache / dedup_index) afterwards to avoid a full reload.
    """
    vec_bytes = embedding.astype(np.float32).tobytes()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO student_face_embeddings (registration_number, sample_count, vector)
               VALUES (%s, %s, %s)
               ON CONFLICT (registration_number) DO UPDATE
                   SET vector       = EXCLUDED.vector,
                       sample_count = EXCLUDED.sample_count,
                       created_at   = NOW()''',
            (registration_number, sample_count, psycopg2.Binary(vec_bytes)),
        )
        conn.commit()
        cur.close()


def registration_exists(registration_number: str) -> bool:
    """True if a student is already registered under this registration number."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT 1 FROM student_face_embeddings WHERE registration_number = %s',
            (registration_number,),
        )
        found = cur.fetchone() is not None
        cur.close()
    return found


def find_matching_student(embedding: np.ndarray) -> tuple[str | None, float]:
    """Find an already-registered face matching `embedding`.

    Backed by the in-memory `dedup_index` (loaded at startup, updated on each
    registration) — no per-call database scan.
    """
    return dedup_index.find_match(embedding)
