import insightface
import numpy as np
from insightface.utils import face_align


class FaceDetector:
    """SCRFD 500M face detector. Detection size depends on mode.
    lite  -> det_size (320, 320)  ~3x faster
    heavy -> det_size (640, 640)  more accurate for small faces
    """
    def __init__(self, mode: str = 'heavy'):
        self.mode = mode
        det_size = (320, 320) if mode == 'lite' else (640, 640)
        self.app = insightface.app.FaceAnalysis(
            name='buffalo_sc',
            allowed_modules=['detection']
        )
        self.app.prepare(ctx_id=0, det_size=det_size)

    def detect(self, frame):
        return self.app.get(frame)

    def align_face(self, frame, face) -> np.ndarray:
        """112x112 keypoint-aligned crop — correct input for ArcFace/MobileFaceNet."""
        return face_align.norm_crop(frame, landmark=face.kps)

    def crop_face(self, frame, face, padding=0.25):
        x1, y1, x2, y2 = face.bbox.astype(int)
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(frame.shape[1], x2 + pad_x)
        y2 = min(frame.shape[0], y2 + pad_y)
        return frame[y1:y2, x1:x2]
