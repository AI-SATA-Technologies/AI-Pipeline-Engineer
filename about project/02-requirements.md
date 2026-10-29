# 2 · Requirements

[← Back to index](README.md)

## Hardware

| | Minimum | Recommended |
|---|---|---|
| CPU | 64-bit x86, 2 cores | 4+ cores (Intel Core i5/i7 8th gen or newer, Ryzen 5) |
| RAM | 4 GB | 8 GB |
| Free disk | 2 GB | 5 GB (room for logs and DB growth) |
| GPU | not needed | optional NVIDIA GPU (CUDA) to speed up heavy mode |

Measured on a 4-thread Intel Core i7-7600U laptop CPU:

| Mode | Process RAM | Per frame | Per face |
|------|------------|-----------|----------|
| Lite | ~110 MB | ~24 ms | ~15 ms |
| Heavy | ~400 MB | ~39 ms | ~250 ms |

So heavy mode on such a CPU handles about 3–4 faces per second. For a busy entrance
(many faces at once) use **lite** mode, a faster CPU, or a GPU (`ONNX_PROVIDERS`).

## Operating system

| OS | Status |
|----|--------|
| Windows 10 / 11 (64-bit) | ✅ Primary target — `setup.bat` and the `.bat` scripts |
| Linux (Ubuntu/Debian) | ✅ Via Docker (see `Dockerfile`), or manual install |
| macOS | ⚠️ Not tested |

## Software

| Software | Version | Notes |
|----------|---------|-------|
| **Python** | **3.11 – 3.14, 64-bit** (3.13 recommended) | Use the **python.org** installer and tick *Add python.exe to PATH*. Avoid the Microsoft Store Python — it is sandboxed and can fail to create the virtual environment. Tested: 3.11 and 3.13. |
| **PostgreSQL** | 12 or newer (tested on 17) | Can be on the same PC or another server. The DB user needs permission to create the database once (the `postgres` user can). |
| Git | any | Optional — only if you clone instead of copying the folder |
| Docker | 24+ | Optional — only for container deployment |

Python packages are installed automatically by `setup.bat` from
`school_attendance/requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.162.0 | Web framework (the API) |
| uvicorn | 0.54.0 | Web server that runs the API |
| python-multipart | 0.0.32 | Parses photo uploads |
| python-dotenv | 1.2.4 | Reads `.env` |
| pydantic-settings | 2.16.1 | Validates the settings |
| psycopg2-binary | 2.9.13 | PostgreSQL driver |
| numpy | 2.4.6 | Maths for embeddings |
| opencv-python | 4.14.0.94 | Image decoding, camera/RTSP reading |
| onnxruntime | 1.31.0 | Runs the face models |
| httpx | 0.28.1 | Sends attendance to the LMS |
| tzdata | 2026.5 | Time-zone data on Windows |

Development extras (`requirements-dev.txt`): pytest, ruff, pip-audit.

## Face models

Downloaded once by `setup.bat` (via `download_models.py`) from the official InsightFace
GitHub release, and verified with SHA-256 checksums.

| File | Size | Used for |
|------|------|----------|
| `buffalo_sc/det_500m.onnx` | 2.5 MB | Face detection (both modes) |
| `buffalo_sc/w600k_mbf.onnx` | 13 MB | Recognition — lite mode |
| `buffalo_l/w600k_r50.onnx` | 174 MB | Recognition — heavy mode |

Default location: `C:\Users\<you>\.insightface\models\` (setting `MODEL_DIR`). The first
download is about 300 MB (the zip files contain extra models, which are deleted).

## Network

| Direction | Port / host | Why | When |
|-----------|-------------|-----|------|
| Inbound | TCP **8000** | The LMS (and viewer) call the API | Always |
| Outbound | TCP 5432 → PostgreSQL | Database | Always (local if same PC) |
| Outbound | TCP **554** → camera IP | RTSP video stream | If `CAMERA_URL` is set |
| Outbound | HTTPS → your LMS | Deliver attendance | If `LMS_API_URL` is set |
| Outbound | HTTPS → pypi.org, files.pythonhosted.org | Install packages | During setup only |
| Outbound | HTTPS → github.com | Download face models | During setup only |

Allow port 8000 through Windows Firewall so the LMS can reach the server (command in
[Setup → after setup](03-setup.md#after-setup)).

## Camera

- Any IP camera that streams **RTSP** (H.264/H.265) — e.g. Hikvision, Dahua — or a USB
  webcam, or a video file for testing.
- Mounted so students face it, at roughly head height, with even lighting and faces at
  least ~64 pixels wide in the image.
- You need the camera's **local** login (usually `admin`) — not a cloud/app account.
  See [Camera setup](07-camera-setup.md).

## Path length (Windows)

Keep the project in a **short folder path** (≤ 120 characters), e.g. `C:\Attendance`.
Some Python packages have deep folders and Windows limits full paths to 260
characters. `setup.bat` checks this and tells you what to do.
