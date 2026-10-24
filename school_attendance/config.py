"""Typed, validated configuration (pydantic-settings).

Values come from the environment / ``.env``. Invalid values fail fast at import
with a clear message. The module-level names below are the public interface the
rest of the code imports (``from config import MODE`` …).
"""
import os
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# Settings that older versions used but this one ignores.
_OBSOLETE_KEYS = ('MIN_REGISTRATION_SAMPLES',)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore', case_sensitive=True)

    # ─── PostgreSQL ─────────────────────────────────────────────────────────
    DB_HOST: str = 'localhost'
    DB_PORT: int = Field(5432, ge=1, le=65535)
    DB_USER: str = 'postgres'
    DB_PASS: str = ''
    DB_NAME: str = 'school_attendance'
    DB_POOL_MIN: int = Field(1, ge=1)
    DB_POOL_MAX: int = Field(8, ge=1)
    # Apply the idempotent schema migrations at startup.
    AUTO_MIGRATE: bool = True

    # ─── Pipeline ───────────────────────────────────────────────────────────
    # 'lite' (MobileFaceNet, fast) or 'heavy' (ArcFace R50, accurate)
    MODE: Literal['lite', 'heavy'] = 'heavy'
    SIMILARITY_THRESHOLD: float = Field(0.40, ge=-1.0, le=1.0)
    # Threshold for rejecting a registration as an already-registered face.
    # Empty = same as SIMILARITY_THRESHOLD.
    DEDUP_THRESHOLD: float | None = Field(None, ge=-1.0, le=1.0)
    # ONNX Runtime execution providers, in priority order (first available is used).
    #   CPU only (default):  CPUExecutionProvider
    #   NVIDIA GPU:          CUDAExecutionProvider,CPUExecutionProvider
    #   Windows DirectML:    DmlExecutionProvider,CPUExecutionProvider
    ONNX_PROVIDERS: str = 'CPUExecutionProvider'
    # Directory holding the .onnx model files, with buffalo_sc/ and buffalo_l/ subfolders.
    MODEL_DIR: str = '~/.insightface/models'
    # Max inference jobs running at once (frames + registrations + camera).
    INFERENCE_CONCURRENCY: int = Field(2, ge=1, le=32)

    # ─── Registration ───────────────────────────────────────────────────────
    # Photos that must be uploaded, and the minimum that must contain a usable face.
    REQUIRED_UPLOAD: int = Field(15, ge=1, le=100)
    REQUIRED_VALID: int = Field(7, ge=1)
    REG_MIN_DET_SCORE: float = Field(0.6, ge=0.0, le=1.0)
    REG_MIN_FACE_PX: int = Field(64, ge=0)
    # Photos whose embedding is less similar than this to the set's most
    # representative photo are dropped as outliers (a different person, a bad crop).
    REG_CONSISTENCY_MIN: float = Field(0.35, ge=-1.0, le=1.0)
    # Include the other student's registration_number in duplicate-face replies.
    REVEAL_DUPLICATE_MATCH: bool = False

    # ─── Security / limits ──────────────────────────────────────────────────
    # If set, the processing/registration endpoints require a matching X-API-Key
    # header. Several keys may be given comma-separated (rotation). Empty = open.
    API_KEY: str = ''
    # Allowed CORS origins (comma-separated). Empty = no cross-origin browser access.
    ALLOWED_ORIGINS: str = ''
    # Maximum accepted size (bytes) per uploaded image. Default 10 MB.
    MAX_UPLOAD_BYTES: int = Field(10 * 1024 * 1024, ge=1024)
    # Whole-request cap. 0 = REQUIRED_UPLOAD x MAX_UPLOAD_BYTES + 1 MB.
    MAX_REQUEST_BYTES: int = Field(0, ge=0)
    # Largest image (width x height) OpenCV will decode — blocks decompression bombs.
    MAX_IMAGE_PIXELS: int = Field(40_000_000, ge=1_000_000)

    # ─── LMS integration ────────────────────────────────────────────────────
    LMS_API_URL: str = ''
    # Sent as "Authorization: Bearer <token>" when set.
    LMS_API_TOKEN: str = ''
    LMS_TIMEOUT: float = Field(5.0, gt=0)
    LMS_MAX_ATTEMPTS: int = Field(10, ge=1)

    # ─── Attendance ─────────────────────────────────────────────────────────
    # IANA timezone that defines the attendance day (e.g. Asia/Karachi).
    # Empty = this server's local timezone.
    ATTENDANCE_TZ: str = ''

    # ─── Camera worker ──────────────────────────────────────────────────────
    # Empty = no server-side camera. "0" = webcam 0; rtsp://… = network camera;
    # a file path = video file (testing).
    CAMERA_URL: str = ''
    CAMERA_ID: str = Field('camera-1', min_length=1, max_length=50)
    CAMERA_FPS: float = Field(2.0, gt=0, le=30)

    @field_validator('MODE', mode='before')
    @classmethod
    def _normalise_mode(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @model_validator(mode='after')
    def _check(self):
        if self.DB_POOL_MIN > self.DB_POOL_MAX:
            raise ValueError('DB_POOL_MIN must be <= DB_POOL_MAX')
        if self.REQUIRED_VALID > self.REQUIRED_UPLOAD:
            raise ValueError('REQUIRED_VALID must be <= REQUIRED_UPLOAD')
        if self.ATTENDANCE_TZ:
            try:
                ZoneInfo(self.ATTENDANCE_TZ)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(
                    f'ATTENDANCE_TZ {self.ATTENDANCE_TZ!r} is not a valid IANA timezone'
                ) from exc
        return self


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(',') if v.strip()]


try:
    settings = Settings()
except ValidationError as exc:
    raise SystemExit(f'Invalid configuration (.env):\n{exc}') from None

# ─── Public names ────────────────────────────────────────────────────────────
DB_HOST = settings.DB_HOST
DB_PORT = settings.DB_PORT
DB_USER = settings.DB_USER
DB_PASS = settings.DB_PASS
DB_NAME = settings.DB_NAME
DB_POOL_MIN = settings.DB_POOL_MIN
DB_POOL_MAX = settings.DB_POOL_MAX
AUTO_MIGRATE = settings.AUTO_MIGRATE

MODE = settings.MODE
SIMILARITY_THRESHOLD = settings.SIMILARITY_THRESHOLD
DEDUP_THRESHOLD = (
    settings.DEDUP_THRESHOLD if settings.DEDUP_THRESHOLD is not None else SIMILARITY_THRESHOLD
)
ONNX_PROVIDERS = _split(settings.ONNX_PROVIDERS) or ['CPUExecutionProvider']
MODEL_DIR = os.path.expanduser(settings.MODEL_DIR)
INFERENCE_CONCURRENCY = settings.INFERENCE_CONCURRENCY

REQUIRED_UPLOAD = settings.REQUIRED_UPLOAD
REQUIRED_VALID = settings.REQUIRED_VALID
REG_MIN_DET_SCORE = settings.REG_MIN_DET_SCORE
REG_MIN_FACE_PX = settings.REG_MIN_FACE_PX
REG_CONSISTENCY_MIN = settings.REG_CONSISTENCY_MIN
REVEAL_DUPLICATE_MATCH = settings.REVEAL_DUPLICATE_MATCH

API_KEYS = _split(settings.API_KEY)
# First configured key — what viewer.py sends.
API_KEY = API_KEYS[0] if API_KEYS else ''
ALLOWED_ORIGINS = _split(settings.ALLOWED_ORIGINS)
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_BYTES
MAX_REQUEST_BYTES = settings.MAX_REQUEST_BYTES or (REQUIRED_UPLOAD * MAX_UPLOAD_BYTES + 1024 * 1024)
MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS

LMS_API_URL = settings.LMS_API_URL
LMS_API_TOKEN = settings.LMS_API_TOKEN
LMS_TIMEOUT = settings.LMS_TIMEOUT
LMS_MAX_ATTEMPTS = settings.LMS_MAX_ATTEMPTS

ATTENDANCE_TZ = ZoneInfo(settings.ATTENDANCE_TZ) if settings.ATTENDANCE_TZ else None

CAMERA_URL = settings.CAMERA_URL.strip()
CAMERA_ID = settings.CAMERA_ID
CAMERA_FPS = settings.CAMERA_FPS

OBSOLETE_KEYS_SET = [k for k in _OBSOLETE_KEYS if os.getenv(k)]

# OpenCV reads these when it decodes / opens streams, so they must be in the
# environment before any `import cv2`. Every entry point imports config first.
os.environ.setdefault('OPENCV_IO_MAX_IMAGE_PIXELS', str(MAX_IMAGE_PIXELS))
os.environ.setdefault('OPENCV_FFMPEG_CAPTURE_OPTIONS', 'rtsp_transport;tcp')
