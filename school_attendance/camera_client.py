"""
Camera client — runs on the classroom PC connected to the camera.
Sends frames to the FastAPI server every CAMERA_INTERVAL seconds.
"""
import cv2
import requests
import time
import sys

API_URL = 'http://localhost:8000/api/process-frame'
CAMERA_ID = 'class_5A'
INTERVAL_SECONDS = 5

# Change to 0 for USB webcam, or provide an RTSP URL string for IP camera:
# RTSP_URL = 'rtsp://admin:password@192.168.1.100:554/stream1'
CAMERA_SOURCE = 0


def open_camera(source):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Cannot open camera: {source}")
        sys.exit(1)
    return cap


def send_frame(frame, camera_id: str):
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    try:
        resp = requests.post(
            API_URL,
            files={'file': ('frame.jpg', buf.tobytes(), 'image/jpeg')},
            data={'camera_id': camera_id},
            timeout=10,
        )
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  Connection error: {e}")
        return None


def main():
    print(f"Starting camera client | Source: {CAMERA_SOURCE} | Interval: {INTERVAL_SECONDS}s")
    cap = open_camera(CAMERA_SOURCE)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera read failed, reconnecting...")
            cap.release()
            time.sleep(2)
            cap = open_camera(CAMERA_SOURCE)
            continue

        result = send_frame(frame, CAMERA_ID)
        if result:
            print(f"Faces: {result.get('faces_detected', 0)} | {result.get('results', [])}")

        time.sleep(INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
