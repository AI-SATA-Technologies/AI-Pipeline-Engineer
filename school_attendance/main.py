import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
import requests
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import MODE, MIN_REGISTRATION_SAMPLES, LMS_API_URL, CAMERA_URL
from database import embedding_cache, store_lms_embedding
from pipeline.detector import FaceDetector
from pipeline.recognizer import FaceRecognizer


# ─── Pipeline ─────────────────────────────────────────────────────────────────
class Pipeline:
    def __init__(self):
        self.detector = FaceDetector(mode=MODE)
        self.recognizer = FaceRecognizer(mode=MODE)
        print(f'[pipeline] {MODE.upper()} ready')


pipeline = Pipeline()


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


def _process_frame_sync(frame: np.ndarray) -> list[tuple[str, float]]:
    """Detect and identify all known faces in one frame. Runs in a thread pool."""
    out = []
    for face in pipeline.detector.detect(frame):
        aligned = pipeline.detector.align_face(frame, face)
        student_id, conf = _identify(aligned)
        if student_id != 'Unknown':
            out.append((student_id, conf))
    return out


# ─── Camera background task ───────────────────────────────────────────────────

_camera_state: dict = {'running': False, 'connected': False}


async def _camera_loop() -> None:
    """
    Connects to CAMERA_URL and processes every frame indefinitely.
    Auto-reconnects on stream loss. Runs for the full server lifetime.
    """
    RECONNECT_DELAY = 5.0
    COOLDOWN = 30.0
    recent_marks: dict[str, float] = {}
    cap: Optional[cv2.VideoCapture] = None
    miss = 0

    _camera_state['running'] = True
    try:
        while True:
            if cap is None or not cap.isOpened():
                _camera_state['connected'] = False
                print(f'[camera] connecting -> {CAMERA_URL}')
                cap = await asyncio.to_thread(lambda: cv2.VideoCapture(CAMERA_URL))
                if not cap.isOpened():
                    print(f'[camera] connection failed, retry in {RECONNECT_DELAY}s')
                    cap = None
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue
                miss = 0
                _camera_state['connected'] = True
                print('[camera] connected')

            ret, frame = await asyncio.to_thread(cap.read)
            if not ret:
                miss += 1
                if miss >= 10:
                    print('[camera] stream lost, reconnecting')
                    cap.release()
                    cap = None
                    await asyncio.sleep(RECONNECT_DELAY)
                else:
                    await asyncio.sleep(0.05)
                continue
            miss = 0

            detections = await asyncio.to_thread(_process_frame_sync, frame)
            now = time.time()
            for student_id, conf in detections:
                if now - recent_marks.get(student_id, 0) > COOLDOWN:
                    recent_marks[student_id] = now
                    await _notify_lms(student_id)
                    embedding_cache.remove(student_id)
                    print(f'[camera] marked {student_id} ({conf:.1%})')

            await asyncio.sleep(0)

    except asyncio.CancelledError:
        pass
    finally:
        _camera_state['running'] = False
        _camera_state['connected'] = False
        if cap and cap.isOpened():
            cap.release()
        print('[camera] background task stopped')


# ─── App + Lifespan ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI):
    count = await asyncio.to_thread(embedding_cache.load)
    print(f'[cache] {count} student embedding(s) loaded into memory')

    cam_task = None
    if CAMERA_URL != '' and CAMERA_URL is not None:
        cam_task = asyncio.create_task(_camera_loop())
        print(f'[camera] background task started -> {CAMERA_URL}')
    else:
        print('[camera] CAMERA_URL not set — background task disabled')

    yield

    if cam_task:
        cam_task.cancel()
        try:
            await cam_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title='School Face Attendance API', version='3.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


# ─── Status ───────────────────────────────────────────────────────────────────
@app.get('/api/status')
def status():
    return {
        'status': 'running',
        'mode': MODE,
        'students_pending': len(embedding_cache),
    }


# ─── Camera status ────────────────────────────────────────────────────────────
@app.get('/api/camera/status')
def camera_status():
    return {
        'task_running': _camera_state['running'],
        'connected': _camera_state['connected'],
        'url_configured': CAMERA_URL != '' and CAMERA_URL is not None,
        'students_pending': len(embedding_cache),
    }


# ─── Process single frame ──────────────────────────────────────────────────────
@app.post('/api/camera/process-frame')
async def process_frame(
    file: UploadFile = File(...),
):
    """
    Submit a single JPEG frame. Notifies the LMS for each recognised face.
    Use for edge devices / IP cameras that push frames on their own schedule.
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
    registration_number: str = Form(...),
    photos: list[UploadFile] = File(..., alias='photos[]'),
):
    """
    Register a student from the LMS.
    Requires exactly 15 images in a single array (key: photos[]).
    At least 7 must contain a detectable face — blurry or faceless images
    are skipped automatically. Returns status 1 on success, 0 on failure.
    """
    REQUIRED_UPLOAD = 15
    REQUIRED_VALID  = 7

    if len(photos) != REQUIRED_UPLOAD:
        return {
            'success': False,
            'status': 0,
            'message': f'Exactly {REQUIRED_UPLOAD} photos required, received {len(photos)}',
        }

    embeddings = []
    for image in photos:
        data = await image.read()
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

    if len(embeddings) < REQUIRED_VALID:
        return {
            'success': False,
            'status': 0,
            'message': f'Only {len(embeddings)} photo(s) had a detectable face, '
                       f'at least {REQUIRED_VALID} required',
        }

    avg = np.mean(embeddings, axis=0).astype(np.float32)
    avg /= np.linalg.norm(avg)

    store_lms_embedding(registration_number, avg, len(embeddings))
    embedding_cache.add(registration_number, avg)

    return {
        'success': True,
        'status': 1,
        'message': 'Face registered successfully',
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
