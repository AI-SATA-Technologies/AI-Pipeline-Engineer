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

LIVENESS_MODEL_PATH = 'models/2.7_80x80_MiniFASNetV2.onnx'
LIVENESS_THRESHOLD = float(os.getenv('LIVENESS_THRESHOLD', '0.60'))
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.40'))

MIN_REGISTRATION_SAMPLES = int(os.getenv('MIN_REGISTRATION_SAMPLES', '5'))
