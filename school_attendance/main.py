import asyncio
import io
import csv
import os
import json
import random
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import (
    MODE, LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD, SIMILARITY_THRESHOLD,
    faiss_paths, MIN_REGISTRATION_SAMPLES,
)
from database import get_db_connection
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer
from pipeline.attendance_logic import mark_attendance, get_student_id_by_name

app = FastAPI(title='School Face Attendance System', version='2.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


# ─── Pipeline state (mode-switchable) ────────────────────────────────────
class Pipeline:
    def __init__(self, mode: str):
        self.mode = mode
        idx_path, names_path = faiss_paths(mode)
        print(f"[pipeline] Loading {mode.upper()} mode...")
        self.detector = FaceDetector(mode=mode)
        self.recognizer = FaceRecognizer(
            mode=mode, threshold=SIMILARITY_THRESHOLD,
            index_path=idx_path, names_path=names_path,
        )
        print(f"[pipeline] {mode.upper()} ready. Students in index: {self.recognizer.index.ntotal}")


pipeline = Pipeline(MODE)

# Passive anti-spoof model — used inside challenge flow
liveness: Optional[LivenessDetector] = None
if os.path.exists(LIVENESS_MODEL_PATH):
    print(f"[pipeline] Loading liveness model: {LIVENESS_MODEL_PATH}")
    liveness = LivenessDetector(LIVENESS_MODEL_PATH, threshold=LIVENESS_THRESHOLD)

# Lazy-loaded landmark extractor (only when challenges are run)
_landmark_extractor = None
def get_landmark_extractor():
    global _landmark_extractor
    if _landmark_extractor is None:
        from pipeline.challenges import LandmarkExtractor
        print("[pipeline] Loading 106-point landmark model...")
        _landmark_extractor = LandmarkExtractor()
    return _landmark_extractor


os.makedirs('static', exist_ok=True)
os.makedirs('embeddings', exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')


# ─── Static / status ─────────────────────────────────────────────────────
@app.get('/', response_class=HTMLResponse)
async def root():
    return '<meta http-equiv="refresh" content="0; url=/static/index.html">'


@app.get('/api/status')
def status():
    return {
        'status': 'running',
        'mode': pipeline.mode,
        'liveness_enabled': liveness is not None,
        'students_in_index': pipeline.recognizer.index.ntotal,
    }


@app.get('/api/mode')
def get_mode():
    return {'mode': pipeline.mode}


@app.post('/api/mode')
def set_mode(mode: str = Form(...)):
    global pipeline
    mode = mode.lower()
    if mode not in ('lite', 'heavy'):
        raise HTTPException(status_code=400, detail='mode must be "lite" or "heavy"')
    if mode == pipeline.mode:
        return {'mode': pipeline.mode, 'changed': False}
    pipeline = Pipeline(mode)
    return {'mode': pipeline.mode, 'changed': True,
            'students_in_index': pipeline.recognizer.index.ntotal}


# ─── Process-frame (used by camera_client.py) ────────────────────────────
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
    faces = pipeline.detector.detect(frame)

    for face in faces:
        aligned = pipeline.detector.align_face(frame, face)
        name, confidence = pipeline.recognizer.identify(aligned)
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
        })

    return {'faces_detected': len(faces), 'results': results}


# ─── Registration: produce embeddings for BOTH modes ────────────────────
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
        cursor.close(); conn.close()
        return {'success': False, 'error': 'Roll number already registered'}

    # Lazy-load the OTHER mode's recognizer so registration covers both indices
    other_mode = 'lite' if pipeline.mode == 'heavy' else 'heavy'
    other_idx, other_names = faiss_paths(other_mode)
    other_recognizer = FaceRecognizer(
        mode=other_mode, threshold=SIMILARITY_THRESHOLD,
        index_path=other_idx, names_path=other_names,
    )

    embeddings_active = []
    embeddings_other = []
    for photo in photos:
        data = await photo.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        faces = pipeline.detector.detect(img)
        if not faces:
            continue
        aligned = pipeline.detector.align_face(img, faces[0])

        e1 = pipeline.recognizer.get_embedding(aligned)
        e2 = other_recognizer.get_embedding(aligned)
        if e1 is not None:
            embeddings_active.append(e1)
        if e2 is not None:
            embeddings_other.append(e2)

    if len(embeddings_active) < MIN_REGISTRATION_SAMPLES:
        cursor.close(); conn.close()
        return {
            'success': False,
            'error': f'Only {len(embeddings_active)} valid face samples found. Need at least {MIN_REGISTRATION_SAMPLES}.',
        }

    cursor.execute(
        'INSERT INTO students (name, roll_number, class_name, section) VALUES (%s, %s, %s, %s)',
        (name, roll_number, class_name, section),
    )
    student_id = cursor.lastrowid
    cursor.execute(
        'INSERT INTO embeddings (student_id, sample_count) VALUES (%s, %s)',
        (student_id, len(embeddings_active)),
    )
    conn.commit()
    cursor.close(); conn.close()

    pipeline.recognizer.add_student(name, embeddings_active)
    if embeddings_other:
        other_recognizer.add_student(name, embeddings_other)

    return {
        'success': True,
        'student_id': student_id,
        'samples_used': len(embeddings_active),
        'mode_active': pipeline.mode,
        'cross_mode_samples': len(embeddings_other),
    }


# ─── Attendance read endpoints ───────────────────────────────────────────
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
        query += ' AND a.date = %s'; params.append(date_str)
    if class_name:
        query += ' AND s.class_name = %s'; params.append(class_name)
    query += ' ORDER BY a.marked_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    for row in rows:
        if row.get('date'): row['date'] = str(row['date'])
        if row.get('marked_at'): row['marked_at'] = str(row['marked_at'])
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


@app.get('/api/students')
def get_students(class_name: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = 'SELECT id, name, roll_number, class_name, section, registered_at FROM students WHERE is_active=1'
    params = []
    if class_name:
        query += ' AND class_name = %s'; params.append(class_name)
    query += ' ORDER BY name'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    for row in rows:
        if row.get('registered_at'): row['registered_at'] = str(row['registered_at'])
    cursor.close(); conn.close()
    return rows


@app.delete('/api/student/{student_id}')
def delete_student(student_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE students SET is_active=0 WHERE id=%s', (student_id,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close(); conn.close()
    if affected == 0:
        raise HTTPException(status_code=404, detail='Student not found')
    return {'success': True}


# ─── Live preview WebSocket (no attendance marking, just feed) ───────────
@app.websocket('/ws/stream')
async def video_stream(websocket: WebSocket):
    await websocket.accept()
    cap = cv2.VideoCapture(0)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            faces = pipeline.detector.detect(frame)
            for face in faces:
                x1, y1, x2, y2 = face.bbox.astype(int)
                aligned = pipeline.detector.align_face(frame, face)
                name, conf = pipeline.recognizer.identify(aligned)
                color = (0, 255, 0) if name != 'Unknown' else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f'{name} {conf:.0%}' if name != 'Unknown' else f'Unknown {conf:.2f}'
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            await websocket.send_bytes(buf.tobytes())
            await asyncio.sleep(0.04)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws/stream] error: {e}")
    finally:
        cap.release()


# ─── Challenge verification WebSocket ────────────────────────────────────
@app.websocket('/ws/verify')
async def verify_stream(websocket: WebSocket):
    """Active liveness with random challenges, then identify + mark attendance."""
    await websocket.accept()

    # Pick 2 random challenges
    pool = ['blink', 'smile', 'turn_left', 'turn_right']
    challenges_seq = random.sample(pool, 2)

    from pipeline.challenges import compute_metrics, make_challenge
    extractor = get_landmark_extractor()

    cap = cv2.VideoCapture(0)
    cv_state = {
        'idx': 0,
        'challenge': make_challenge(challenges_seq[0]),
        'started_at': time.time(),
        'live_score_avg': [],
        'identified_name': None,
        'identified_conf': 0.0,
    }
    timeout_per_challenge = 12.0    # seconds
    final_done = False

    async def send(obj):
        try: await websocket.send_text(json.dumps(obj))
        except Exception: pass

    await send({'type': 'init', 'challenges': challenges_seq})

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Detect (cheap) — used for box + crop for liveness
            faces = pipeline.detector.detect(frame)
            face_box = None
            if faces:
                face = faces[0]
                x1, y1, x2, y2 = face.bbox.astype(int)
                face_box = [int(x1), int(y1), int(x2), int(y2)]

                # Passive anti-spoof
                if liveness:
                    crop = pipeline.detector.crop_face(frame, face)
                    _, ls = liveness.check(crop)
                    cv_state['live_score_avg'].append(ls)

            # Active liveness via 106-point landmarks
            lm = extractor.get_landmarks(frame)
            metrics = compute_metrics(lm) if lm is not None else {}

            if not final_done:
                ch = cv_state['challenge']
                if metrics:
                    ch.update(metrics)

                elapsed = time.time() - cv_state['started_at']
                if ch.passed:
                    cv_state['idx'] += 1
                    if cv_state['idx'] >= len(challenges_seq):
                        # All passed → identify
                        if faces:
                            aligned = pipeline.detector.align_face(frame, faces[0])
                            n, c = pipeline.recognizer.identify(aligned)
                            cv_state['identified_name'] = n
                            cv_state['identified_conf'] = float(c)
                            if n != 'Unknown':
                                sid = get_student_id_by_name(n)
                                if sid:
                                    mark_attendance(sid, c, 'verify')
                        avg_live = float(np.mean(cv_state['live_score_avg'])) if cv_state['live_score_avg'] else 1.0
                        spoof_blocked = liveness is not None and avg_live < LIVENESS_THRESHOLD
                        await send({
                            'type': 'done',
                            'success': cv_state['identified_name'] not in (None, 'Unknown') and not spoof_blocked,
                            'name': cv_state['identified_name'],
                            'confidence': round(cv_state['identified_conf'], 4),
                            'avg_live_score': round(avg_live, 4),
                            'spoof_blocked': spoof_blocked,
                        })
                        final_done = True
                    else:
                        cv_state['challenge'] = make_challenge(challenges_seq[cv_state['idx']])
                        cv_state['started_at'] = time.time()
                elif elapsed > timeout_per_challenge:
                    await send({
                        'type': 'done', 'success': False,
                        'reason': f'timeout on challenge: {challenges_seq[cv_state["idx"]]}'
                    })
                    final_done = True

            # Encode + send the frame WITH overlay box
            if face_box:
                cv2.rectangle(frame, (face_box[0], face_box[1]), (face_box[2], face_box[3]), (0, 200, 255), 2)

            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            try:
                await websocket.send_bytes(buf.tobytes())
            except Exception:
                break

            # Send progress update
            await send({
                'type': 'progress',
                'current_index': cv_state['idx'] if not final_done else len(challenges_seq),
                'current_challenge': challenges_seq[cv_state['idx']] if cv_state['idx'] < len(challenges_seq) else None,
                'label': cv_state['challenge'].label if cv_state['idx'] < len(challenges_seq) and not final_done else None,
                'metrics': {k: round(v, 4) for k, v in metrics.items()} if metrics else None,
            })

            if final_done:
                await asyncio.sleep(1.0)
                break

            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws/verify] error: {e}")
    finally:
        cap.release()
        try: await websocket.close()
        except Exception: pass


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
