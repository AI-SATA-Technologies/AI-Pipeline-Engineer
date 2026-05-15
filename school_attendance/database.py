import threading

import numpy as np
import psycopg2

from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, SIMILARITY_THRESHOLD


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        dbname=DB_NAME,
    )


# ─── In-memory embedding cache ────────────────────────────────────────────────

class EmbeddingCache:
    """
    Thread-safe in-memory store of all student embeddings.

    PostgreSQL is the source of truth; this cache serves every detection query
    with zero DB I/O.  Layout:
        _ids    — ordered list of registration_number strings
        _matrix — (N, 512) float32 array; row i corresponds to _ids[i]

    Cosine similarity reduces to a dot product because both the stored vectors
    and the query are L2-normalised before they reach this class.
    """

    def __init__(self):
        self._ids: list[str] = []
        self._matrix = np.empty((0, 512), dtype=np.float32)
        self._lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def load(self) -> int:
        """Load (or reload) all embeddings from PostgreSQL. Returns record count."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT registration_number, vector FROM student_face_embeddings')
        rows = cursor.fetchall()
        cursor.close(); conn.close()

        ids, vecs = [], []
        for lms_id, vec_bytes in rows:
            ids.append(lms_id)
            vecs.append(np.frombuffer(bytes(vec_bytes), dtype=np.float32).copy())

        with self._lock:
            self._ids = ids
            self._matrix = (
                np.stack(vecs).astype(np.float32)
                if vecs else np.empty((0, 512), dtype=np.float32)
            )
        return len(ids)

    # ── Write ──────────────────────────────────────────────────────────────────

    def add(self, registration_number: str, embedding: np.ndarray) -> None:
        """Insert or update a student's L2-normalised embedding in the cache."""
        vec = embedding.astype(np.float32)
        with self._lock:
            if registration_number in self._ids:
                self._matrix[self._ids.index(registration_number)] = vec
            else:
                self._ids.append(registration_number)
                self._matrix = (
                    np.vstack([self._matrix, vec.reshape(1, 512)])
                    if self._matrix.shape[0] else vec.reshape(1, 512)
                )

    def remove(self, registration_number: str) -> None:
        """Evict a student from RAM after their attendance is marked."""
        with self._lock:
            if registration_number not in self._ids:
                return
            idx = self._ids.index(registration_number)
            self._ids.pop(idx)
            self._matrix = np.delete(self._matrix, idx, axis=0)

    # ── Read ───────────────────────────────────────────────────────────────────

    def search(self, query: np.ndarray) -> tuple[str, float]:
        """
        Cosine similarity search via matrix dot-product (no DB I/O).
        Returns (registration_number, score) or ('Unknown', score) if below threshold.
        Score range: -1.0 to 1.0  (1.0 = identical).
        """
        with self._lock:
            if self._matrix.shape[0] == 0:
                return 'Unknown', 0.0
            scores = self._matrix @ query.astype(np.float32)   # (N,)
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])
            best_id = self._ids[best_idx]

        if best_score >= SIMILARITY_THRESHOLD:
            return best_id, best_score
        return 'Unknown', best_score

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)


embedding_cache = EmbeddingCache()


# ─── LMS embedding storage ─────────────────────────────────────────────────────

def store_lms_embedding(registration_number: str, embedding: np.ndarray, sample_count: int) -> None:
    """
    Persist the embedding to PostgreSQL.
    Only the 512-dim float32 vector and the registration number are written to the DB.
    Source images are processed in memory and never stored anywhere.
    Call embedding_cache.add() after this to keep the cache current without a reload.
    """
    vec_bytes = embedding.astype(np.float32).tobytes()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO student_face_embeddings (registration_number, sample_count, vector)
           VALUES (%s, %s, %s)
           ON CONFLICT (registration_number) DO UPDATE
               SET vector       = EXCLUDED.vector,
                   sample_count = EXCLUDED.sample_count,
                   created_at   = NOW()''',
        (registration_number, sample_count, psycopg2.Binary(vec_bytes)),
    )
    conn.commit()
    cursor.close(); conn.close()


def registration_exists(registration_number: str) -> bool:
    """True if a student is already registered under this registration number."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT 1 FROM student_face_embeddings WHERE registration_number = %s',
        (registration_number,),
    )
    found = cursor.fetchone() is not None
    cursor.close(); conn.close()
    return found


def find_matching_student(embedding: np.ndarray) -> tuple[str | None, float]:
    """
    Search every stored embedding for a face matching `embedding`.
    Returns (registration_number, score) of the best match at or above
    SIMILARITY_THRESHOLD, or (None, score) if no stored face matches.

    Scans the full DB on purpose — embedding_cache is emptied as attendance
    is marked, so it cannot be used to detect already-registered faces.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT registration_number, vector FROM student_face_embeddings')
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    if not rows:
        return None, 0.0

    ids = [r[0] for r in rows]
    matrix = np.stack([
        np.frombuffer(bytes(r[1]), dtype=np.float32) for r in rows
    ]).astype(np.float32)
    scores = matrix @ embedding.astype(np.float32)
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    if best_score >= SIMILARITY_THRESHOLD:
        return ids[best_idx], best_score
    return None, best_score


