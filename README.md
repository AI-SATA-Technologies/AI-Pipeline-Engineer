<div align="center">

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║       █████╗ ██╗      ██████╗ ██╗ ██████╗  ██████╗  ███████╗             ║
║      ██╔══██╗██║      ██╔══██╗██║██╔════╝ ██╔═══██╗ ██╔════╝             ║
║      ███████║██║      ██████╔╝██║██║  ███╗██║   ██║ █████╗               ║
║      ██╔══██║██║      ██╔══██╗██║██║   ██║██║   ██║ ██╔══╝               ║
║      ██║  ██║██║██╗   ██║  ██║██║╚██████╔╝╚██████╔╝ ███████╗             ║
║      ╚═╝  ╚═╝╚═╝╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝  ╚═════╝  ╚══════╝             ║
║                                                                          ║
║              S C H O O L  ·  F A C E  ·  A T T E N D A N C E             ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

###### A headless, LMS-integrated face-recognition attendance API.
###### FastAPI · ONNX Runtime · SCRFD + ArcFace · PostgreSQL · OpenCV

![Python](https://img.shields.io/badge/python-3.11%20%7C%203.13-1c1c1c?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/fastapi-0.162-009688?style=flat-square&logo=fastapi&logoColor=white)
![Models](https://img.shields.io/badge/models-SCRFD%20%2B%20ArcFace-ff5c00?style=flat-square)
![ONNX Runtime](https://img.shields.io/badge/onnxruntime-1.31-005f9e?style=flat-square)
![PostgreSQL](https://img.shields.io/badge/postgresql-12%2B-336791?style=flat-square&logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-internal-1c1c1c?style=flat-square)

**📘 Full documentation: [`about project/`](about%20project/README.md)** — overview,
requirements, setup, folder structure, configuration, API, camera, operations,
troubleshooting, security, development.

**🚀 New PC?** Double-click `school_attendance\scripts\setup.bat`.

</div>

---

## ❍ &nbsp; Synopsis

A production-grade face-recognition **backend** for schools, built to plug into an
existing **LMS** — there is no UI of its own. The LMS enrolls a student once by
posting a batch of photos; afterwards the service watches a camera (it reads an RTSP
stream itself, or a client posts frames), recognizes each face, and reports
attendance to the LMS.

The split of responsibility is deliberate:

- **This service owns recognition** — face embedding, matching, duplicate rejection,
  and reliable *delivery* of each detection (it keeps a per-day attendance log that
  doubles as a retry queue).
- **The LMS owns attendance records** — it receives `{registration_number, detected_at}`
  and records the attendance row however it likes.

Only the averaged face embedding, the registration number and the per-day detection
log are stored. Source images are decoded in memory and discarded.

The pipeline runs in two interchangeable modes, selected by the `MODE` env var:

| Mode | Detector | Recognizer | Use case |
|------|----------|------------|----------|
| **⚡ Lite**  | SCRFD @ 320×320 | MobileFaceNet (`w600k_mbf.onnx`, 13 MB)  | Low-end PCs, real-time on CPU |
| **🎯 Heavy** | SCRFD @ 640×640 | ArcFace R50    (`w600k_r50.onnx`, 174 MB) | Maximum accuracy, small faces |

Detection and alignment run **directly on ONNX Runtime + OpenCV** — there is no
heavyweight face SDK dependency.

---

## ❍ &nbsp; What Makes It Real

```
  ┌─────────────────────┬──────────────────────────────────────────────┐
  │  API-only           │  Plugs behind any LMS — no frontend to host. │
  │                     │  API-key auth (with key rotation), opt-in    │
  │                     │  CORS, request/image size limits.            │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │  Never loses a      │  Detections are written to the DB first,     │
  │  detection          │  then delivered to the LMS by an outbox      │
  │                     │  that retries with backoff across restarts.  │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │  Once per day       │  Each student is reported once per           │
  │                     │  attendance day — even across restarts —     │
  │                     │  and everyone resets automatically at        │
  │                     │  midnight (ATTENDANCE_TZ).                   │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │  Reads the camera   │  Built-in RTSP worker: TCP transport, no     │
  │                     │  buffer lag, gentle reconnects that won't    │
  │                     │  trip the camera's login lockout.            │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │  Clean enrollment   │  Largest confident face per photo, outlier   │
  │                     │  photos dropped, duplicate number AND        │
  │                     │  duplicate face rejected — atomically.       │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │  In-memory search   │  Every embedding lives in one (N,512) NumPy  │
  │                     │  matrix; recognition is a single dot-product │
  │                     │  — zero DB reads on the hot path.            │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │  Privacy-first      │  No source photos persisted; duplicate-face  │
  │                     │  replies don't reveal other students; face   │
  │                     │  data can be erased per student.             │
  └─────────────────────┴──────────────────────────────────────────────┘
```

---

## ❍ &nbsp; System Architecture

```mermaid
flowchart LR
    subgraph CLIENTS["🌐  Clients"]
        LMS_C[LMS Backend]
        RTSP[IP camera<br/>RTSP]
        CAM[viewer.py / any client<br/>JPEG frames]
    end

    subgraph SERVER["⚙️  FastAPI · uvicorn :8000 · 1 worker"]
        REG[POST /api/register/lms]
        FRAME[POST /api/camera/process-frame]
        WORKER[Camera worker<br/>CAMERA_URL]
        SVC[Attendance service<br/>claim → record]
        OUTBOX[LMS outbox<br/>retry + backoff]
        PIPE[Pipeline<br/>detector + recognizer]
    end

    subgraph MODELS["🧠  ONNX Models (SHA-256 pinned)"]
        DET[SCRFD 500M]
        REC[ArcFace R50 /<br/>MobileFaceNet]
    end

    subgraph STORE["💾  Persistence"]
        PG[(PostgreSQL<br/>student_face_embeddings<br/>attendance_events)]
        CACHE[In-memory pending cache<br/>+ dedup index]
    end

    LMS_C -->|15 photos| REG
    CAM -->|JPEG frame| FRAME
    RTSP -->|stream| WORKER
    REG --> PIPE
    FRAME --> PIPE
    WORKER --> PIPE
    PIPE --> DET
    PIPE --> REC
    FRAME --> SVC
    WORKER --> SVC
    SVC -->|claim| CACHE
    SVC -->|insert event| PG
    REG -->|store vector| PG
    PG -->|load at startup / new day| CACHE
    PG --> OUTBOX
    OUTBOX -->|POST detection| LMS_C

    classDef client fill:#0a0a0a,stroke:#ff5c00,color:#fff
    classDef server fill:#1c1c1c,stroke:#009688,color:#fff
    classDef model  fill:#1c1c1c,stroke:#ff5c00,color:#fff
    classDef store  fill:#1c1c1c,stroke:#4479a1,color:#fff
    class LMS_C,RTSP,CAM client
    class REG,FRAME,WORKER,SVC,OUTBOX,PIPE server
    class DET,REC model
    class PG,CACHE store
```

---

## ❍ &nbsp; Registration Flow

The LMS posts **exactly 15 photos** (`REQUIRED_UPLOAD`). From each photo the **largest**
face that is confident (`REG_MIN_DET_SCORE`) and big enough (`REG_MIN_FACE_PX`) is
embedded. Photos that don't look like the rest of the set — compared with the set's
most representative photo (`REG_CONSISTENCY_MIN`) — are dropped as outliers; at least
**7** must remain (`REQUIRED_VALID`). They are averaged into one L2-normalized 512-d
vector. The duplicate check and the insert run as one locked step, so two concurrent
registrations can't both get in.

```mermaid
sequenceDiagram
    autonumber
    participant U as LMS Backend
    participant API as POST /api/register/lms
    participant P as Pipeline
    participant C as In-memory stores
    participant DB as PostgreSQL

    U->>API: registration_number + photos[] (×15)
    API->>API: count = REQUIRED_UPLOAD? number valid (1–100 chars)?
    API->>DB: registration_exists(reg_no)?
    alt already registered
        API-->>U: { status: 0, "already registered" }
    end
    API->>P: embed_photos — largest confident face per photo
    API->>API: drop outlier photos → need ≥ REQUIRED_VALID → average
    Note over API,DB: registration lock
    API->>C: dedup_index.find_match(template)
    alt face matches another student
        API-->>U: { status: 0, "face already registered under another number" }
    else new face
        API->>DB: INSERT … ON CONFLICT DO NOTHING
        API->>C: dedup_index.add + cache.add
        API-->>U: { status: 1, "registered successfully" }
    end
```

---

## ❍ &nbsp; Recognition Flow

Frames come from the built-in camera worker (`CAMERA_URL`) or from clients posting
JPEGs. Each face is matched against the in-memory **pending** cache — students not yet
marked today. A hit is claimed atomically (match + evict under one lock), written to
`attendance_events` (unique per student per day), and queued for the LMS. If the DB
write fails the claim is undone, so the student is simply detected again later.

```mermaid
sequenceDiagram
    autonumber
    participant SRC as Camera worker / client
    participant P as Pipeline
    participant C as Pending cache
    participant DB as attendance_events
    participant OB as LMS outbox
    participant LMS as LMS_API_URL

    SRC->>P: frame
    P-->>SRC: faces[] (bbox + embedding)
    loop each face
        SRC->>C: claim(emb)  (atomic match + evict)
        alt matched (score ≥ SIMILARITY_THRESHOLD)
            SRC->>DB: INSERT event (pending) — once per student per day
            Note right of SRC: status "notified"
        else seen earlier today
            Note right of SRC: status "already_marked"
        else no match
            Note right of SRC: status "unknown"
        end
    end
    OB->>DB: pending events due?
    OB->>LMS: POST { registration_number, detected_at }
    alt 2xx
        OB->>DB: lms_status = sent
    else error / timeout / 5xx
        OB->>DB: retry later (5 s, 10 s, 20 s … ≤ 10 min), failed after LMS_MAX_ATTEMPTS
    end
```

> **Day rollover.** The pending cache is rebuilt automatically when the attendance day
> changes (in `ATTENDANCE_TZ`), and at every start/reload it excludes students already
> marked today — so a restart never re-notifies anyone. Duplicate-face checks at
> registration use a separate, permanent `dedup_index` (never evicted).

---

## ❍ &nbsp; Data Model

```mermaid
erDiagram
    STUDENT_FACE_EMBEDDINGS {
        varchar   registration_number PK
        timestamp created_at
        int       sample_count
        bytea     vector "512-d float32, L2-normalized"
        varchar   model  "w600k_r50 | w600k_mbf"
    }
    ATTENDANCE_EVENTS {
        bigserial   id PK
        varchar     registration_number
        date        attendance_date "UNIQUE with registration_number"
        timestamptz detected_at
        varchar     source "api | CAMERA_ID"
        real        score
        varchar     lms_status "pending | sent | failed | skipped"
        int         lms_attempts
        text        lms_last_error
        timestamptz next_attempt_at
    }
```

The schema lives in `migrations/*.sql` (idempotent) and is applied at startup when
`AUTO_MIGRATE=true` (default). `attendance_events` has no foreign key on purpose: the
history survives when a student's face data is deleted. Embeddings are tagged with the
`model` that produced them; only rows matching the active `MODE` are loaded.

> Embeddings are stored as raw `BYTEA` and searched in Python (NumPy dot-product over
> L2-normalized vectors == cosine similarity). No `pgvector` or other extension is
> required.

---

## ❍ &nbsp; Tech Stack

| Layer | Component | Role |
|-------|-----------|------|
| **Web** | FastAPI 0.162 · Uvicorn 0.54 · python-multipart 0.0.32 | REST API, API-key auth, body-size limit |
| **Config** | pydantic-settings 2.16 | Typed, validated `.env` (fails fast on bad values) |
| **Detection** | SCRFD 500M on ONNX Runtime 1.31 | Face detector + 5-point align (NumPy Umeyama) |
| **Recognition** | ArcFace R50 / MobileFaceNet | 512-d L2-normalized embeddings |
| **Search** | NumPy 2.4 `(N,512)` matrix dot-product | Cosine similarity, in-process |
| **Storage** | PostgreSQL 12+ (tested 17) + psycopg2-binary 2.9.13 (pooled) | Embeddings + attendance/outbox |
| **LMS client** | httpx 0.28 (async, shared connection pool) | Outbox delivery with retries |
| **Video / image I/O** | OpenCV 4.14 (FFmpeg) | Decode, RTSP, align |
| **Quality** | pytest 9 · ruff · pip-audit · GitHub Actions | Tests, lint, dependency CVE audit |

---

## ❍ &nbsp; Project Layout

```
school_attendance/
├── main.py                 ← FastAPI routes + lifespan (startup, background tasks)
├── attendance.py           ← attendance + registration service (shared by API and camera)
├── camera_worker.py        ← server-side RTSP / webcam / video-file reader
├── lms.py                  ← LMS outbox: delivery, retries, backoff
├── database.py             ← pooled psycopg2, migrations, queries, in-memory vector stores
├── auth.py                 ← env-gated X-API-Key dependency (multiple keys)
├── limits.py               ← request body-size limit middleware
├── config.py               ← typed settings (pydantic-settings)
├── migrations/             ← idempotent schema migrations (applied at startup)
├── schema.sql              ← creates the database + applies migrations (fresh install)
├── download_models.py      ← fetch + SHA-256-verify the ONNX models (one-time)
├── viewer.py               ← live view: camera → server → draws returned boxes
├── requirements.txt        ← runtime deps
├── requirements-dev.txt    ← + pytest, ruff, pip-audit
├── pyproject.toml          ← ruff + pytest config
├── Dockerfile              ← non-root, headless OpenCV, healthcheck
├── .env.example            ← copy to .env and fill in
│
├── pipeline/
│   ├── engine.py           ← decode → detect → align → embed (concurrency-capped)
│   ├── scrfd.py            ← SCRFD detector on raw ONNX Runtime
│   ├── align.py            ← ArcFace 5-point norm_crop (NumPy Umeyama)
│   ├── detector.py         ← detector wrapper (lite/heavy det_size) + align
│   ├── recognizer.py       ← ArcFace / MobileFaceNet inference
│   └── model_files.py      ← model paths + pinned SHA-256 checksums
│
├── tests/                  ← pytest suite (fakes for DB + models: runs anywhere)
│
└── scripts/                ← Windows helpers: setup.bat (one-click install), start, restart, stop, status, viewer
```

---

## ❍ &nbsp; API Surface

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET`    | `/healthz` | open | Liveness probe (process up) |
| `GET`    | `/api/status` | open | Readiness, DB, mode/model, counts, LMS backlog, camera state |
| `POST`   | `/api/register/lms` | key | Enroll a student (multipart: `registration_number`, `photos[]` ×15) |
| `POST`   | `/api/camera/process-frame` | key | Recognize faces in one image (`file`) and record attendance |
| `GET`    | `/api/attendance?date=YYYY-MM-DD` | key | Attendance for a day (default today) with LMS delivery status |
| `DELETE` | `/api/students/{registration_number}` | key | Erase a student's face data (history kept); allows re-registration |
| `POST`   | `/api/cache/reload` | key | Reload embeddings from PostgreSQL (after editing the DB by hand) |

> **Auth:** when `API_KEY` is set, send it as an `X-API-Key` header ("key" rows above).
> Several comma-separated keys are accepted, for rotation. When `API_KEY` is empty the
> endpoints are open and a warning is logged at startup.
>
> Until the database has been loaded once, keyed endpoints return `503`
> (`/api/status` → `"ready": false`); loading is retried every 10 s.

### `GET /api/status`

```json
{
  "status": "running", "ready": true, "db_ok": true,
  "mode": "heavy", "model": "w600k_r50", "attendance_date": "2026-10-24",
  "students_pending": 42, "registered_total": 1280, "ignored_other_model": 0,
  "lms_enabled": true, "lms_pending": 0,
  "camera": { "id": "camera-1", "state": "running", "frames_processed": 5120,
              "last_frame_at": "2026-10-24T03:15:00+00:00", "last_error": null }
}
```

### `POST /api/register/lms`

Multipart form: `registration_number` (1–100 characters) + `photos[]` (exactly 15 image
files, each ≤ `MAX_UPLOAD_BYTES`).

```bash
curl -X POST http://localhost:8000/api/register/lms \
  -H "X-API-Key: $API_KEY" \                      # omit if API_KEY is unset
  -F "registration_number=2026-CS-001" \
  -F "photos[]=@1.jpg" -F "photos[]=@2.jpg" ...  # 15 files total
```

```jsonc
// success
{ "success": true,  "status": 1, "message": "Face registered successfully" }
// failures (HTTP 200, status 0):
//   "Exactly 15 photos required, received N"
//   "registration_number is required" / "... at most 100 characters" / "... invalid characters"
//   "registration_number <X> is already registered"
//   "Only N photo(s) had a detectable face, at least 7 required"
//   "Only N of M photos consistently show the same person, at least 7 required"
//   "This face is already registered under another registration_number"
//      (names the other number only if REVEAL_DUPLICATE_MATCH=true)
```

### `POST /api/camera/process-frame`

Multipart form: `file` (one JPEG/PNG; > `MAX_UPLOAD_BYTES` → `413`; corrupt or larger
than `MAX_IMAGE_PIXELS` → `400`).

```bash
curl -X POST http://localhost:8000/api/camera/process-frame \
  -H "X-API-Key: $API_KEY" -F "file=@frame.jpg"
```

```json
{
  "faces_detected": 2,
  "detected_at": "2026-10-24T03:30:00+00:00",
  "results": [
    { "registration_number": "2026-CS-001", "status": "notified",
      "detected_at": "2026-10-24T03:30:00+00:00", "bbox": [412, 120, 530, 268] },
    { "status": "unknown", "bbox": [80, 140, 170, 252] }
  ]
}
```

Per-face `status`: `notified` (newly marked; the LMS is told asynchronously),
`already_marked` (seen earlier today), `unknown`, or `error` (could not be recorded —
the student will be detected again). `bbox` is `[x1, y1, x2, y2]` in frame pixels.
Timestamps are UTC (ISO-8601).

### `GET /api/attendance`

```bash
curl "http://localhost:8000/api/attendance?date=2026-10-24" -H "X-API-Key: $API_KEY"
```

```json
{ "date": "2026-10-24", "count": 1, "events": [
  { "registration_number": "2026-CS-001", "detected_at": "2026-10-24T08:30:00+05:00",
    "source": "camera-1", "score": 0.6312, "lms_status": "sent",
    "lms_attempts": 1, "lms_last_error": null } ] }
```

### `DELETE /api/students/{registration_number}`

Removes the student's embedding from the DB and memory (a leaver, a re-enrollment, or
an erasure request). Attendance history is kept. `404` if not registered.

### LMS detection callback

For each new attendance event the outbox POSTs to `LMS_API_URL` (with
`Authorization: Bearer $LMS_API_TOKEN` if set). Any non-2xx reply, timeout or network
error is retried — 5 s, 10 s, 20 s … up to 10 min apart — until `LMS_MAX_ATTEMPTS`,
then the event is marked `failed` (visible in `/api/attendance`). Pending events are
resent after a restart.

```json
{ "registration_number": "2026-CS-001", "detected_at": "2026-10-24T03:30:00+00:00" }
```

---

## ❍ &nbsp; Setup

> Tested on **Windows 11 / Python 3.11 / PostgreSQL 17**; CI also runs Python 3.13 on
> Linux.

### ⚡ One-click setup (Windows)

```
school_attendance\scripts\setup.bat
```

It finds Python, creates the venv, installs the packages, creates `.env` (with a random
`API_KEY`) and opens it for you to fill in, downloads and verifies the models, creates
the database and tables, and checks that the pipeline loads. Safe to re-run. Details:
[about project/03-setup.md](about%20project/03-setup.md). The manual steps follow.

### 1 · Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | **3.11 – 3.13** | All dependencies ship wheels for cp311–cp313 |
| PostgreSQL | **12+** (tested 17) | Port 5432 default |
| Camera | IP camera (RTSP) or webcam | Optional: the API also accepts posted frames |

### 2 · Virtualenv + dependencies

```powershell
cd school_attendance
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3 · PostgreSQL

Create the database once (tables are created/updated automatically at startup):

```bash
psql -U postgres -f schema.sql
```

> Upgrading from v3.1? Nothing to do — the server applies `migrations/002_attendance.sql`
> on start. Existing embeddings are tagged `w600k_r50` (heavy mode).

### 4 · Download the face models

```bash
python download_models.py
```

This downloads, **SHA-256-verifies** and keeps the three files the pipeline uses (unused
`buffalo_l` models are pruned to save several hundred MB):

```
~/.insightface/models/buffalo_sc/det_500m.onnx   ← detector (both modes)
~/.insightface/models/buffalo_sc/w600k_mbf.onnx  ← lite recognizer
~/.insightface/models/buffalo_l/w600k_r50.onnx   ← heavy recognizer
```

> If the download fails (network/proxy), place those three files under `MODEL_DIR`
> manually; the script will verify them on the next run.

### 5 · `.env`

Copy `.env.example` to `.env` and fill it in — at minimum:

```env
DB_USER=postgres
DB_PASS=your_postgres_password
API_KEY=<long random string>        # e.g. python -c "import secrets; print(secrets.token_urlsafe(32))"
LMS_API_URL=https://your-lms.example.com/api/attendance
ATTENDANCE_TZ=Asia/Karachi          # the school's timezone
CAMERA_URL=rtsp://admin:PASSWORD@192.168.18.234:554/Streaming/Channels/101
```

See the configuration reference below (or [about project/05-configuration.md](about%20project/05-configuration.md)) for everything else.

### 6 · Run

```bash
cd school_attendance
uvicorn main:app --host 0.0.0.0 --port 8000      # keep ONE worker
```

On Windows you can use the helpers in `scripts/` instead (`start.bat`, `status.bat`,
`stop.bat`, …). Then:

| Resource | URL |
|----------|-----|
| Interactive API docs | `http://localhost:8000/docs` |
| Status / readiness | `http://localhost:8000/api/status` |

To watch the camera with recognition boxes drawn on it:

```bash
python viewer.py                 # uses CAMERA_URL, else webcam 0; press Q to quit
python viewer.py 0               # or pass a source: webcam index, rtsp://…, video file
```

### 7 · Tests, lint, audit

```bash
pip install -r requirements-dev.txt
pytest                      # no database or models needed
ruff check .
pip-audit -r requirements.txt
```

The same checks run on every push / PR (`.github/workflows/ci.yml`).

### 8 · Docker (optional)

Models aren't baked into the image — mount them (or run `download_models.py` in-container):

```bash
docker build -t school-attendance .
docker run -p 8000:8000 --env-file .env -v ~/.insightface/models:/models:ro school-attendance
```

The image runs as a non-root user with headless OpenCV and a `/healthz` healthcheck.

---

## ❍ &nbsp; Configuration Reference

Invalid values stop the server at startup with a clear message.

| Variable | Default | Effect |
|----------|---------|--------|
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME` | `localhost` / `5432` / `postgres` / — / `school_attendance` | PostgreSQL connection |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `1` / `8` | Connection-pool sizing |
| `AUTO_MIGRATE` | `true` | Apply `migrations/*.sql` at startup |
| `MODE` | `heavy` | `lite` = MobileFaceNet + 320×320 detector (re-enroll after switching) |
| `SIMILARITY_THRESHOLD` | `0.40` | Recognition: cosine score below this → `unknown` |
| `DEDUP_THRESHOLD` | = similarity | Registration: score at/above this → "face already registered" |
| `ONNX_PROVIDERS` | `CPUExecutionProvider` | Comma-separated ORT providers (e.g. `CUDAExecutionProvider,CPUExecutionProvider`) |
| `MODEL_DIR` | `~/.insightface/models` | Directory holding `buffalo_sc/` + `buffalo_l/` |
| `INFERENCE_CONCURRENCY` | `2` | Max inference jobs at once (frames + registrations + camera) |
| `REQUIRED_UPLOAD` / `REQUIRED_VALID` | `15` / `7` | Photos per registration / minimum usable after filtering |
| `REG_MIN_DET_SCORE` / `REG_MIN_FACE_PX` | `0.6` / `64` | Minimum face confidence / size in registration photos |
| `REG_CONSISTENCY_MIN` | `0.35` | Drop registration photos less similar than this to the set's most representative photo |
| `REVEAL_DUPLICATE_MATCH` | `false` | Name the other student in duplicate-face replies |
| `API_KEY` | *(empty)* | Required `X-API-Key` value(s), comma-separated; empty = open (warning logged) |
| `ALLOWED_ORIGINS` | *(empty)* | Comma-separated CORS origins; empty = no cross-origin browser access |
| `MAX_UPLOAD_BYTES` | `10485760` | Max size per uploaded image (10 MB) → else `413` |
| `MAX_REQUEST_BYTES` | `0` (auto) | Whole-request cap; `0` = `REQUIRED_UPLOAD × MAX_UPLOAD_BYTES + 1 MB` |
| `MAX_IMAGE_PIXELS` | `40000000` | Largest image decoded (blocks decompression bombs) → else `400` |
| `LMS_API_URL` | *(empty)* | Detection callback target; empty = events recorded as `skipped` |
| `LMS_API_TOKEN` | *(empty)* | Sent as `Authorization: Bearer …` |
| `LMS_TIMEOUT` / `LMS_MAX_ATTEMPTS` | `5` / `10` | Per-request timeout (s) / attempts before `failed` |
| `ATTENDANCE_TZ` | server local | IANA timezone defining the attendance day (e.g. `Asia/Karachi`) |
| `CAMERA_URL` | *(empty)* | Server-side camera: `0` (webcam), `rtsp://…`, or a video file; empty = none |
| `CAMERA_ID` / `CAMERA_FPS` | `camera-1` / `2` | Label stored with events / frames analysed per second |

---

## ❍ &nbsp; Mode Comparison

```
                  ⚡ LITE                              🎯 HEAVY
                  ──────                               ───────
  Detector    │   SCRFD 500M  · 320×320           │   SCRFD 500M  · 640×640
  Recognizer  │   MobileFaceNet · 13 MB           │   ArcFace R50    · 174 MB
  Embedding   │   512-d                            │   512-d
  Detect (CPU)│   ~24 ms / 720p frame             │   ~39 ms / 720p frame
  Embed (CPU) │   ~15 ms / face                   │   ~250 ms / face
  RAM         │   ~110 MB                          │   ~400 MB
  Accuracy    │   Good (close-range, single face) │   Excellent (small/angled faces)
```

> Timings measured on an Intel Core i7-7600U (4 threads), CPU only. For busy entrances
> with many faces per frame on a modest CPU, prefer lite mode or a GPU.

> **Embeddings from R50 ≠ MobileFaceNet** — they live in different vector spaces. Each
> stored embedding is tagged with its model and only those matching the active `MODE`
> are used (`/api/status` → `ignored_other_model` counts the rest). Switching mode means
> re-enrolling.

---

## ❍ &nbsp; Security Notes

- **Set `API_KEY`.** With it set, every endpoint except `/healthz` and `/api/status`
  requires a matching `X-API-Key` (constant-time comparison). Use a long random value;
  list two keys during a rotation. Left empty, the API is open to anyone who can reach
  it — the server logs a warning at every start.
- **Use TLS.** The server speaks plain HTTP on `0.0.0.0:8000`: run it behind a reverse
  proxy that terminates HTTPS (and can add rate limiting), or keep it on a firewalled LAN.
- **Request limits.** Per-file (`MAX_UPLOAD_BYTES`) and whole-request
  (`MAX_REQUEST_BYTES`) caps return `413`; images larger than `MAX_IMAGE_PIXELS` are
  rejected before decoding, so a tiny "decompression bomb" can't exhaust memory.
  Inference is capped at `INFERENCE_CONCURRENCY` jobs.
- **Biometric data.** Face embeddings are biometric identifiers: restrict DB access, back
  up securely, and use `DELETE /api/students/{reg}` for leavers and erasure requests.
  Duplicate-face replies don't reveal the other student unless `REVEAL_DUPLICATE_MATCH=true`.
- **Supply chain.** Model files are SHA-256-pinned (`pipeline/model_files.py`); CI runs
  `pip-audit` against the pinned dependencies.
- **Camera credentials** live only in `.env` and are masked in logs; `/api/status`
  doesn't expose the camera address.
- **Not covered yet:** liveness / anti-spoofing — a printed photo or a phone screen held
  up to the camera can still mark attendance (see Roadmap).

---

## ❍ &nbsp; Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Only N photo(s) had a detectable face` | Faces small, blurry or not detected | Bright photos, one face filling the frame, looking ahead |
| `… consistently show the same person` | The photo set mixes people or has bad crops | Re-take the set with only the student |
| `unknown` for a known student | Threshold too high, or enrolled under a different `MODE` | Check `/api/status` (`model`, `ignored_other_model`); re-enroll |
| `already_marked` | Already recorded today | Expected — once per student per day |
| `503 service not ready` | PostgreSQL unreachable at startup | Start PostgreSQL; the server retries every 10 s |
| `401 Invalid or missing API key` | `API_KEY` set but header missing/wrong | Send `X-API-Key: <key>` |
| `413 … limit` | Upload larger than `MAX_UPLOAD_BYTES` / `MAX_REQUEST_BYTES` | Smaller images, or raise the limit |
| `400 Invalid image data` | Corrupt image or larger than `MAX_IMAGE_PIXELS` | Send a normal JPEG/PNG |
| LMS isn't receiving detections | `LMS_API_URL` empty/unreachable or LMS erroring | `GET /api/attendance` shows `lms_status` + `lms_last_error`; logs show retries |
| Camera `state: reconnecting` | Wrong RTSP URL/path/credentials, camera offline | Hikvision: path `/Streaming/Channels/101`, LOCAL `admin` account. After 5 failures the worker retries every 15 min so it won't keep the camera locked |
| `Invalid configuration (.env)` at start | A setting has a bad value | The message names the setting and the problem |
| `FileNotFoundError: Model not found` | Models not downloaded | `python download_models.py` (or set `MODEL_DIR`) |

---

## ❍ &nbsp; Roadmap

```
✓  Headless, LMS-integrated API (no UI)
✓  15-photo enrollment: largest-face selection, outlier rejection, averaged embedding
✓  Two-way duplicate rejection (registration number + face), atomic
✓  In-memory cosine recognition (zero DB reads on the hot path)
✓  Privacy-first storage; per-student erasure
✓  Dual model modes (lite / heavy), model-tagged embeddings
✓  Reliable LMS delivery (outbox, retries, survives restarts)
✓  Once-per-day attendance with automatic day rollover
✓  Server-side RTSP camera ingestion
✓  API-key auth with rotation · request/image limits · CI with dependency audit
✓  GPU runtime (configurable ONNX execution providers)
☐  Liveness / anti-spoofing (passive model, tuned on real students)
☐  Multi-camera ingestion (CAMERA_URLS)
☐  Prometheus metrics
☐  OpenCV 5 · psycopg 3 · pgvector for very large schools
```

---

## ❍ &nbsp; Team

A team project — clone, configure your own `.env`, and run locally. Branch naming:
`feature/<short-name>`, `fix/<short-name>`. Open a PR against `main` for review.

<div align="center">

###### ─────────────────────────────────────
###### Built for AI-SATA Technologies · 2026
###### ─────────────────────────────────────

</div>
