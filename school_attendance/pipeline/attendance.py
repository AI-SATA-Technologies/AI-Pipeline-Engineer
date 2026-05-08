import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv

# Load database credentials from .env
load_dotenv()

def mark_attendance(student_id):
    """
    Mark student as present in the MySQL database.
    Uses INSERT IGNORE or handled exception for deduplication.
    """
    conn = None
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASS', ''),
            database=os.getenv('DB_NAME', 'school_db')
        )
        cursor = conn.cursor()
        
        # The schema uses a UNIQUE KEY on (student_id, date) to prevent double counting
        # We use CURDATE() to ensure only one entry per day
        query = """
        INSERT INTO attendance (student_id, status, attendance_date) 
        VALUES (%s, 'present', CURDATE())
        """
        cursor.execute(query, (student_id,))
        conn.commit()
        print(f"Attendance recorded for {student_id}")
        return True
        
    except mysql.connector.Error as err:
        # 1062 is Duplicate Entry error code in MySQL
        if err.errno == 1062:
            print(f"Attendance already marked for {student_id} today.")
            return False
        else:
            print(f"Database Error: {err}")
            return False
    finally:
        if conn and conn.is_connected():
            conn.close()
