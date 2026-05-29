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
