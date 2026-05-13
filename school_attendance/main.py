import asyncio
import io
import csv
import os
import json
import time
from datetime import date as dt
from typing import Optional

import cv2
import numpy as np
import psycopg2.extras
from fastapi import FastAPI, File, UploadFile, Form, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import MODE, LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD, MIN_REGISTRATION_SAMPLES
from database import (
    get_db_connection,
    mark_attendance,
    get_student_id_by_name,
    identify_face,
    store_embedding,
    count_registered_students,
)
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer

app = FastAPI(title='School Face Attendance API', version='3.0')
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
    """Get embedding then search pgvector."""
    emb = pipeline.recognizer.get_embedding(aligned)
    if emb is None:
        return 'Unknown', 0.0
    return identify_face(emb)


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
    WebSocket live feed with automatic attendance marking.
    Binary messages : JPEG frame bytes (render as video).
    Text messages   : JSON attendance events.
      {"type": "attendance", "name": "...", "status": "marked|already_marked", "confidence": 0.92}
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
                name, conf = _identify(aligned)
                color = (0, 255, 0) if name != 'Unknown' else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f'{name} {conf:.0%}', (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                now = time.time()
                if name != 'Unknown' and now - recent_marks.get(name, 0) > COOLDOWN:
                    recent_marks[name] = now
                    sid = get_student_id_by_name(name)
                    if sid:
                        marked = mark_attendance(sid, conf, 'ws_camera')
                        try:
                            await websocket.send_text(json.dumps({
                                'type': 'attendance',
                                'name': name,
                                'status': 'marked' if marked else 'already_marked',
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
    camera_id: str = Form('cam_01'),
):
    """
    Submit a single JPEG frame. Returns detected faces and attendance results.
    Use for edge devices / IP cameras that send frames on their own schedule.
    """
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail='Invalid image data')

    results = []
    for face in pipeline.detector.detect(frame):
        aligned = pipeline.detector.align_face(frame, face)
        name, confidence = _identify(aligned)
        if name == 'Unknown':
            results.append({'status': 'unknown', 'confidence': round(confidence, 3)})
            continue
        sid = get_student_id_by_name(name)
        if sid is None:
            results.append({'status': 'db_missing', 'name': name})
            continue
        marked = mark_attendance(sid, confidence, camera_id)
        results.append({
            'name': name,
            'status': 'marked' if marked else 'already_marked',
            'confidence': round(confidence, 3),
        })
    return {'faces_detected': len(results), 'results': results}


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


# ─── Attendance ────────────────────────────────────────────────────────────────
@app.get('/api/attendance')
def get_attendance(date_str: Optional[str] = None, class_name: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = '''
        SELECT s.name, s.roll_number, s.class_name, s.section,
               a.date, a.marked_at, a.confidence, a.camera_id
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE 1=1
    '''
    params = []
    if date_str:
        query += ' AND a.date=%s'; params.append(date_str)
    if class_name:
        query += ' AND s.class_name=%s'; params.append(class_name)
    cursor.execute(query + ' ORDER BY a.marked_at DESC', params)
    rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        if r.get('date'): r['date'] = str(r['date'])
        if r.get('marked_at'): r['marked_at'] = str(r['marked_at'])
    cursor.close(); conn.close()
    return rows


@app.get('/api/attendance/export')
def export_attendance(date_str: str):
    rows = get_attendance(date_str)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        output, media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=attendance_{date_str}.csv'},
    )


# ─── Statistics ────────────────────────────────────────────────────────────────
@app.get('/api/stats')
def get_stats(date_str: Optional[str] = None, class_name: Optional[str] = None):
    """Attendance summary for a date (defaults to today). Includes per-class breakdown."""
    target_date = date_str or str(dt.today())
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    q_total = 'SELECT COUNT(*) AS total FROM students WHERE is_active=TRUE'
    p_total: list = []
    if class_name:
        q_total += ' AND class_name=%s'; p_total.append(class_name)
    cursor.execute(q_total, p_total)
    total = cursor.fetchone()['total']

    q_present = '''
        SELECT COUNT(DISTINCT a.student_id) AS present
        FROM attendance a JOIN students s ON a.student_id = s.id
        WHERE a.date=%s AND s.is_active=TRUE
    '''
    p_present = [target_date]
    if class_name:
        q_present += ' AND s.class_name=%s'; p_present.append(class_name)
    cursor.execute(q_present, p_present)
    present = cursor.fetchone()['present']

    cursor.execute('''
        SELECT s.class_name,
               COUNT(DISTINCT s.id)          AS total,
               COUNT(DISTINCT a.student_id)  AS present
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id AND a.date=%s
        WHERE s.is_active=TRUE
        GROUP BY s.class_name ORDER BY s.class_name
    ''', [target_date])
    by_class = [dict(r) for r in cursor.fetchall()]

    cursor.close(); conn.close()
    absent = total - present
    return {
        'date': target_date,
        'total_students': total,
        'present': present,
        'absent': absent,
        'attendance_rate': round(present / total * 100, 1) if total else 0.0,
        'by_class': by_class,
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
