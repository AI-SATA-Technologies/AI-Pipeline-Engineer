"""
viewer.py  -  Temporary live camera feed viewer (testing tool only).

Opens this PC's webcam, sends each frame to the running attendance server's
/api/camera/process-frame endpoint, and shows the feed with face boxes,
student IDs and detection time drawn on it.

The server handles the actual attendance (LMS notification). The API only
returns the student ID + detection time per face -- it does NOT return the
face box. This viewer detects faces locally (InsightFace) to know where to
draw the rectangles, and pairs each detected face with the server result by
detection order.

Start the server first, then run from school_attendance/:
    python viewer.py

Press Q in the window to quit.
"""
import sys

import cv2
import numpy as np
import requests

from config import MODE
from pipeline.detector import FaceDetector

SERVER_URL = 'http://127.0.0.1:8000/api/camera/process-frame'
CAMERA_INDEX = 0
JPEG_QUALITY = 80


def draw(frame, face, result):
    x1, y1, x2, y2 = (int(v) for v in face.bbox)
    known = result is not None and result.get('status') == 'notified'
    color = (0, 255, 0) if known else (0, 0, 255)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    if known:
        label = result['registration_number']
        time_label = result.get('detected_at', '')
    else:
        label = 'Unknown'
        time_label = ''

    cv2.putText(frame, label, (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    if time_label:
        cv2.putText(frame, time_label, (x1, y2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def main():
    print('[viewer] Loading face detector ...')
    detector = FaceDetector(mode=MODE)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f'[viewer] ERROR: cannot open webcam (index {CAMERA_INDEX})')
        sys.exit(1)

    print('[viewer] Running -- press Q to quit')
    while True:
        ret, frame = cap.read()
        if not ret:
            print('[viewer] Frame read failed')
            break

        ok, buf = cv2.imencode('.jpg', frame,
                               [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            jpeg = buf.tobytes()
            # Detect locally on the exact same JPEG the server receives,
            # so the face order matches the server's results.
            decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8),
                                   cv2.IMREAD_COLOR)
            faces = detector.detect(decoded)

            try:
                resp = requests.post(
                    SERVER_URL,
                    files={'file': ('frame.jpg', jpeg, 'image/jpeg')},
                    timeout=10,
                )
                if resp.status_code == 200:
                    results = resp.json().get('results', [])
                    for i, face in enumerate(faces):
                        result = results[i] if i < len(results) else None
                        draw(frame, face, result)
                        if result and result.get('status') == 'notified':
                            print(f"[detected] {result['registration_number']} at "
                                  f"{result.get('detected_at')}")
                else:
                    cv2.putText(frame, f'server error {resp.status_code}',
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                                0.7, (0, 0, 255), 2)
            except requests.RequestException:
                cv2.putText(frame, 'server offline -- start the server first',
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 255), 2)

        cv2.putText(frame, 'TESTING VIEWER  |  Q = quit',
                    (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.imshow('Face Attendance - Live View (testing)', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print('[viewer] Closed')


if __name__ == '__main__':
    main()
