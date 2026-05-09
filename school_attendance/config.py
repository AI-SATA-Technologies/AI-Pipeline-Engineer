import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'school_attendance')

LIVENESS_MODEL_PATH = 'models/2.7_80x80_MiniFASNetV2.onnx'
LIVENESS_THRESHOLD = float(os.getenv('LIVENESS_THRESHOLD', '0.70'))
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.55'))
FAISS_INDEX_PATH = 'embeddings/faiss.index'
FAISS_NAMES_PATH = 'embeddings/names.pkl'
MIN_REGISTRATION_SAMPLES = int(os.getenv('MIN_REGISTRATION_SAMPLES', '5'))
CAMERA_INTERVAL = int(os.getenv('CAMERA_INTERVAL', '5'))
