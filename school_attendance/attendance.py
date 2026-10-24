"""Attendance + registration service — the logic shared by the HTTP API and the
camera worker.

Attendance flow (per detected face):
    claim from the in-memory cache  ->  INSERT attendance_events (unique per
    student per day)  ->  LMS outbox delivers it (retries until the LMS accepts).
If recording fails the claim is undone, so a DB outage can't silently drop a
student. The cache always holds "registered students not yet marked today", so
restarts and reloads never re-notify, and it is rebuilt when the day changes.
"""
import asyncio
import logging
import threading
import unicodedata
from datetime import date, datetime, UTC

import numpy as np

import database
import lms
from config import (
    ATTENDANCE_TZ, AUTO_MIGRATE, REG_CONSISTENCY_MIN, REQUIRED_VALID,
    REVEAL_DUPLICATE_MATCH, SIMILARITY_THRESHOLD,
)

logger = logging.getLogger('attendance')

MAX_REGISTRATION_NUMBER_LEN = 100  # matches VARCHAR(100) in the schema


def today() -> date:
    """The current attendance day in ATTENDANCE_TZ (server-local when unset)."""
    now = datetime.now(ATTENDANCE_TZ) if ATTENDANCE_TZ else datetime.now().astimezone()
    return now.date()


def validate_registration_number(raw: str | None) -> tuple[str, str | None]:
    """Return (cleaned value, error message or None)."""
    value = (raw or '').strip()
    if not value:
        return value, 'registration_number is required'
    if len(value) > MAX_REGISTRATION_NUMBER_LEN:
        return value, f'registration_number must be at most {MAX_REGISTRATION_NUMBER_LEN} characters'
    if any(unicodedata.category(ch).startswith('C') for ch in value):
        return value, 'registration_number contains invalid characters'
    return value, None


def build_template(embeddings: list[np.ndarray]) -> tuple[np.ndarray | None, int]:
    """Average registration embeddings after dropping outliers.

    The reference is the set's medoid — the photo most similar on average to all
    the others — which always belongs to the majority person, even in a set that
    is half one person and half another (where the plain mean would sit between
    the two and accept everything). Embeddings whose cosine similarity to the
    medoid is below REG_CONSISTENCY_MIN are discarded; the rest are averaged and
    L2-normalised. Returns (template, embeddings kept).
    """
    if not embeddings:
        return None, 0
    stack = np.stack(embeddings).astype(np.float32)
    sims = stack @ stack.T
    medoid = int(np.argmax(sims.mean(axis=1)))
    kept = stack[sims[medoid] >= REG_CONSISTENCY_MIN]
    template = kept.mean(axis=0)
    norm = float(np.linalg.norm(template))
    if norm == 0:
        return None, 0
    return (template / norm).astype(np.float32), int(kept.shape[0])


def _fail(message: str) -> dict:
    return {'success': False, 'status': 0, 'message': message}


class AttendanceService:
    def __init__(self, pipeline, outbox: 'lms.LmsOutbox | None' = None):
        self.pipeline = pipeline
        self.model = pipeline.model_name
        self.outbox = outbox
        self.ready = False
        self.loaded_day: date | None = None
        self.other_model_count = 0
        self.last_error: str | None = None
        self._reload_lock = threading.Lock()
        self._register_lock = asyncio.Lock()

    # ── Loading ────────────────────────────────────────────────────────────

    def startup_load(self) -> int:
        """Apply migrations (if enabled) and load the stores. Raises StorageError."""
        if AUTO_MIGRATE:
            applied = database.apply_migrations()
            logger.info('schema up to date (%s)', ', '.join(applied))
        return self.reload()

    def reload(self) -> int:
        """Rebuild both in-memory stores for today. Returns students still pending."""
        with self._reload_lock:
            day = today()
            ids, matrix = database.rows_to_matrix(database.fetch_embeddings(self.model))
            marked = database.fetch_marked_on(day)
            other = database.count_other_models(self.model)
            keep = [i for i, reg in enumerate(ids) if reg not in marked]
            database.dedup_index.replace(ids, matrix)
            database.embedding_cache.replace([ids[i] for i in keep], matrix[keep])
            self.other_model_count = other
            self.loaded_day = day
            self.ready = True
            self.last_error = None
        if other:
            logger.warning('%d embedding(s) were made by another model and are ignored in %s mode '
                           '(those students must re-register)', other, self.model)
        logger.info('%s: %d registered, %d pending, %d already marked',
                    day.isoformat(), len(ids), len(keep), len(ids) - len(keep))
        return len(keep)

    async def maintain(self, interval: float = 10.0) -> None:
        """Background loop: retry the initial load until the DB is reachable, then
        reload the cache whenever the attendance day changes."""
        while True:
            try:
                if not self.ready:
                    await asyncio.to_thread(self.startup_load)
                elif today() != self.loaded_day:
                    logger.info('new attendance day — reloading cache')
                    await asyncio.to_thread(self.reload)
            except database.StorageError as exc:
                if str(exc) != self.last_error:
                    logger.error('database unavailable: %s', exc)
                self.last_error = str(exc)
            await asyncio.sleep(interval)

    # ── Attendance ─────────────────────────────────────────────────────────

    def record_faces(self, faces, source: str) -> list[dict]:
        """Claim + record attendance for each (bbox, embedding). Blocking (DB I/O):
        call from a worker thread. Returns one result dict per face, in order."""
        day = today()
        now = datetime.now(UTC)
        detected_at = now.isoformat(timespec='seconds')
        lms_status = 'pending' if lms.enabled() else 'skipped'
        results, queued = [], False

        for bbox, emb in faces:
            claimed = database.embedding_cache.claim(emb) if emb is not None else None
            if claimed is None:
                results.append(self._unclaimed_result(bbox, emb))
                continue
            reg, score, vec = claimed
            try:
                event_id = database.insert_event(reg, day, now, source, score, lms_status)
            except database.StorageError as exc:
                database.embedding_cache.add(reg, vec)  # undo: detect again later
                logger.error('could not record attendance for %s: %s', reg, exc)
                results.append({'status': 'error', 'bbox': bbox})
                continue
            if event_id is None:  # already recorded today (e.g. by another source)
                results.append({'registration_number': reg, 'status': 'already_marked', 'bbox': bbox})
                continue
            queued = queued or lms_status == 'pending'
            logger.info('attendance: %s via %s (score %.3f)', reg, source, score)
            results.append({
                'registration_number': reg,
                'status': 'notified',
                'detected_at': detected_at,
                'bbox': bbox,
            })

        if queued and self.outbox is not None:
            self.outbox.wake()
        return results

    @staticmethod
    def _unclaimed_result(bbox, emb) -> dict:
        """A face not in the pending cache: either already marked today or unknown."""
        if emb is not None:
            reg, _ = database.dedup_index.find_match(emb, SIMILARITY_THRESHOLD)
            if reg is not None:
                return {'registration_number': reg, 'status': 'already_marked', 'bbox': bbox}
        return {'status': 'unknown', 'bbox': bbox}

    # ── Registration ───────────────────────────────────────────────────────

    async def register(self, raw_registration_number: str, blobs: list[bytes]) -> dict:
        """Register a student from REQUIRED_UPLOAD photos. Raises StorageError."""
        reg, error = validate_registration_number(raw_registration_number)
        if error:
            return _fail(error)
        if await asyncio.to_thread(database.registration_exists, reg):
            return _fail(f'registration_number {reg} is already registered')

        embeddings = await asyncio.to_thread(self.pipeline.embed_photos, blobs)
        if len(embeddings) < REQUIRED_VALID:
            return _fail(f'Only {len(embeddings)} photo(s) had a detectable face, '
                         f'at least {REQUIRED_VALID} required')

        template, kept = build_template(embeddings)
        if template is None or kept < REQUIRED_VALID:
            return _fail(f'Only {kept} of {len(embeddings)} photos consistently show the same person, '
                         f'at least {REQUIRED_VALID} required')

        # Duplicate check + insert + in-memory add happen as one step, so two
        # concurrent registrations can't both slip past the duplicate check.
        async with self._register_lock:
            existing, score = database.dedup_index.find_match(template)
            if existing is not None:
                logger.warning('registration %s rejected: face matches %s (score %.3f)',
                               reg, existing, score)
                if REVEAL_DUPLICATE_MATCH:
                    return _fail(f'This face is already registered under registration_number {existing}')
                return _fail('This face is already registered under another registration_number')

            inserted = await asyncio.to_thread(
                database.insert_embedding, reg, template, kept, self.model
            )
            if not inserted:
                return _fail(f'registration_number {reg} is already registered')
            database.dedup_index.add(reg, template)
            database.embedding_cache.add(reg, template)

        logger.info('registered %s (%d of %d samples used)', reg, kept, len(embeddings))
        return {'success': True, 'status': 1, 'message': 'Face registered successfully'}

    async def delete_student(self, registration_number: str) -> bool:
        """Delete a student's face data (attendance history is kept). Raises StorageError."""
        async with self._register_lock:
            deleted = await asyncio.to_thread(database.delete_embedding, registration_number)
            database.dedup_index.remove(registration_number)
            database.embedding_cache.remove(registration_number)
        if deleted:
            logger.info('deleted face data for %s', registration_number)
        return deleted
