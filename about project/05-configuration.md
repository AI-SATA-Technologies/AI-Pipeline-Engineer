# 5 · Configuration (`.env`)

[← Back to index](README.md)

All settings live in `school_attendance/.env` (created from `.env.example`). They are
**checked when the server starts**: a wrong value stops it with a message naming the
setting. A blank value (`NAME=`) means "use the default". Restart the server after
changing `.env`.

## Database

| Setting | Default | Meaning |
|---------|---------|---------|
| `DB_HOST` | `localhost` | PostgreSQL server address |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `postgres` | Login |
| `DB_PASS` | *(empty)* | Password |
| `DB_NAME` | `school_attendance` | Database name |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `1` / `8` | Open connections kept / maximum |
| `AUTO_MIGRATE` | `true` | Create/update tables automatically at startup |

## Face recognition

| Setting | Default | Meaning |
|---------|---------|---------|
| `MODE` | `heavy` | `heavy` = most accurate; `lite` = ~15× faster per face, less accurate. **Changing it means re-registering everyone** |
| `SIMILARITY_THRESHOLD` | `0.40` | How similar a face must be (−1…1) to count as a match. Higher = fewer false matches, more "unknown" |
| `DEDUP_THRESHOLD` | = `SIMILARITY_THRESHOLD` | Similarity at which a new registration counts as an already-registered face |
| `ONNX_PROVIDERS` | `CPUExecutionProvider` | Hardware to run the models on. NVIDIA GPU: `CUDAExecutionProvider,CPUExecutionProvider` (needs the GPU build of onnxruntime) |
| `MODEL_DIR` | `~/.insightface/models` | Folder with the model files |
| `INFERENCE_CONCURRENCY` | `2` | Max face-analysis jobs at the same time |

## Registration

| Setting | Default | Meaning |
|---------|---------|---------|
| `REQUIRED_UPLOAD` | `15` | Photos the LMS must send |
| `REQUIRED_VALID` | `7` | Good photos needed after filtering |
| `REG_MIN_DET_SCORE` | `0.6` | Minimum face-detection confidence in a photo |
| `REG_MIN_FACE_PX` | `64` | Minimum face width/height in pixels |
| `REG_CONSISTENCY_MIN` | `0.35` | Photos less similar than this to the set's most typical photo are dropped |
| `REVEAL_DUPLICATE_MATCH` | `false` | If `true`, a duplicate-face rejection names the other student (privacy risk) |

## Security and limits

| Setting | Default | Meaning |
|---------|---------|---------|
| `API_KEY` | *(empty)* | Key the LMS must send as `X-API-Key`. Several keys separated by commas are all accepted (for changing keys without downtime). **Empty = API open to anyone on the network** |
| `ALLOWED_ORIGINS` | *(empty)* | Websites allowed to call the API from a browser (comma-separated). Usually not needed (the LMS calls server-to-server) |
| `MAX_UPLOAD_BYTES` | `10485760` | Max size of one image (10 MB) |
| `MAX_REQUEST_BYTES` | `0` = automatic | Max size of a whole request (default 15 × 10 MB + 1 MB) |
| `MAX_IMAGE_PIXELS` | `40000000` | Max image resolution decoded (blocks "decompression bomb" files) |

## LMS

| Setting | Default | Meaning |
|---------|---------|---------|
| `LMS_API_URL` | *(empty)* | Where attendance is POSTed. Empty = recorded locally only (`lms_status: skipped`) |
| `LMS_API_TOKEN` | *(empty)* | Sent as `Authorization: Bearer <token>` if the LMS requires it |
| `LMS_TIMEOUT` | `5` | Seconds to wait for the LMS |
| `LMS_MAX_ATTEMPTS` | `10` | Attempts before an event is marked `failed` |

## Attendance day

| Setting | Default | Meaning |
|---------|---------|---------|
| `ATTENDANCE_TZ` | this PC's timezone | Timezone that defines "today", e.g. `Asia/Karachi`, `Asia/Dubai`, `Europe/London` |

## Camera

| Setting | Default | Meaning |
|---------|---------|---------|
| `CAMERA_URL` | *(empty)* | Camera the server reads itself: `0` = webcam, `rtsp://…` = IP camera, a file path = video. Empty = no camera worker |
| `CAMERA_ID` | `camera-1` | Name saved with each attendance event (`source`) |
| `CAMERA_FPS` | `2` | Frames analysed per second |

Details and examples: [Camera setup](07-camera-setup.md).

## Example: a typical school PC

```env
DB_HOST=localhost
DB_USER=postgres
DB_PASS=MyStrongDbPassword
DB_NAME=school_attendance

MODE=heavy
ATTENDANCE_TZ=Asia/Karachi

API_KEY=Xq3...generated-by-setup...9Lw
LMS_API_URL=https://lms.myschool.edu/api/attendance

CAMERA_URL=rtsp://admin:CameraPass@192.168.18.234:554/Streaming/Channels/101
CAMERA_ID=main-gate
CAMERA_FPS=2
```

## Settings that no longer exist

`MIN_REGISTRATION_SAMPLES` (from v1/v2) is ignored; the server logs a notice if it's
still in `.env`. Use `REQUIRED_VALID` instead.
