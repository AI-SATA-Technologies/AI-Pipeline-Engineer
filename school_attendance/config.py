import os

from dotenv import load_dotenv

load_dotenv()

# ─── PostgreSQL connection ──────────────────────────────────────────────────
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'school_attendance')

# Connection pool sizing (psycopg2 ThreadedConnectionPool).
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '1'))
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '8'))

# ─── Pipeline ───────────────────────────────────────────────────────────────
# 'lite' (MobileFaceNet, fast) or 'heavy' (ArcFace R50, accurate)
MODE = os.getenv('MODE', 'heavy').lower()

SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.40'))

# Registration sample requirements: photos that must be uploaded, and the
# minimum number of those that must contain a usable face.
REQUIRED_UPLOAD = int(os.getenv('REQUIRED_UPLOAD', '15'))
REQUIRED_VALID = int(os.getenv('REQUIRED_VALID', '7'))

# ONNX Runtime execution providers, in priority order (first available is used).
#   CPU only (default):  CPUExecutionProvider
#   NVIDIA GPU:          CUDAExecutionProvider,CPUExecutionProvider
#   Windows DirectML:    DmlExecutionProvider,CPUExecutionProvider
ONNX_PROVIDERS = [
    p.strip() for p in os.getenv('ONNX_PROVIDERS', 'CPUExecutionProvider').split(',') if p.strip()
] or ['CPUExecutionProvider']

# Directory holding the .onnx model files, with buffalo_sc/ and buffalo_l/ subfolders.
MODEL_DIR = os.path.expanduser(os.getenv('MODEL_DIR', '~/.insightface/models'))

# ─── Security ───────────────────────────────────────────────────────────────
# If set, the processing/registration endpoints require a matching X-API-Key
# header. Leave empty to keep the endpoints open (backward-compatible default).
API_KEY = os.getenv('API_KEY', '')

# Allowed CORS origins (comma-separated). Empty = no cross-origin browser access.
# Set to "*" only for trusted/development setups.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv('ALLOWED_ORIGINS', '').split(',') if o.strip()
]

# Maximum accepted size (bytes) per uploaded image. Default 10 MB.
MAX_UPLOAD_BYTES = int(os.getenv('MAX_UPLOAD_BYTES', str(10 * 1024 * 1024)))

# ─── LMS integration ────────────────────────────────────────────────────────
LMS_API_URL = os.getenv('LMS_API_URL', '')
