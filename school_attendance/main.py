import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import cv2
import numpy as np
import requests
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import MODE, MIN_REGISTRATION_SAMPLES, LMS_API_URL
from database import (
    embedding_cache,
    store_lms_embedding,
    registration_exists,
    find_matching_student,
)
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


async def _notify_lms(registration_number: str) -> None:
    """POST detection event to the LMS API (non-blocking, errors are logged not raised)."""
    if not LMS_API_URL:
        return
    payload = {
        'registration_number': registration_number,
        'detected_at': datetime.now().isoformat(timespec='seconds'),
    }
    try:
        await asyncio.to_thread(
            requests.post, LMS_API_URL, json=payload, timeout=5
        )
    except Exception as exc:
        print(f'[lms] notify failed for {registration_number}: {exc}')


# ─── App + Lifespan ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI):
    count = await asyncio.to_thread(embedding_cache.load)
    print(f'[cache] {count} student embedding(s) loaded into memory')
    yield


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


# ─── Process single frame ──────────────────────────────────────────────────────
@app.post('/api/camera/process-frame')
async def process_frame(
    file: UploadFile = File(...),
):
    """
    Submit a single JPEG frame / image. Notifies the LMS for each recognised
    face and returns the registration number and detection time. Used by
    viewer.py and for manual image-upload testing.
    """
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail='Invalid image data')

    detected_at = datetime.now().isoformat(timespec='seconds')
    results = []
    for face in pipeline.detector.detect(frame):
        aligned = pipeline.detector.align_face(frame, face)
        registration_number, _ = _identify(aligned)
        if registration_number == 'Unknown':
            results.append({
                'status': 'unknown',
            })
            continue
        await _notify_lms(registration_number)
        embedding_cache.remove(registration_number)
        results.append({
            'registration_number': registration_number,
            'status': 'notified',
            'detected_at': detected_at,
        })
    return {
        'faces_detected': len(results),
        'detected_at': detected_at,
        'results': results,
    }


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

    Rejects the request if the registration_number is already registered,
    or if the submitted face is already registered under another number.
    """
    REQUIRED_UPLOAD = 15
    REQUIRED_VALID  = 7

    if len(photos) != REQUIRED_UPLOAD:
        return {
            'success': False,
            'status': 0,
            'message': f'Exactly {REQUIRED_UPLOAD} photos required, received {len(photos)}',
        }

    if registration_exists(registration_number):
        return {
            'success': False,
            'status': 0,
            'message': f'registration_number {registration_number} is already registered',
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

    existing, _ = find_matching_student(avg)
    if existing is not None:
        return {
            'success': False,
            'status': 0,
            'message': f'This face is already registered under registration_number {existing}',
        }

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
