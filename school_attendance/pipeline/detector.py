import insightface
import numpy as np


class FaceDetector:
    def __init__(self):
        self.app = insightface.app.FaceAnalysis(
            name='buffalo_sc',
            allowed_modules=['detection']
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def detect(self, frame):
        """Returns list of Face objects with .bbox and .kps"""
        return self.app.get(frame)

    def crop_face(self, frame, face, padding=0.25):
        """Crop face with padding for liveness + recognition"""
        x1, y1, x2, y2 = face.bbox.astype(int)
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(frame.shape[1], x2 + pad_x)
        y2 = min(frame.shape[0], y2 + pad_y)
        return frame[y1:y2, x1:x2]
