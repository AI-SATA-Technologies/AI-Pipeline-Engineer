# 6 · API Reference

[← Back to index](README.md)

Base URL: `http://<server-ip>:8000`. Interactive docs (try requests in the browser):
`http://<server-ip>:8000/docs`.

## Authentication

When `API_KEY` is set in `.env`, every endpoint except `/healthz` and `/api/status`
needs the header:

```
X-API-Key: <the API_KEY value>
```

Missing or wrong key → `401 {"detail": "Invalid or missing API key"}`.

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/healthz` | – | Is the process running? |
| `GET` | `/api/status` | – | Readiness, counts, LMS backlog, camera state |
| `POST` | `/api/register/lms` | key | Register a student (15 photos) |
| `POST` | `/api/camera/process-frame` | key | Recognize faces in one image and record attendance |
| `GET` | `/api/attendance` | key | Attendance for a day + LMS delivery status |
| `DELETE` | `/api/students/{registration_number}` | key | Delete a student's face data |
| `POST` | `/api/cache/reload` | key | Reload students from the database |

Until the database has loaded once after startup, the keyed endpoints return
`503 {"detail": "service not ready: database unavailable"}`.

---

### `GET /healthz`

```json
{ "status": "ok" }
```

### `GET /api/status`

```json
{
  "status": "running",
  "ready": true,
  "db_ok": true,
  "mode": "heavy",
  "model": "w600k_r50",
  "attendance_date": "2026-10-24",
  "students_pending": 42,
  "registered_total": 1280,
  "ignored_other_model": 0,
  "lms_enabled": true,
  "lms_pending": 0,
  "camera": { "id": "main-gate", "state": "running", "frames_processed": 5120,
              "last_frame_at": "2026-10-24T03:15:00+00:00", "last_error": null }
}
```

| Field | Meaning |
|-------|---------|
| `ready` | Students are loaded; endpoints accept requests |
| `students_pending` | Registered students not yet seen today |
| `registered_total` | All registered students (for the current `MODE`) |
| `ignored_other_model` | Students registered under the other `MODE` (must re-register) |
| `lms_pending` | Events waiting to be delivered to the LMS |
| `camera.state` | `connecting`, `running`, `reconnecting` or `stopped`; `null` if no camera |

---

### `POST /api/register/lms`

`multipart/form-data` with:

| Field | Type | Rules |
|-------|------|-------|
| `registration_number` | text | 1–100 characters, no control characters; spaces at the ends are trimmed |
| `photos[]` | 15 files | JPEG/PNG, each ≤ 10 MB; the student's face clearly visible |

```bash
curl -X POST http://localhost:8000/api/register/lms \
  -H "X-API-Key: $API_KEY" \
  -F "registration_number=2026-CS-001" \
  -F "photos[]=@1.jpg" -F "photos[]=@2.jpg"   # … 15 files in total
```

PowerShell (7+):

```powershell
$form = @{ registration_number = '2026-CS-001'; 'photos[]' = (Get-ChildItem .\photos\*.jpg) }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/register/lms `
  -Headers @{ 'X-API-Key' = $env:API_KEY } -Form $form
```

Success (HTTP 200):

```json
{ "success": true, "status": 1, "message": "Face registered successfully" }
```

Failures are also HTTP 200 with `"status": 0` and a `message`:

| `message` | Meaning |
|-----------|---------|
| `Exactly 15 photos required, received N` | Wrong number of files |
| `registration_number is required` / `… at most 100 characters` / `… invalid characters` | Bad number |
| `registration_number X is already registered` | Delete the student first to re-register |
| `Only N photo(s) had a detectable face, at least 7 required` | Faces too small, blurry, dark or missing |
| `Only N of M photos consistently show the same person, at least 7 required` | Photos of more than one person, or bad crops |
| `This face is already registered under another registration_number` | The same person is registered under a different number |

Other responses: `401` (key), `413` (file/request too large), `503` (database down).

---

### `POST /api/camera/process-frame`

`multipart/form-data` with `file` = one JPEG/PNG (≤ 10 MB).

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

| `status` | Meaning |
|----------|---------|
| `notified` | Newly marked present; queued for the LMS |
| `already_marked` | Recognized, but already marked earlier today (nothing sent) |
| `unknown` | Face not recognized |
| `error` | Recognized but couldn't be saved (database problem) — will be marked on a later frame |

`bbox` = `[x1, y1, x2, y2]` in pixels. Times are UTC. Other responses: `400` (not a valid
image, or larger than `MAX_IMAGE_PIXELS`), `401`, `413`, `503`.

---

### `GET /api/attendance?date=YYYY-MM-DD`

`date` is optional (default: today in `ATTENDANCE_TZ`).

```bash
curl "http://localhost:8000/api/attendance?date=2026-10-24" -H "X-API-Key: $API_KEY"
```

```json
{
  "date": "2026-10-24",
  "count": 1,
  "events": [
    { "registration_number": "2026-CS-001", "detected_at": "2026-10-24T08:30:00+05:00",
      "source": "main-gate", "score": 0.6312,
      "lms_status": "sent", "lms_attempts": 1, "lms_last_error": null }
  ]
}
```

`lms_status`: `pending` (waiting/retrying), `sent`, `failed` (gave up — see
[Operations](08-operations.md#lms-delivery-problems)), `skipped` (no `LMS_API_URL`).

---

### `DELETE /api/students/{registration_number}`

Deletes the student's face embedding (for a student who leaves, a re-registration, or a
data-erasure request). Their attendance history is kept.

```bash
curl -X DELETE http://localhost:8000/api/students/2026-CS-001 -H "X-API-Key: $API_KEY"
```

`200 {"deleted": true, "registration_number": "2026-CS-001"}` · `404` if not registered.

---

### `POST /api/cache/reload`

Reloads the students from the database — only needed if the database was edited by
hand. Students already marked today stay marked; the new day starts automatically.

```json
{ "reloaded": true, "students_pending": 1280, "registered_total": 1280 }
```

---

## What the LMS receives

For every new attendance event the server POSTs JSON to `LMS_API_URL`:

```http
POST /api/attendance HTTP/1.1
Content-Type: application/json
Authorization: Bearer <LMS_API_TOKEN>        (only if LMS_API_TOKEN is set)

{ "registration_number": "2026-CS-001", "detected_at": "2026-10-24T03:30:00+00:00" }
```

The LMS should:

- reply with any **2xx** status when it has stored the event — anything else (or no reply
  within `LMS_TIMEOUT` seconds) is retried;
- be **idempotent**: in rare cases (e.g. the LMS stored the event but its reply was lost)
  the same event may arrive twice — store at most one record per student per
  `detected_at` / day;
- treat `detected_at` as UTC (ISO-8601 with `+00:00`).
