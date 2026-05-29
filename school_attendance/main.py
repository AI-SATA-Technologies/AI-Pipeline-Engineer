import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import cv2
import numpy as np
import requests
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from auth import require_api_key
from config import (
    MODE, LMS_API_URL, ALLOWED_ORIGINS, MAX_UPLOAD_BYTES,
    REQUIRED_UPLOAD, REQUIRED_VALID,
)
from database import (
    embedding_cache,
    dedup_index,
    store_lms_embedding,
    registration_exists,
    find_matching_student,
    StorageError,
)
from pipeline.detector import FaceDetector
from pipeline.recognizer import FaceRecognizer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('attendance')


# ─── Pipeline ─────────────────────────────────────────────────────────────────
class Pipeline:
    def __init__(self):
        self.detector = FaceDetector(mode=MODE)
        self.recognizer = FaceRecognizer(mode=MODE)
        logger.info('%s pipeline ready', MODE.upper())

    def embed_frame(self, data: bytes) -> list[np.ndarray | None]:
        """Decode + detect + embed every face in a frame (CPU-bound; run in a thread).
        Returns one entry per detected face, preserving order (None if unusable)."""
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('invalid image data')
        out = []
        for face in self.detector.detect(frame):
            aligned = self.detector.align_face(frame, face)
            out.append(self.recognizer.get_embedding(aligned))
        return out

    def embed_photos(self, blobs: list[bytes]) -> list[np.ndarray]:
        """Extract one embedding per registration photo that has a usable face."""
        embeddings = []
        for data in blobs:
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            faces = self.detector.detect(img)
            if not faces:
                continue
            aligned = self.detector.align_face(img, faces[0])
            emb = self.recognizer.get_embedding(aligned)
            if emb is not None:
                embeddings.append(emb)
        return embeddings


pipeline = Pipeline()


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _read_limited(file: UploadFile) -> bytes:
    """Read an upload, rejecting anything over MAX_UPLOAD_BYTES."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f'File exceeds {MAX_UPLOAD_BYTES}-byte limit')
    return data


async def _notify_lms(registration_number: str, detected_at: str) -> None:
    """POST a detection event to the LMS API (non-blocking; errors logged, not raised)."""
    if not LMS_API_URL:
        return
    payload = {'registration_number': registration_number, 'detected_at': detected_at}
    try:
        await asyncio.to_thread(requests.post, LMS_API_URL, json=payload, timeout=5)
    except Exception as exc:
        logger.warning('LMS notify failed for %s: %s', registration_number, exc)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ─── App + Lifespan ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        n_cache = await asyncio.to_thread(embedding_cache.load)
        await asyncio.to_thread(dedup_index.load)
        logger.info('%d student embedding(s) loaded into memory', n_cache)
    except StorageError as exc:
        logger.error('startup DB load failed (server will start anyway): %s', exc)
    yield


app = FastAPI(title='School Face Attendance API', version='3.1', lifespan=lifespan)

# CORS is opt-in: only enabled when ALLOWED_ORIGINS is configured.
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=['*'],
        allow_headers=['*'],
    )


# ─── Status ───────────────────────────────────────────────────────────────────
@app.get('/api/status')
def status():
    return {
        'status': 'running',
        'mode': MODE,
        'students_pending': len(embedding_cache),
        'registered_total': len(dedup_index),
    }


# ─── Process single frame ──────────────────────────────────────────────────────
@app.post('/api/camera/process-frame', dependencies=[Depends(require_api_key)])
async def process_frame(file: UploadFile = File(...)):
    """
    Submit a single JPEG frame / image. Notifies the LMS for each recognised face
    and returns the registration number and detection time. Used by viewer.py and
    for manual image-upload testing.
    """
    data = await _read_limited(file)
    try:
        embeddings = await asyncio.to_thread(pipeline.embed_frame, data)
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid image data')

    detected_at = _now_utc()
    results = []
    for emb in embeddings:
        reg = embedding_cache.claim(emb) if emb is not None else None
        if reg is None:
            results.append({'status': 'unknown'})
            continue
        await _notify_lms(reg, detected_at)
        results.append({
            'registration_number': reg,
            'status': 'notified',
            'detected_at': detected_at,
        })
    return {
        'faces_detected': len(results),
        'detected_at': detected_at,
        'results': results,
    }


# ─── Register student (LMS integration) ───────────────────────────────────────
@app.post('/api/register/lms', dependencies=[Depends(require_api_key)])
async def register_from_lms(
    registration_number: str = Form(...),
    photos: list[UploadFile] = File(..., alias='photos[]'),
):
    """
    Register a student from the LMS. Requires exactly REQUIRED_UPLOAD images in a
    single array (key: photos[]); at least REQUIRED_VALID must contain a detectable
    face. Returns status 1 on success, 0 on failure.

    Rejects the request if the registration_number is already registered, or if the
    submitted face is already registered under another number.
    """
    if len(photos) != REQUIRED_UPLOAD:
        return {
            'success': False, 'status': 0,
            'message': f'Exactly {REQUIRED_UPLOAD} photos required, received {len(photos)}',
        }

    try:
        if registration_exists(registration_number):
            return {
                'success': False, 'status': 0,
                'message': f'registration_number {registration_number} is already registered',
            }
    except StorageError:
        raise HTTPException(status_code=503, detail='storage unavailable')

    blobs = [await _read_limited(p) for p in photos]
    embeddings = await asyncio.to_thread(pipeline.embed_photos, blobs)

    if len(embeddings) < REQUIRED_VALID:
        return {
            'success': False, 'status': 0,
            'message': f'Only {len(embeddings)} photo(s) had a detectable face, '
                       f'at least {REQUIRED_VALID} required',
        }

    avg = np.mean(embeddings, axis=0).astype(np.float32)
    avg /= np.linalg.norm(avg)

    existing, _ = find_matching_student(avg)
    if existing is not None:
        return {
            'success': False, 'status': 0,
            'message': f'This face is already registered under registration_number {existing}',
        }

    try:
        store_lms_embedding(registration_number, avg, len(embeddings))
    except StorageError:
        raise HTTPException(status_code=503, detail='storage unavailable')

    embedding_cache.add(registration_number, avg)
    dedup_index.add(registration_number, avg)
    logger.info('registered %s (%d valid samples)', registration_number, len(embeddings))

    return {'success': True, 'status': 1, 'message': 'Face registered successfully'}


# ─── Cache reload (new attendance day) ─────────────────────────────────────────
@app.post('/api/cache/reload', dependencies=[Depends(require_api_key)])
async def reload_cache():
    """Reload all embeddings from PostgreSQL — repopulates the detect-once
    attendance cache for a new day without restarting the server."""
    try:
        n_cache = await asyncio.to_thread(embedding_cache.load)
        n_dedup = await asyncio.to_thread(dedup_index.load)
    except StorageError:
        raise HTTPException(status_code=503, detail='storage unavailable')
    return {'reloaded': True, 'students_pending': n_cache, 'registered_total': n_dedup}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
