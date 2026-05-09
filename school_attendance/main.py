import asyncio
import io
import csv
import os
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import (
    LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD, SIMILARITY_THRESHOLD,
    FAISS_INDEX_PATH, FAISS_NAMES_PATH, MIN_REGISTRATION_SAMPLES
)
from database import get_db_connection
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer
from pipeline.attendance_logic import mark_attendance, get_student_id_by_name

app = FastAPI(title='School Face Attendance System', version='1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

print("Loading face detector (SCRFD 500M)...")
detector = FaceDetector()

liveness: Optional[LivenessDetector] = None
if os.path.exists(LIVENESS_MODEL_PATH):
    print(f"Loading liveness model: {LIVENESS_MODEL_PATH}")
    liveness = LivenessDetector(LIVENESS_MODEL_PATH, threshold=LIVENESS_THRESHOLD)
else:
    print(f"WARNING: Liveness model not found at '{LIVENESS_MODEL_PATH}'.")
    print("  Run 'python setup_liveness.py' to set it up. System will run without liveness check.")

print("Loading face recognizer (ArcFace R50)...")
recognizer = FaceRecognizer(
    threshold=SIMILARITY_THRESHOLD,
    index_path=FAISS_INDEX_PATH,
    names_path=FAISS_NAMES_PATH,
)

os.makedirs('static', exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/', response_class=HTMLResponse)
async def root():
    return '<meta http-equiv="refresh" content="0; url=/static/index.html">'


@app.get('/api/status')
def status():
    return {
        'status': 'running',
        'liveness_enabled': liveness is not None,
        'students_in_index': recognizer.index.ntotal,
    }


@app.post('/api/process-frame')
async def process_frame(
    file: UploadFile = File(...),
    camera_id: str = Form('cam_01'),
):
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail='Invalid image data')

    results = []
    faces = detector.detect(frame)

    for face in faces:
        crop = detector.crop_face(frame, face)

        live_score = 1.0
        if liveness:
            is_live, live_score = liveness.check(crop)
            if not is_live:
                results.append({'status': 'spoof', 'live_score': round(live_score, 3)})
                continue

        name, confidence = recognizer.identify(crop)
        if name == 'Unknown':
            results.append({'status': 'unknown', 'confidence': round(confidence, 3)})
            continue

        student_id = get_student_id_by_name(name)
        if student_id is None:
            results.append({'status': 'db_missing', 'name': name})
            continue

        marked = mark_attendance(student_id, confidence, camera_id)
        results.append({
            'name': name,
            'status': 'marked' if marked else 'already_marked',
            'confidence': round(confidence, 3),
            'live_score': round(live_score, 3),
        })

    return {'faces_detected': len(faces), 'results': results}


@app.post('/api/register')
async def register_student(
    name: str = Form(...),
    roll_number: str = Form(...),
    class_name: str = Form(...),
    section: str = Form(''),
    photos: list[UploadFile] = File(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM students WHERE roll_number=%s', (roll_number,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return {'success': False, 'error': 'Roll number already registered'}

    embeddings = []
    for photo in photos:
        data = await photo.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        faces = detector.detect(img)
        if not faces:
            continue
        crop = detector.crop_face(img, faces[0])

        if liveness:
            is_live, _ = liveness.check(crop)
            if not is_live:
                continue

        emb = recognizer.get_embedding(crop)
        if emb is not None:
            embeddings.append(emb)

    if len(embeddings) < MIN_REGISTRATION_SAMPLES:
        cursor.close()
        conn.close()
        return {
            'success': False,
            'error': f'Only {len(embeddings)} valid face samples found. Need at least {MIN_REGISTRATION_SAMPLES}.',
        }

    cursor.execute(
        'INSERT INTO students (name, roll_number, class_name, section) VALUES (%s, %s, %s, %s)',
        (name, roll_number, class_name, section),
    )
    student_id = cursor.lastrowid
    cursor.execute(
        'INSERT INTO embeddings (student_id, sample_count) VALUES (%s, %s)',
        (student_id, len(embeddings)),
    )
    conn.commit()
    cursor.close()
    conn.close()

    recognizer.add_student(name, embeddings)
    return {'success': True, 'student_id': student_id, 'samples_used': len(embeddings)}


@app.get('/api/attendance')
def get_attendance(date_str: Optional[str] = None, class_name: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = '''
        SELECT s.name, s.roll_number, s.class_name, s.section,
               a.date, a.marked_at, a.confidence, a.camera_id
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE 1=1
    '''
    params = []
    if date_str:
        query += ' AND a.date = %s'
        params.append(date_str)
    if class_name:
        query += ' AND s.class_name = %s'
        params.append(class_name)
    query += ' ORDER BY a.marked_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    for row in rows:
        if row.get('date'):
            row['date'] = str(row['date'])
        if row.get('marked_at'):
            row['marked_at'] = str(row['marked_at'])
    cursor.close()
    conn.close()
    return rows


@app.get('/api/attendance/export')
def export_attendance(date_str: str):
    rows = get_attendance(date_str)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=attendance_{date_str}.csv'},
    )


@app.get('/api/students')
def get_students(class_name: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = 'SELECT id, name, roll_number, class_name, section, registered_at FROM students WHERE is_active=1'
    params = []
    if class_name:
        query += ' AND class_name = %s'
        params.append(class_name)
    query += ' ORDER BY name'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    for row in rows:
        if row.get('registered_at'):
            row['registered_at'] = str(row['registered_at'])
    cursor.close()
    conn.close()
    return rows


@app.delete('/api/student/{student_id}')
def delete_student(student_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE students SET is_active=0 WHERE id=%s', (student_id,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    if affected == 0:
        raise HTTPException(status_code=404, detail='Student not found')
    return {'success': True}


@app.websocket('/ws/stream')
async def video_stream(websocket: WebSocket):
    await websocket.accept()
    cap = cv2.VideoCapture(0)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            faces = detector.detect(frame)
            for face in faces:
                x1, y1, x2, y2 = face.bbox.astype(int)
                crop = detector.crop_face(frame, face)

                if liveness:
                    is_live, ls = liveness.check(crop)
                    if not is_live:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv2.putText(frame, 'SPOOF', (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        continue

                name, conf = recognizer.identify(crop)
                color = (0, 255, 0) if name != 'Unknown' else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f'{name} {conf:.0%}' if name != 'Unknown' else 'Unknown'
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            await websocket.send_bytes(buf.tobytes())
            await asyncio.sleep(0.04)
    except Exception:
        pass
    finally:
        cap.release()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
