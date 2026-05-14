import asyncio
import os
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
import psycopg2.extras
import requests
from fastapi import FastAPI, File, UploadFile, Form, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import MODE, LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD, MIN_REGISTRATION_SAMPLES, LMS_API_URL
from database import (
    get_db_connection,
    embedding_cache,
    store_embedding,
    store_lms_embedding,
    count_registered_students,
)
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer

@asynccontextmanager
async def lifespan(_: FastAPI):
    count = await asyncio.to_thread(embedding_cache.load)
    print(f'[cache] {count} student embedding(s) loaded into memory')
    yield


app = FastAPI(title='School Face Attendance API', version='3.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


# ─── Pipeline ─────────────────────────────────────────────────────────────────
class Pipeline:
    def __init__(self):
        self.detector = FaceDetector(mode=MODE)
        self.recognizer = FaceRecognizer(mode=MODE)
        print(f'[pipeline] {MODE.upper()} ready')


pipeline = Pipeline()

liveness: Optional[LivenessDetector] = None
if os.path.exists(LIVENESS_MODEL_PATH):
    liveness = LivenessDetector(LIVENESS_MODEL_PATH, threshold=LIVENESS_THRESHOLD)
    print('[pipeline] Liveness model loaded')


def _identify(aligned: np.ndarray) -> tuple[str, float]:
    emb = pipeline.recognizer.get_embedding(aligned)
    if emb is None:
        return 'Unknown', 0.0
    return embedding_cache.search(emb)


async def _notify_lms(student_id: str) -> None:
    """POST detection event to the LMS API (non-blocking, errors are logged not raised)."""
    if not LMS_API_URL:
        return
    payload = {
        'student_id': student_id,
        'detected_at': datetime.now().isoformat(timespec='seconds'),
    }
    try:
        await asyncio.to_thread(
            requests.post, LMS_API_URL, json=payload, timeout=5
        )
    except Exception as exc:
        print(f'[lms] notify failed for {student_id}: {exc}')


# ─── Status ───────────────────────────────────────────────────────────────────
@app.get('/api/status')
def status():
    return {
        'status': 'running',
        'mode': MODE,
        'liveness_enabled': liveness is not None,
        'students_in_db': count_registered_students(),
    }


# ─── Camera: MJPEG HTTP stream ────────────────────────────────────────────────
@app.get('/api/camera/stream')
async def camera_stream():
    """
    MJPEG live feed with face detection overlays (view only — no attendance marking).
    Consume as:  <img src="http://host:8000/api/camera/stream">
    """
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    async def gen():
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                for face in pipeline.detector.detect(frame):
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    aligned = pipeline.detector.align_face(frame, face)
                    name, conf = _identify(aligned)
                    color = (0, 255, 0) if name != 'Unknown' else (0, 165, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f'{name} {conf:.0%}', (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
                await asyncio.sleep(0.04)
        finally:
            cap.release()

    return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')


# ─── Camera: WebSocket stream ─────────────────────────────────────────────────
@app.websocket('/ws/camera')
async def camera_ws(websocket: WebSocket):
    """
    WebSocket live feed with automatic LMS notification on detection.
    Binary messages : JPEG frame bytes (render as video).
    Text messages   : JSON detection events.
      {"type": "detection", "student_id": "...", "confidence": 0.92}
    """
    await websocket.accept()
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    for _ in range(8):
        cap.read()  # camera warmup

    recent_marks: dict[str, float] = {}
    COOLDOWN = 30.0
    miss = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                miss += 1
                if miss >= 10:
                    break
                await asyncio.sleep(0.05)
                continue
            miss = 0

            for face in pipeline.detector.detect(frame):
                x1, y1, x2, y2 = face.bbox.astype(int)
                aligned = pipeline.detector.align_face(frame, face)
                student_id, conf = _identify(aligned)
                color = (0, 255, 0) if student_id != 'Unknown' else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f'{student_id} {conf:.0%}', (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                now = time.time()
                if student_id != 'Unknown' and now - recent_marks.get(student_id, 0) > COOLDOWN:
                    recent_marks[student_id] = now
                    await _notify_lms(student_id)
                    embedding_cache.remove(student_id)
                    try:
                        await websocket.send_text(json.dumps({
                            'type': 'detection',
                            'student_id': student_id,
                            'confidence': round(float(conf), 3),
                        }))
                    except Exception:
                        pass

            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            await websocket.send_bytes(buf.tobytes())
            await asyncio.sleep(0.04)
    except WebSocketDisconnect:
        pass
    finally:
        cap.release()


# ─── Process single frame ──────────────────────────────────────────────────────
@app.post('/api/camera/process-frame')
async def process_frame(
    file: UploadFile = File(...),
):
    """
    Submit a single JPEG frame. Notifies the LMS for each recognised face.
    Use for edge devices / IP cameras that send frames on their own schedule.
    """
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail='Invalid image data')

    results = []
    for face in pipeline.detector.detect(frame):
        aligned = pipeline.detector.align_face(frame, face)
        student_id, confidence = _identify(aligned)
        if student_id == 'Unknown':
            results.append({'status': 'unknown', 'confidence': round(confidence, 3)})
            continue
        await _notify_lms(student_id)
        embedding_cache.remove(student_id)
        results.append({
            'student_id': student_id,
            'status': 'notified',
            'confidence': round(confidence, 3),
        })
    return {'faces_detected': len(results), 'results': results}


# ─── Register student (LMS integration) ───────────────────────────────────────
@app.post('/api/register/lms')
async def register_from_lms(
    student_id: str = Form(...),
    photos: list[UploadFile] = File(...),
):
    """
    Register a student from the LMS.
    Accepts the LMS-issued unique student_id and exactly 15 photos.
    The ML pipeline only processes pixel data; student_id is stored as-is
    and never passed to the face detector or recognizer.
    """
    if len(photos) != 15:
        raise HTTPException(
            status_code=400,
            detail=f'Exactly 15 photos required, got {len(photos)}.',
        )

    embeddings = []
    failed = 0
    for photo in photos:
        data = await photo.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            failed += 1
            continue
        faces = pipeline.detector.detect(img)
        if not faces:
            failed += 1
            continue
        aligned = pipeline.detector.align_face(img, faces[0])
        emb = pipeline.recognizer.get_embedding(aligned)
        if emb is not None:
            embeddings.append(emb)
        else:
            failed += 1

    if len(embeddings) < MIN_REGISTRATION_SAMPLES:
        return {
            'success': False,
            'error': (
                f'Only {len(embeddings)} valid face(s) extracted from {len(photos)} photos. '
                f'Need at least {MIN_REGISTRATION_SAMPLES}.'
            ),
        }

    avg = np.mean(embeddings, axis=0).astype(np.float32)
    avg /= np.linalg.norm(avg)

    # Persist to PostgreSQL — only student_id + embedding vector, never the images
    store_lms_embedding(student_id, avg, len(embeddings))
    # Mirror into the in-memory cache so detection is instant without a reload
    embedding_cache.add(student_id, avg)

    return {
        'success': True,
        'student_id': student_id,
        'samples_used': len(embeddings),
        'photos_failed': failed,
    }


# ─── Register student ──────────────────────────────────────────────────────────
@app.post('/api/register')
async def register_student(
    name: str = Form(...),
    roll_number: str = Form(...),
    class_name: str = Form(...),
    section: str = Form(''),
    photos: list[UploadFile] = File(...),
):
    """
    Register a new student with face photos.
    Detects faces, computes ArcFace embeddings, averages them,
    and stores the single 512-dim vector in PostgreSQL via pgvector.
    Requires at least MIN_REGISTRATION_SAMPLES valid face detections.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM students WHERE roll_number=%s', (roll_number,))
    if cursor.fetchone():
        cursor.close(); conn.close()
        return {'success': False, 'error': 'Roll number already registered'}

    embeddings = []
    for photo in photos:
        data = await photo.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        faces = pipeline.detector.detect(img)
        if not faces:
            continue
        aligned = pipeline.detector.align_face(img, faces[0])
        emb = pipeline.recognizer.get_embedding(aligned)
        if emb is not None:
            embeddings.append(emb)

    if len(embeddings) < MIN_REGISTRATION_SAMPLES:
        cursor.close(); conn.close()
        return {
            'success': False,
            'error': (
                f'Only {len(embeddings)} valid face samples found. '
                f'Need at least {MIN_REGISTRATION_SAMPLES}.'
            ),
        }

    cursor.execute(
        'INSERT INTO students (name, roll_number, class_name, section) VALUES (%s, %s, %s, %s) RETURNING id',
        (name, roll_number, class_name, section),
    )
    student_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close(); conn.close()

    avg = np.mean(embeddings, axis=0).astype(np.float32)
    avg /= np.linalg.norm(avg)
    store_embedding(student_id, avg, len(embeddings))

    return {'success': True, 'student_id': student_id, 'samples_used': len(embeddings)}


# ─── Students ──────────────────────────────────────────────────────────────────
@app.get('/api/students')
def get_students(class_name: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = ('SELECT id, name, roll_number, class_name, section, registered_at '
             'FROM students WHERE is_active=TRUE')
    params = []
    if class_name:
        query += ' AND class_name=%s'; params.append(class_name)
    cursor.execute(query + ' ORDER BY name', params)
    rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        if r.get('registered_at'): r['registered_at'] = str(r['registered_at'])
    cursor.close(); conn.close()
    return rows


@app.delete('/api/students/{student_id}')
def delete_student(student_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE students SET is_active=FALSE WHERE id=%s', (student_id,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close(); conn.close()
    if not affected:
        raise HTTPException(status_code=404, detail='Student not found')
    return {'success': True}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
