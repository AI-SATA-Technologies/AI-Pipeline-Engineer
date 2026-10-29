# 4 · Folder Structure

[← Back to index](README.md)

```
Attandance/                       ← repository root
├── README.md                     ← project front page (architecture, API, config)
├── about project/                ← this documentation
├── .github/workflows/ci.yml      ← automatic lint + tests + security audit on GitHub
├── .gitignore / .gitattributes   ← git rules (.bat files keep Windows line endings)
│
└── school_attendance/            ← the application
    ├── main.py                   ← START HERE: API endpoints + startup/shutdown
    ├── attendance.py             ← business rules: recognition → attendance; registration
    ├── camera_worker.py          ← reads the IP camera / webcam / video file
    ├── lms.py                    ← sends attendance to the LMS (outbox + retries)
    ├── database.py               ← PostgreSQL queries, migrations, in-memory face lists
    ├── auth.py                   ← X-API-Key check
    ├── limits.py                 ← rejects oversized requests
    ├── config.py                 ← reads + validates .env
    ├── viewer.py                 ← live view window: camera → server → draws boxes
    ├── download_models.py        ← downloads + verifies the face models
    │
    ├── pipeline/                 ← face AI
    │   ├── engine.py             ← decode → detect → align → embed (shared entry point)
    │   ├── scrfd.py              ← SCRFD face detector (ONNX Runtime)
    │   ├── align.py              ← aligns a face to 112×112 using 5 landmarks
    │   ├── detector.py           ← detector wrapper (lite 320 / heavy 640)
    │   ├── recognizer.py         ← ArcFace / MobileFaceNet → 512-number embedding
    │   └── model_files.py        ← model file names, paths and SHA-256 checksums
    │
    ├── migrations/               ← database changes, applied automatically at startup
    │   ├── 001_init.sql          ← student_face_embeddings table
    │   └── 002_attendance.sql    ← model column + attendance_events table
    ├── schema.sql                ← creates the database on a fresh install
    │
    ├── scripts/                  ← Windows helpers (double-click)
    │   ├── setup.bat             ← one-click install on a new PC
    │   ├── setup_helper.py       ← used by setup.bat (don't run directly)
    │   ├── start.bat             ← start the server on port 8000
    │   ├── stop.bat              ← stop the server (and the viewer)
    │   ├── restart.bat           ← free port 8000, then start
    │   ├── status.bat            ← show server status
    │   └── viewer.bat            ← open the live camera viewer
    │
    ├── tests/                    ← automated tests (no DB or models needed)
    │   ├── conftest.py           ← test setup (isolates tests from your .env)
    │   ├── fakes.py              ← fake database + fake face pipeline
    │   ├── test_api.py           ← endpoints, attendance, registration, day rollover
    │   ├── test_lms.py           ← LMS delivery and retries
    │   ├── test_hardening.py     ← limits, image bombs, DB errors, config, camera URLs
    │   ├── test_cache.py         ← in-memory face lists
    │   ├── test_auth.py          ← API keys
    │   ├── test_align.py         ← face alignment maths
    │   └── test_scrfd.py         ← detector box decoding
    │
    ├── requirements.txt          ← packages needed to run
    ├── requirements-dev.txt      ← + test / lint / audit tools
    ├── pyproject.toml            ← ruff + pytest settings
    ├── Dockerfile / .dockerignore← container build
    └── .env.example              ← template for .env (copy, then fill in)
```

## Created on each PC (not in git)

| Path | Created by | Contents |
|------|-----------|----------|
| `school_attendance/venv/` | `setup.bat` | Private Python + installed packages (~330 MB). Never copy between PCs |
| `school_attendance/.env` | `setup.bat` / you | Your settings and secrets (DB password, API key, camera login). **Never commit or share** |
| `C:\Users\<you>\.insightface\models\` | `download_models.py` | Face models (~182 MB). Location set by `MODEL_DIR` |
| `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` | Python / tools | Caches; safe to delete |

## Where the data lives

All data is in **PostgreSQL** (database `school_attendance` by default), not in the
project folder:

| Table | One row per | Main columns |
|-------|-------------|--------------|
| `student_face_embeddings` | registered student | `registration_number` (key), `vector` (embedding), `model`, `sample_count`, `created_at` |
| `attendance_events` | student per day they were seen | `registration_number`, `attendance_date`, `detected_at`, `source`, `score`, `lms_status`, `lms_attempts`, `lms_last_error` |

## How a request flows through the files

**A camera frame:** `camera_worker.py` (or `main.py → /api/camera/process-frame`)
→ `pipeline/engine.py` (detect + embed) → `attendance.py → record_faces()`
→ `database.py` (claim from pending list, insert event) → `lms.py` (deliver).

**A registration:** `main.py → /api/register/lms` → `attendance.py → register()`
→ `pipeline/engine.py → embed_photos()` → `attendance.py → build_template()`
→ `database.py` (duplicate check, insert).
