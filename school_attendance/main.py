import asyncio
import os
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse

from config import MODE, LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD, MIN_REGISTRATION_SAMPLES
from database import (
    store_embedding,
    identify_face,
    embedding_exists,
    count_registered_students,
)
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer

app = FastAPI(
    title='LMS Face Attendance API',
    version='4.0',
    description='Minimal face attendance system. Stores only LMS student_id + embedding.',
)
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


def _get_embedding(aligned: np.ndarray) -> Optional[np.ndarray]:
    """Get normalized ArcFace embedding from an aligned face crop."""
    emb = pipeline.recognizer.get_embedding(aligned)
    if emb is None:
        return None
    emb = emb.astype(np.float32)
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 0 else emb


def _identify(aligned: np.ndarray) -> tuple[str | None, float]:
    """Embed face then search DB. Returns (lms_student_id | None, confidence)."""
    emb = _get_embedding(aligned)
    if emb is None:
        return None, 0.0
    return identify_face(emb)


# ─── Status ───────────────────────────────────────────────────────────────────

@app.get('/api/status', summary='System health check')
def status():
    return {
        'status': 'running',
        'mode': MODE,
        'liveness_enabled': liveness is not None,
        'registered_students': count_registered_students(),
    }


# ─── LMS: Register student ────────────────────────────────────────────────────

@app.post('/api/lms/register', summary='Register a student from LMS')
async def lms_register(
    student_id: str = Form(..., description='Unique student ID from the LMS'),
    images: list[UploadFile] = File(..., description='15 face photos of the student'),
):
    """
    Receive a student_id (from LMS) + face images.
    Generates ArcFace embeddings, averages them, and stores:
      - lms_student_id
      - averaged 512-dim embedding (normalized)

    Nothing else is stored (no name, no class, no roll number).
    Requires at least MIN_REGISTRATION_SAMPLES valid face detections.
    """
    if not student_id or not student_id.strip():
        raise HTTPException(status_code=400, detail='student_id cannot be empty.')

    student_id = student_id.strip()

    embeddings = []
    failed_images = 0

    for img_file in images:
        data = await img_file.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            failed_images += 1
            continue

        faces = pipeline.detector.detect(img)
        if not faces:
            failed_images += 1
            continue

        aligned = pipeline.detector.align_face(img, faces[0])
        emb = _get_embedding(aligned)
        if emb is not None:
            embeddings.append(emb)
        else:
            failed_images += 1

    if len(embeddings) < MIN_REGISTRATION_SAMPLES:
        return {
            'success': False,
            'student_id': student_id,
            'error': (
                f'Only {len(embeddings)} valid face(s) detected from {len(images)} image(s). '
                f'Need at least {MIN_REGISTRATION_SAMPLES}.'
            ),
            'samples_found': len(embeddings),
            'failed_images': failed_images,
        }

    # Average all valid embeddings and re-normalize
    avg = np.mean(embeddings, axis=0).astype(np.float32)
    norm = np.linalg.norm(avg)
    avg = avg / norm if norm > 0 else avg

    store_embedding(student_id, avg, len(embeddings))

    return {
        'success': True,
        'student_id': student_id,
        'samples_used': len(embeddings),
        'failed_images': failed_images,
        'overwritten': embedding_exists(student_id),  # True means it was updated
    }


# ─── LMS: Attend — single frame recognition ───────────────────────────────────

@app.post('/api/lms/attend', summary='Identify a face and return student_id + status')
async def lms_attend(
    file: UploadFile = File(..., description='JPEG frame from camera'),
):
    """
    Submit a single camera frame (JPEG).
    Returns the matched LMS student_id and status=1 if recognized,
    or student_id=null and status=0 if unknown.

    Response:
      {"student_id": "STU-001", "status": 1, "confidence": 0.87}
      {"student_id": null,      "status": 0, "confidence": 0.21}
    """
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail='Invalid image data.')

    faces = pipeline.detector.detect(frame)
    if not faces:
        return {'student_id': None, 'status': 0, 'confidence': 0.0, 'detail': 'No face detected'}

    # Use the largest / most prominent face
    aligned = pipeline.detector.align_face(frame, faces[0])
    student_id, confidence = _identify(aligned)

    return {
        'student_id': student_id,
        'status': 1 if student_id is not None else 0,
        'confidence': round(confidence, 4),
    }


# ─── Camera: MJPEG HTTP stream (view only) ───────────────────────────────────

@app.get('/api/camera/stream', summary='Live MJPEG camera feed (view only)')
async def camera_stream():
    """
    MJPEG live feed with face detection overlays.
    View only — does NOT mark attendance.
    Use as: <img src="http://host:8000/api/camera/stream">
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
                    sid, conf = _identify(aligned)
                    label = f'{sid} {conf:.0%}' if sid else f'Unknown {conf:.0%}'
                    color = (0, 255, 0) if sid else (0, 165, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
                await asyncio.sleep(0.04)
        finally:
            cap.release()

    return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')


# ─── Camera: WebSocket stream (auto-identify, no DB writes) ──────────────────

@app.websocket('/ws/camera')
async def camera_ws(websocket: WebSocket):
    """
    WebSocket live feed.
    Binary messages : JPEG frame bytes.
    Text messages   : JSON recognition events.
      {"student_id": "STU-001", "status": 1, "confidence": 0.92}
      {"student_id": null,      "status": 0, "confidence": 0.18}
    """
    await websocket.accept()
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    for _ in range(8):
        cap.read()  # camera warmup

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
                sid, conf = _identify(aligned)
                label = f'{sid} {conf:.0%}' if sid else f'Unknown {conf:.0%}'
                color = (0, 255, 0) if sid else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                try:
                    import json
                    await websocket.send_text(json.dumps({
                        'student_id': sid,
                        'status': 1 if sid else 0,
                        'confidence': round(float(conf), 4),
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


if __name__ == '__main__':
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
