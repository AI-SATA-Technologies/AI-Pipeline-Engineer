"""
One-time migration script: FAISS → PostgreSQL

Reads the old faiss_heavy.index + names_heavy.pkl files and inserts each
student's face embedding into the PostgreSQL embeddings table.

Run once:
    cd school_attendance
    .\venv\Scripts\activate
    python migrate_faiss.py
"""
import os
import sys
import pickle
import numpy as np

try:
    import faiss
except ImportError:
    print("ERROR: faiss not installed. Run: pip install faiss-cpu")
    sys.exit(1)

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db_connection, store_embedding

INDEX_PATH = os.path.join('embeddings', 'faiss_heavy.index')
NAMES_PATH = os.path.join('embeddings', 'names_heavy.pkl')


def migrate():
    if not os.path.exists(INDEX_PATH) or not os.path.exists(NAMES_PATH):
        print(f"ERROR: FAISS files not found.")
        print(f"  Expected: {INDEX_PATH}")
        print(f"  Expected: {NAMES_PATH}")
        sys.exit(1)

    print("Loading FAISS heavy index...")
    index = faiss.read_index(INDEX_PATH)
    with open(NAMES_PATH, 'rb') as f:
        names = pickle.load(f)

    total = len(names)
    print(f"Found {total} student(s) in FAISS index: {names}\n")

    if index.ntotal != total:
        print(f"WARNING: index has {index.ntotal} vectors but {total} names. Will use min({index.ntotal}, {total}).")
        total = min(index.ntotal, total)

    conn = get_db_connection()
    cursor = conn.cursor()
    migrated = 0
    skipped = 0

    for i in range(total):
        name = names[i]

        # Skip if already in PostgreSQL
        cursor.execute('SELECT id FROM students WHERE name=%s', (name,))
        existing = cursor.fetchone()
        if existing:
            print(f"[{i+1}/{total}] Skipping '{name}' — already in PostgreSQL (id={existing[0]})")
            skipped += 1
            continue

        # Extract embedding from FAISS (IndexFlatIP stores raw vectors)
        embedding = index.reconstruct(i).astype(np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding /= norm  # ensure L2-normalized

        # Insert student record with auto-generated roll number
        roll = f'MIGRATED_{i+1:03d}'
        cursor.execute(
            'INSERT INTO students (name, roll_number) VALUES (%s, %s) RETURNING id',
            (name, roll),
        )
        student_id = cursor.fetchone()[0]
        conn.commit()

        # Store embedding in PostgreSQL
        store_embedding(student_id, embedding, sample_count=1)

        print(f"[{i+1}/{total}] Migrated '{name}' -> student_id={student_id}, roll={roll}")
        migrated += 1

    cursor.close()
    conn.close()

    print(f"\nMigration complete: {migrated} migrated, {skipped} skipped.")
    if migrated > 0:
        print("\nNOTE: Roll numbers were auto-generated (MIGRATED_001, etc.).")
        print("      Update them via:  python test_ui.py  ->  Students tab")
        print("      Or via API:       DELETE /api/students/{id} then re-register with correct details.")


if __name__ == '__main__':
    migrate()
