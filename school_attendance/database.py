import numpy as np
import mysql.connector

from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, SIMILARITY_THRESHOLD


def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
    )


# ─── Store embedding ──────────────────────────────────────────────────────────

def store_embedding(lms_student_id: str, embedding: np.ndarray, sample_count: int) -> None:
    """
    Store (or overwrite) a student's averaged 512-dim float32 embedding.
    Only lms_student_id + vector are stored. Nothing else.
    """
    vec_bytes = embedding.astype(np.float32).tobytes()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO student_embeddings (lms_student_id, vector, sample_count)
           VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE
               vector       = VALUES(vector),
               sample_count = VALUES(sample_count),
               registered_at = CURRENT_TIMESTAMP''',
        (lms_student_id, vec_bytes, sample_count),
    )
    conn.commit()
    cursor.close()
    conn.close()


# ─── Check if student exists ──────────────────────────────────────────────────

def embedding_exists(lms_student_id: str) -> bool:
    """Return True if a student with this LMS ID already has a stored embedding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT 1 FROM student_embeddings WHERE lms_student_id = %s',
        (lms_student_id,),
    )
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return exists


# ─── Load all embeddings for search ──────────────────────────────────────────

def _load_all_embeddings() -> list[tuple[str, np.ndarray]]:
    """Load all stored (lms_student_id, embedding) pairs from DB into memory."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT lms_student_id, vector FROM student_embeddings')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    result = []
    for lms_student_id, vec_bytes in rows:
        vec = np.frombuffer(vec_bytes, dtype=np.float32).copy()
        result.append((lms_student_id, vec))
    return result


# ─── Identify face ────────────────────────────────────────────────────────────

def identify_face(embedding: np.ndarray) -> tuple[str | None, float]:
    """
    Cosine similarity search against all stored embeddings.
    Returns (lms_student_id, confidence) if match found above threshold.
    Returns (None, confidence) if no match.
    """
    records = _load_all_embeddings()
    if not records:
        return None, 0.0

    ids = [r[0] for r in records]
    matrix = np.stack([r[1] for r in records])   # (N, 512)
    query = embedding.astype(np.float32)

    # Cosine similarity — both sides are L2-normalized ArcFace vectors
    scores = matrix @ query                       # (N,)
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])

    if best_score >= SIMILARITY_THRESHOLD:
        return ids[best_idx], best_score
    return None, best_score


# ─── Count ────────────────────────────────────────────────────────────────────

def count_registered_students() -> int:
    """Count total registered students."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM student_embeddings')
    row = cursor.fetchone()
    count = row[0] if row else 0
    cursor.close()
    conn.close()
    return count
