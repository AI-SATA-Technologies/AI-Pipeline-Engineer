import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'school_attendance')

# Pipeline mode: 'lite' (fast, MobileFaceNet) or 'heavy' (accurate, ArcFace R50)
MODE = os.getenv('MODE', 'heavy').lower()

LIVENESS_MODEL_PATH = 'models/2.7_80x80_MiniFASNetV2.onnx'
LIVENESS_THRESHOLD = float(os.getenv('LIVENESS_THRESHOLD', '0.60'))
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.40'))

# Per-mode FAISS index paths (embeddings from R50 ≠ MobileFaceNet, so separate them)
FAISS_INDEX_DIR = 'embeddings'
def faiss_paths(mode: str) -> tuple[str, str]:
    return (
        os.path.join(FAISS_INDEX_DIR, f'faiss_{mode}.index'),
        os.path.join(FAISS_INDEX_DIR, f'names_{mode}.pkl'),
    )

MIN_REGISTRATION_SAMPLES = int(os.getenv('MIN_REGISTRATION_SAMPLES', '5'))
CAMERA_INTERVAL = int(os.getenv('CAMERA_INTERVAL', '5'))
