# 1 · Overview

[← Back to index](README.md)

## What it is

The **School Face Attendance API** is a backend service that marks student attendance
by face recognition. It has **no user interface** of its own: the school's existing
**LMS** (Learning Management System) talks to it over HTTP.

| The service is responsible for | The LMS is responsible for |
|-------------------------------|----------------------------|
| Detecting and recognizing faces | Student records, classes, timetables |
| Storing one face embedding per student | Showing / reporting attendance |
| Recording each detection once per day | Deciding what a detection means (present, late…) |
| Delivering detections to the LMS reliably | Receiving `{registration_number, detected_at}` |

## How it works

### 1. Registration (once per student)

1. The LMS sends the student's `registration_number` and **15 photos**.
2. In each photo the service finds the **largest clear face**, aligns it to 112×112
   pixels, and turns it into a **512-number embedding** (a mathematical description of
   the face).
3. Photos that don't match the rest (a different person, a bad crop) are dropped. At
   least **7** good photos must remain.
4. The good embeddings are averaged into one embedding for the student.
5. It is rejected if the registration number **or the face** is already registered.
6. Only the embedding is stored — **the photos are never saved**.

### 2. Recognition (all day)

1. Frames arrive from the **camera worker** (the server reads the IP camera itself) or
   from a client posting images to `/api/camera/process-frame`.
2. Every face in the frame is embedded and compared against the students **not yet
   marked today** (an in-memory list; comparison is one fast matrix multiplication).
3. A match above `SIMILARITY_THRESHOLD` (default 0.40) marks the student: the event is
   written to the `attendance_events` table and the student is removed from today's
   pending list, so they're recorded only **once per day**.

### 3. Delivery to the LMS

1. A background **outbox** sends each new event to `LMS_API_URL`.
2. If the LMS is down, slow or returns an error, it retries: 5 s, 10 s, 20 s … up to
   10 minutes apart, for up to 10 attempts. Pending events survive a server restart.
3. Each event's status (`pending`, `sent`, `failed`, `skipped`) is visible through
   `GET /api/attendance`.

### 4. A new day

At midnight (in `ATTENDANCE_TZ`) the pending list is rebuilt with every registered
student, so everyone can be marked again. Restarting the server mid-day does **not**
re-notify students already marked that day.

```
 LMS ──(15 photos)──► register ──► embedding ──► PostgreSQL
                                                     │ load at start / new day
 IP camera ─► camera worker ─┐                       ▼
 client ─► /process-frame ───┴─► recognize ──► pending list ──► attendance_events
                                                                    │
                                                outbox (retries) ◄──┘
                                                     │
                                                     ▼
                                                    LMS
```

## Main components

| Component | File | What it does |
|-----------|------|--------------|
| Web API | `main.py` | HTTP endpoints, startup/shutdown, background tasks |
| Attendance service | `attendance.py` | Recognition → recording; registration rules |
| Camera worker | `camera_worker.py` | Reads the RTSP camera / webcam / video file |
| LMS outbox | `lms.py` | Delivers events to the LMS with retries |
| Database layer | `database.py` | PostgreSQL access, migrations, in-memory face lists |
| Face pipeline | `pipeline/` | Detection (SCRFD), alignment, recognition (ArcFace) |
| Settings | `config.py` + `.env` | All configuration, validated at startup |

## Two modes

| | ⚡ Lite | 🎯 Heavy (default) |
|---|---|---|
| Detector | SCRFD 500M at 320×320 | SCRFD 500M at 640×640 |
| Recognizer | MobileFaceNet (13 MB) | ArcFace ResNet-50 (174 MB) |
| Speed* | ~24 ms/frame + ~15 ms/face | ~39 ms/frame + ~250 ms/face |
| Memory* | ~110 MB | ~400 MB |
| Best for | Low-end PCs, many faces per frame | Best accuracy, small or angled faces |

\* Measured on an Intel Core i7-7600U (4 threads), CPU only.

> Embeddings from the two models are **not compatible**. Choose a mode before
> registering students; switching later means every student must register again.

## What is stored

| Data | Where | Notes |
|------|-------|-------|
| Face embedding (512 numbers) per student | `student_face_embeddings` | Plus registration number, photo count, model name |
| One row per student per day they were seen | `attendance_events` | Time, camera/source, score, LMS delivery status |
| Photos / video frames | **nowhere** | Processed in memory and discarded |

## Current limitations

- **No liveness / anti-spoofing yet** — a printed photo or a phone screen held up to
  the camera could mark attendance. Planned as a later phase.
- One camera per server (`CAMERA_URL`); more cameras can post frames to the API.
- Must run as a **single process** (one uvicorn worker), because today's pending list
  lives in memory.
