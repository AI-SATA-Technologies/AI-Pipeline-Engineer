import os
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL connection
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'school_attendance')

# Pipeline mode: 'lite' (MobileFaceNet, fast) or 'heavy' (ArcFace R50, accurate)
MODE = os.getenv('MODE', 'heavy').lower()

SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.40'))

MIN_REGISTRATION_SAMPLES = int(os.getenv('MIN_REGISTRATION_SAMPLES', '5'))

# LMS integration
LMS_API_URL = os.getenv('LMS_API_URL', '')

# Camera — integer index (e.g. 0) for webcam, or full URL for RTSP/HTTP
_cam = os.getenv('CAMERA_URL', '')
CAMERA_URL = int(_cam) if _cam.isdigit() else _cam
