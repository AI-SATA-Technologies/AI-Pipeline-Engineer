"""
viewer.py  -  Temporary live camera feed viewer.
Shows bounding boxes and identity labels in real time.
Press Q to quit.

Run from school_attendance/:
    python viewer.py
"""
import sys
import os
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import MODE
from database import embedding_cache
from pipeline.detector import FaceDetector
from pipeline.recognizer import FaceRecognizer


def main():
    print('[viewer] Loading models...')
    detector = FaceDetector(mode=MODE)
    recognizer = FaceRecognizer(mode=MODE)

    print('[viewer] Loading embeddings from database...')
    count = embedding_cache.load()
    print(f'[viewer] {count} student(s) loaded')

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print('[viewer] ERROR: Cannot open webcam')
        return

    print('[viewer] Running -- press Q to quit')

    while True:
        ret, frame = cap.read()
        if not ret:
            print('[viewer] Frame read failed')
            break

        faces = detector.detect(frame)

        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            aligned = detector.align_face(frame, face)
            emb = recognizer.get_embedding(aligned)

            if emb is not None:
                student_id, score = embedding_cache.search(emb)
            else:
                student_id, score = 'Unknown', 0.0

            if student_id != 'Unknown':
                color = (0, 255, 0)
                label = f'{student_id}  {score:.1%}'
            else:
                color = (0, 0, 255)
                label = f'Unknown  {score:.1%}'

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, max(y1 - 10, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        pending = len(embedding_cache)
        cv2.putText(
            frame,
            f'Students pending: {pending}  |  MODE: {MODE.upper()}  |  Q = quit',
            (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
        )

        cv2.imshow('Face Attendance - Live View', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print('[viewer] Closed')


if __name__ == '__main__':
    main()
