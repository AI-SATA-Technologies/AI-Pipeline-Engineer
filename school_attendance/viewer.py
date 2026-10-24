"""
viewer.py  -  Live camera feed viewer (testing / display tool).

Opens a camera, sends frames to the running attendance server's
/api/camera/process-frame endpoint, and shows the feed with the face boxes,
registration numbers and detection times the server returns.

The server does all detection and recognition and returns each face's box, so
this viewer loads no models. Frames are sent at most VIEWER_FPS times a second.

Camera source (first one set wins):
    python viewer.py <source>       e.g. 0, rtsp://user:pass@ip:554/..., video.mp4
    CAMERA_URL in .env
    webcam 0

Note: if the server itself reads CAMERA_URL (camera worker), the viewer is not
needed for attendance; use it only to watch. Attendance is still recorded once
per student per day.

Start the server first, then run from school_attendance/:
    python viewer.py

Press Q in the window to quit.
"""
import config  # noqa: F401  (sets OpenCV env options before cv2 is imported)

import sys
import time

import cv2
import httpx

from camera_worker import mask_source, normalize_source
from config import API_KEY, CAMERA_URL

SERVER_URL = 'http://127.0.0.1:8000/api/camera/process-frame'
JPEG_QUALITY = 80
VIEWER_FPS = 4.0
# Sent only when the server is configured with an API_KEY.
HEADERS = {'X-API-Key': API_KEY} if API_KEY else {}

KNOWN_STATUSES = {'notified', 'already_marked'}


def draw(frame, result):
    x1, y1, x2, y2 = result['bbox']
    known = result.get('status') in KNOWN_STATUSES
    color = (0, 255, 0) if known else (0, 0, 255)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    label = result['registration_number'] if known else 'Unknown'
    cv2.putText(frame, label, (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    time_label = result.get('detected_at', '')
    if time_label:
        cv2.putText(frame, time_label, (x1, y2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def open_capture(source):
    if isinstance(source, str) and '://' in source:
        return cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    return cv2.VideoCapture(source)


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else (CAMERA_URL or '0')
    source = normalize_source(raw)
    print(f'[viewer] Opening {mask_source(source)}')
    cap = open_capture(source)
    if not cap.isOpened():
        print(f'[viewer] ERROR: cannot open camera source {mask_source(source)}')
        print('[viewer] For RTSP, check the path and use the camera\'s LOCAL account '
              '(not a cloud/Hik-Connect email).')
        sys.exit(1)

    print('[viewer] Running -- press Q to quit')
    results, status_text = [], ''
    next_send = 0.0
    with httpx.Client(timeout=10, headers=HEADERS) as client:
        while True:
            ret, frame = cap.read()
            if not ret:
                print('[viewer] Frame read failed')
                break

            now = time.monotonic()
            if now >= next_send:
                next_send = now + 1.0 / VIEWER_FPS
                ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if ok:
                    try:
                        resp = client.post(
                            SERVER_URL,
                            files={'file': ('frame.jpg', buf.tobytes(), 'image/jpeg')},
                        )
                        if resp.status_code == 200:
                            results, status_text = resp.json().get('results', []), ''
                            for r in results:
                                if r.get('status') == 'notified':
                                    print(f"[detected] {r['registration_number']} at {r.get('detected_at')}")
                        else:
                            results, status_text = [], f'server error {resp.status_code}'
                    except httpx.HTTPError:
                        results, status_text = [], 'server offline -- start the server first'

            # Boxes come from the last server reply (refreshed VIEWER_FPS times a second).
            for r in results:
                if 'bbox' in r:
                    draw(frame, r)
            if status_text:
                cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 255), 2)
            cv2.putText(frame, 'VIEWER  |  Q = quit', (10, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow('Face Attendance - Live View', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()
    print('[viewer] Closed')


if __name__ == '__main__':
    main()
