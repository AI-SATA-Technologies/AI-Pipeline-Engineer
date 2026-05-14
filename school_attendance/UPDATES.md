# LMS Face Attendance System — Update Documentation

**Project:** School Attendance System  
**Update Version:** 4.0  
**Date:** 2026-05-14  
**Server:** `http://192.168.0.102:8000`

---

## Overview

The system was refactored from a standalone school attendance app into a **minimal LMS-integrated face recognition API**. The core goal: store only what is necessary — the **LMS student ID** and their **face embedding**. Nothing else.

---

## Changes Summary

### 1. Database — `schema.sql`

**Before:** Three tables — `students`, `attendance`, `embeddings` — storing names, roll numbers, class info, attendance logs, etc.

**After:** Single table only:

```sql
CREATE TABLE student_embeddings (
    lms_student_id  VARCHAR(100)  PRIMARY KEY,
    vector          LONGBLOB      NOT NULL,
    sample_count    INT           DEFAULT 0,
    registered_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
```

- New database name: `lms_attendance` (was `school_attendance`)
- No student names, roll numbers, class names, or attendance records
- Only the LMS-provided student ID and the averaged ArcFace embedding are stored

---

### 2. Configuration — `config.py`

| Setting | Before | After |
|---|---|---|
| `DB_NAME` default | `school_attendance` | `lms_attendance` |

All other settings (`DB_HOST`, `DB_USER`, `DB_PASS`, `MODE`, thresholds) remain unchanged.

---

### 3. Database Layer — `database.py`

**Before:** Functions for attendance marking, student lookup by name, joining multiple tables.

**After:** Clean, minimal functions:

| Function | Purpose |
|---|---|
| `store_embedding(lms_student_id, embedding, sample_count)` | Save or overwrite a student's embedding |
| `embedding_exists(lms_student_id)` | Check if a student is already registered |
| `identify_face(embedding)` | Cosine similarity search — returns `(lms_student_id or None, confidence)` |
| `count_registered_students()` | Count total registered students |
| `get_db_connection()` | MySQL connection helper |

**Key change:** `identify_face()` now returns the **LMS student ID** (not a name) or `None` if unrecognized.

---

### 4. API — `main.py`

**Before:** Endpoints for student CRUD, attendance logs, CSV export, statistics, and camera streams.

**After:** Focused LMS integration endpoints:

#### New: `POST /api/lms/register`
Registers a student from the LMS.

| Input | Type | Required |
|---|---|---|
| `student_id` | string (form field) | Yes |
| `images` | list of JPEG uploads | Yes (min 5 valid faces) |

**What it does:**
1. Receives `student_id` + up to 15+ images from LMS
2. Detects a face in each image
3. Generates a 512-dim ArcFace embedding per valid image
4. Averages all embeddings and L2-normalizes the result
5. Stores `(lms_student_id, averaged_embedding)` in MySQL

**Response:**
```json
{"success": true, "student_id": "STU-001", "samples_used": 13, "failed_images": 2}
```

---

#### New: `POST /api/lms/attend`
Identifies a face from a single camera frame.

| Input | Type |
|---|---|
| `file` | JPEG image (single camera frame) |

**What it does:**
1. Receives one JPEG frame
2. Detects a face
3. Generates embedding
4. Runs cosine similarity against all stored embeddings
5. Returns matched student ID and status

**Response (recognized):**
```json
{"student_id": "STU-001", "status": 1, "confidence": 0.87}
```

**Response (unknown face):**
```json
{"student_id": null, "status": 0, "confidence": 0.21}
```

---

#### Kept: `GET /api/status`
Returns server health and registered student count.

#### Kept: `GET /api/camera/stream`
Live MJPEG camera feed with face detection overlays (view only, no DB writes).

#### Kept: `WebSocket /ws/camera`
Live WebSocket stream — sends JPEG frames + JSON recognition events:
```json
{"student_id": "STU-001", "status": 1, "confidence": 0.92}
```

#### Removed:
- `POST /api/register` (old student registration)
- `GET /api/students`, `DELETE /api/students/{id}`
- `GET /api/attendance`, `GET /api/attendance/export`
- `GET /api/stats`
- `POST /api/camera/process-frame`

---

### 5. Minor Code Fixes — `main.py`

Two `# pyrefly: ignore [missing-import]` comments added (by user) for linting compatibility:
- Before `from fastapi.responses import StreamingResponse`
- Before `import uvicorn` in the `__main__` block

---

## Architecture Flow

```
REGISTRATION:
LMS --> POST /api/lms/register --> [student_id + 15 images]
                                        |
                              Face detect + ArcFace embed
                                        |
                              Average + L2-normalize --> 512-dim vector
                                        |
                              MySQL: INSERT INTO student_embeddings
                                        |
                              <-- {success: true, student_id, samples_used}

ATTENDANCE:
Camera frame --> POST /api/lms/attend --> [JPEG image]
                                              |
                                    Face detect + embed
                                              |
                                    Cosine similarity vs DB
                                              |
                              <-- {student_id: "STU-001", status: 1}
                              <-- {student_id: null, status: 0}
```

---

## API Reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/status` | GET | Server health + student count |
| `/api/lms/register` | POST | Register student (ID + images) |
| `/api/lms/attend` | POST | Identify face from camera frame |
| `/api/camera/stream` | GET | Live MJPEG preview |
| `/ws/camera` | WebSocket | Live recognition stream |

**Swagger UI:** `http://192.168.0.102:8000/docs`

---

## Files Changed

| File | Change Type | Summary |
|---|---|---|
| `schema.sql` | Rewritten | Single-table minimal schema |
| `config.py` | Modified | `DB_NAME` default updated |
| `database.py` | Rewritten | Minimal functions, ID-based search |
| `main.py` | Rewritten | LMS endpoints, removed old CRUD |
