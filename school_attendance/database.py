from datetime import date

import numpy as np
import psycopg2
import psycopg2.extras

from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, SIMILARITY_THRESHOLD


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        dbname=DB_NAME,
    )


# ─── Attendance ────────────────────────────────────────────────────────────────

def mark_attendance(student_id: int, confidence: float, camera_id: str) -> bool:
    """Insert today's attendance. Returns True if newly marked."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT INTO attendance (student_id, date, confidence, camera_id)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (student_id, date) DO NOTHING''',
            (student_id, date.today(), confidence, camera_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close(); conn.close()


def get_student_id_by_name(name: str) -> int | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM students WHERE name=%s AND is_active=TRUE', (name,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row[0] if row else None


# ─── Embedding storage ─────────────────────────────────────────────────────────

def store_embedding(student_id: int, embedding: np.ndarray, sample_count: int) -> None:
    """Store a student's averaged 512-dim float32 embedding as raw bytes (BYTEA)."""
    vec_bytes = embedding.astype(np.float32).tobytes()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO embeddings (student_id, sample_count, vector)
           VALUES (%s, %s, %s)
           ON CONFLICT (student_id) DO UPDATE
               SET vector       = EXCLUDED.vector,
                   sample_count = EXCLUDED.sample_count,
                   created_at   = NOW()''',
        (student_id, sample_count, psycopg2.Binary(vec_bytes)),
    )
    conn.commit()
    cursor.close(); conn.close()


def _load_all_embeddings() -> list[tuple[str, np.ndarray]]:
    """Load all active students' embeddings from DB into memory for search."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT s.name, e.vector
           FROM embeddings e
           JOIN students s ON e.student_id = s.id
           WHERE s.is_active = TRUE'''
    )
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    result = []
    for name, vec_bytes in rows:
        vec = np.frombuffer(bytes(vec_bytes), dtype=np.float32).copy()
        result.append((name, vec))
    return result


# ─── Vector search (numpy cosine similarity) ──────────────────────────────────

def identify_face(embedding: np.ndarray) -> tuple[str, float]:
    """
    Cosine similarity search using numpy over all stored embeddings.
    No PostgreSQL extension required.
    Returns (student_name, score) or ('Unknown', score) if below threshold.
    Score range: -1.0 to 1.0  (1.0 = identical)
    Suitable for up to ~10,000 students at real-time speed.
    """
    records = _load_all_embeddings()
    if not records:
        return 'Unknown', 0.0

    names = [r[0] for r in records]
    matrix = np.stack([r[1] for r in records])          # (N, 512)
    query = embedding.astype(np.float32)

    # Cosine similarity = dot product (both sides are L2-normalized)
    scores = matrix @ query                              # (N,)
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])

    if best_score >= SIMILARITY_THRESHOLD:
        return names[best_idx], best_score
    return 'Unknown', best_score


# ─── Count ────────────────────────────────────────────────────────────────────

def count_registered_students() -> int:
    """Count active students who have a stored embedding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT COUNT(*) FROM embeddings e
           JOIN students s ON e.student_id = s.id
           WHERE s.is_active = TRUE'''
    )
    count = cursor.fetchone()[0]
    cursor.close(); conn.close()
    return count
