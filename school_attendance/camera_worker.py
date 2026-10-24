"""Server-side camera ingestion.

Reads CAMERA_URL directly (RTSP network camera, local webcam index, or a video
file for testing) in a background thread, samples CAMERA_FPS frames per second,
and marks attendance through the same service the HTTP API uses.

For live sources it keeps grabbing frames and only decodes the ones it
processes, so the RTSP buffer never backs up (no growing lag). Reconnects use
a 5 s -> 60 s backoff so a misconfigured camera isn't hammered into an
authentication lockout.
"""
import config  # noqa: F401  (sets OpenCV env options before cv2 is imported)

import logging
import re
import threading
import time
from datetime import datetime, UTC
from urllib.parse import quote

import cv2

logger = logging.getLogger('attendance.camera')

_MIN_BACKOFF = 5.0
_MAX_BACKOFF = 60.0
# After this many consecutive failed connects (wrong password, wrong path…),
# slow down to one attempt per _LONG_BACKOFF: cameras such as Hikvision lock the
# account after repeated failed logins, and retrying every minute would keep it locked.
_FAST_FAILURES = 5
_LONG_BACKOFF = 900.0


def normalize_source(raw: str) -> int | str:
    """Turn a CAMERA_URL value into a cv2.VideoCapture source.

    - bare integer      -> that webcam index;
    - stream URL        -> the URL, with two common mistakes corrected:
        * stray characters before the scheme (e.g. "0rtsp://...");
        * an unencoded username/password (e.g. an email login, whose "@" collides
          with the user@host separator) -> percent-encoded.
      Credentials that already contain "%" are assumed encoded and left alone;
    - anything else     -> used as-is (e.g. a video file path).
    """
    raw = (raw or '').strip().strip('"').strip("'")
    if raw.isdigit():
        return int(raw)
    low = raw.lower()
    for scheme in ('rtsp://', 'rtsps://', 'http://', 'https://'):
        k = low.find(scheme)
        if k > 0:
            raw = raw[k:]
            break
    m = re.match(r'(?i)^(\w+://)(.+)$', raw)
    if m and '@' in m.group(2) and '%' not in m.group(2):
        scheme, rest = m.group(1), m.group(2)
        userinfo, host = rest.rsplit('@', 1)  # last '@' separates creds from host
        if ':' in userinfo:
            user, pwd = userinfo.split(':', 1)
            userinfo = f'{quote(user, safe="")}:{quote(pwd, safe="")}'
        else:
            userinfo = quote(userinfo, safe='')
        raw = f'{scheme}{userinfo}@{host}'
    return raw


def mask_source(source: int | str) -> str:
    """Printable form of a source with credentials hidden."""
    if isinstance(source, int):
        return f'webcam {source}'
    return re.sub(r'(//)[^/]*@', r'\1***:***@', source)


def _is_live(source: int | str) -> bool:
    return isinstance(source, int) or '://' in source


class CameraWorker:
    def __init__(self, raw_source: str, camera_id: str, fps: float, pipeline, service):
        self.source = normalize_source(raw_source)
        self.display = mask_source(self.source)
        self.camera_id = camera_id
        self.interval = 1.0 / fps
        self.pipeline = pipeline
        self.service = service
        self.state = 'stopped'
        self.last_error: str | None = None
        self.frames_processed = 0
        self.last_frame_at: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f'camera-{self.camera_id}', daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def status(self) -> dict:
        # The source (camera IP/path) is deliberately left out: /api/status is
        # unauthenticated. It is logged at startup instead.
        return {
            'id': self.camera_id,
            'state': self.state,
            'frames_processed': self.frames_processed,
            'last_frame_at': self.last_frame_at,
            'last_error': self.last_error,
        }

    # ── Loop ───────────────────────────────────────────────────────────────

    def _open(self):
        if isinstance(self.source, str) and '://' in self.source:
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(self.source)
        if cap.isOpened():
            return cap
        cap.release()
        return None

    def _run(self) -> None:
        backoff = _MIN_BACKOFF
        failures = 0
        while not self._stop.is_set():
            self.state = 'connecting'
            cap = self._open()
            if cap is None:
                failures += 1
                wait = _LONG_BACKOFF if failures >= _FAST_FAILURES else backoff
                self.state = 'reconnecting'
                self.last_error = (f'cannot open camera source ({failures} failed attempt(s)); '
                                   'check URL, path and credentials')
                logger.warning('camera %s: cannot open %s (attempt %d); retry in %.0fs',
                               self.camera_id, self.display, failures, wait)
                self._stop.wait(wait)
                backoff = min(backoff * 2, _MAX_BACKOFF)
                continue

            logger.info('camera %s: streaming from %s', self.camera_id, self.display)
            self.state, self.last_error, backoff, failures = 'running', None, _MIN_BACKOFF, 0
            try:
                self._consume(cap)
            except Exception as exc:  # keep the worker alive
                logger.exception('camera %s: error while streaming', self.camera_id)
                self.last_error = f'{type(exc).__name__}: {exc}'
            finally:
                cap.release()

            if not self._stop.is_set():
                self.state = 'reconnecting'
                logger.warning('camera %s: stream ended (%s); reconnecting in %.0fs',
                               self.camera_id, self.last_error or 'end of stream', backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)
        self.state = 'stopped'

    def _consume(self, cap) -> None:
        live = _is_live(self.source)
        next_due = time.monotonic()
        while not self._stop.is_set():
            if live:
                # grab() keeps the stream drained; decode only when a frame is due.
                if not cap.grab():
                    self.last_error = 'frame read failed'
                    return
                if time.monotonic() < next_due:
                    continue
                ok, frame = cap.retrieve()
            else:
                # Video file: play at CAMERA_FPS, frame by frame.
                self._stop.wait(max(0.0, next_due - time.monotonic()))
                ok, frame = cap.read()
            if not ok or frame is None:
                return
            next_due = max(next_due + self.interval, time.monotonic())
            self._process(frame)

    def _process(self, frame) -> None:
        faces = self.pipeline.embed_image(frame)
        self.frames_processed += 1
        self.last_frame_at = datetime.now(UTC).isoformat(timespec='seconds')
        if faces and self.service.ready:
            self.service.record_faces(faces, self.camera_id)
