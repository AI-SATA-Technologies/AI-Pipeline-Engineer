import config  # noqa: F401  (must be first: sets OpenCV limits before cv2 is imported)

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, UTC

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import database
import lms
from attendance import AttendanceService, today
from auth import require_api_key
from camera_worker import CameraWorker
from config import (
    ALLOWED_ORIGINS, API_KEYS, CAMERA_FPS, CAMERA_ID, CAMERA_URL, MAX_REQUEST_BYTES,
    MAX_UPLOAD_BYTES, MODE, OBSOLETE_KEYS_SET, REQUIRED_UPLOAD,
)
from database import StorageError, dedup_index, embedding_cache
from limits import BodySizeLimitMiddleware
from pipeline.engine import InvalidImage, Pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('attendance')

pipeline = Pipeline()
logger.info('%s pipeline ready (%s)', MODE.upper(), pipeline.model_name)
outbox = lms.LmsOutbox() if lms.enabled() else None
service = AttendanceService(pipeline, outbox)
camera: CameraWorker | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _read_limited(file: UploadFile) -> bytes:
    """Read an upload, rejecting anything over MAX_UPLOAD_BYTES without
    loading more than MAX_UPLOAD_BYTES + 1 bytes into memory."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f'File exceeds {MAX_UPLOAD_BYTES}-byte limit')
    return data


def _require_ready() -> None:
    if not service.ready:
        raise HTTPException(status_code=503, detail='service not ready: database unavailable')


def _storage_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail='storage unavailable')


# ─── App + Lifespan ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI):
    global camera
    if not API_KEYS:
        logger.warning('API_KEY is not set: registration and attendance endpoints are OPEN '
                       'to anyone who can reach this server. Set API_KEY in .env.')
    if OBSOLETE_KEYS_SET:
        logger.info('ignoring obsolete .env settings: %s', ', '.join(OBSOLETE_KEYS_SET))

    try:
        await asyncio.to_thread(service.startup_load)
    except StorageError as exc:
        service.last_error = str(exc)
        logger.error('startup DB load failed (retrying every 10s; endpoints return 503 '
                     'until it succeeds): %s', exc)
    maintenance = asyncio.create_task(service.maintain(), name='maintenance')
    if outbox is not None:
        await outbox.start()
    if CAMERA_URL:
        camera = CameraWorker(CAMERA_URL, CAMERA_ID, CAMERA_FPS, pipeline, service)
        camera.start()

    yield

    if camera is not None:
        await asyncio.to_thread(camera.stop)
    maintenance.cancel()
    if outbox is not None:
        await outbox.stop()


app = FastAPI(title='School Face Attendance API', version='3.2', lifespan=lifespan)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

# CORS is opt-in: only enabled when ALLOWED_ORIGINS is configured.
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=['*'],
        allow_headers=['*'],
    )


# ─── Health / status ──────────────────────────────────────────────────────────

@app.get('/healthz')
def healthz():
    """Liveness probe: the process is up (says nothing about the database)."""
    return {'status': 'ok'}


@app.get('/api/status')
def status():
    db_ok = database.ping()
    lms_pending = None
    if db_ok and service.ready:
        try:
            lms_pending = database.count_pending()
        except StorageError:
            db_ok = False
    return {
        'status': 'running',
        'ready': service.ready,
        'db_ok': db_ok,
        'mode': MODE,
        'model': service.model,
        'attendance_date': service.loaded_day.isoformat() if service.loaded_day else None,
        'students_pending': len(embedding_cache),
        'registered_total': len(dedup_index),
        'ignored_other_model': service.other_model_count,
        'lms_enabled': lms.enabled(),
        'lms_pending': lms_pending,
        'camera': camera.status() if camera else None,
    }


# ─── Process single frame ──────────────────────────────────────────────────────

@app.post('/api/camera/process-frame', dependencies=[Depends(require_api_key)])
async def process_frame(file: UploadFile = File(...)):
    """
    Submit a single JPEG/PNG frame. Records attendance for each recognised face
    (the LMS is notified asynchronously, with retries) and returns per-face
    results in detection order, each with its bounding box.

    status per face: notified (newly marked), already_marked (seen earlier today),
    unknown, or error (could not be recorded; will be detected again).
    """
    _require_ready()
    data = await _read_limited(file)
    try:
        faces = await asyncio.to_thread(pipeline.embed_frame, data)
    except InvalidImage:
        raise HTTPException(status_code=400, detail='Invalid image data')
    results = await asyncio.to_thread(service.record_faces, faces, 'api')
    return {
        'faces_detected': len(results),
        'detected_at': datetime.now(UTC).isoformat(timespec='seconds'),
        'results': results,
    }


# ─── Register student (LMS integration) ───────────────────────────────────────

@app.post('/api/register/lms', dependencies=[Depends(require_api_key)])
async def register_from_lms(
    registration_number: str = Form(''),
    photos: list[UploadFile] = File(..., alias='photos[]'),
):
    """
    Register a student from the LMS. Requires exactly REQUIRED_UPLOAD images in a
    single array (key: photos[]); at least REQUIRED_VALID must contain a clear,
    consistent face. Returns status 1 on success, 0 on failure.

    Rejects the request if the registration_number is already registered, or if the
    submitted face is already registered under another number.
    """
    if len(photos) != REQUIRED_UPLOAD:
        return {
            'success': False, 'status': 0,
            'message': f'Exactly {REQUIRED_UPLOAD} photos required, received {len(photos)}',
        }
    _require_ready()
    blobs = [await _read_limited(p) for p in photos]
    try:
        return await service.register(registration_number, blobs)
    except StorageError:
        raise _storage_unavailable()


# ─── Student management ───────────────────────────────────────────────────────

@app.delete('/api/students/{registration_number:path}', dependencies=[Depends(require_api_key)])
async def delete_student(registration_number: str):
    """Delete a student's face data (leaver / erasure request). Attendance history
    is kept. The student can then be registered again."""
    _require_ready()
    try:
        deleted = await service.delete_student(registration_number)
    except StorageError:
        raise _storage_unavailable()
    if not deleted:
        raise HTTPException(status_code=404, detail='registration_number not found')
    return {'deleted': True, 'registration_number': registration_number}


@app.get('/api/attendance', dependencies=[Depends(require_api_key)])
async def list_attendance(day: date | None = Query(None, alias='date')):
    """Attendance recorded on a day (default: today) with LMS delivery status."""
    day = day or today()
    try:
        events = await asyncio.to_thread(database.list_events, day)
    except StorageError:
        raise _storage_unavailable()
    return {'date': day.isoformat(), 'count': len(events), 'events': events}


# ─── Cache reload ─────────────────────────────────────────────────────────────

@app.post('/api/cache/reload', dependencies=[Depends(require_api_key)])
async def reload_cache():
    """Reload embeddings from PostgreSQL (e.g. after editing the DB by hand).
    Students already marked today stay marked; the day rolls over automatically."""
    try:
        loader = service.reload if service.ready else service.startup_load
        n_pending = await asyncio.to_thread(loader)
    except StorageError:
        raise _storage_unavailable()
    return {'reloaded': True, 'students_pending': n_pending, 'registered_total': len(dedup_index)}


if __name__ == '__main__':
    import uvicorn
    # Keep a single worker: attendance state lives in this process's memory.
    uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
