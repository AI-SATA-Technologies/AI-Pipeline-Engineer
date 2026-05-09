from datetime import date
from database import get_db_connection


def mark_attendance(student_id: int, confidence: float, camera_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT IGNORE INTO attendance
               (student_id, date, confidence, camera_id)
               VALUES (%s, %s, %s, %s)''',
            (student_id, date.today(), confidence, camera_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def get_student_id_by_name(name: str) -> int | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM students WHERE name=%s AND is_active=1', (name,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None
