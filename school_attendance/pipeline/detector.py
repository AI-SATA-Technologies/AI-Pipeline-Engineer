import os

import numpy as np

from config import MODEL_DIR, ONNX_PROVIDERS
from pipeline.align import norm_crop
from pipeline.scrfd import SCRFD

# Detection always uses the lightweight SCRFD-500MF model (buffalo_sc); only the
# input resolution changes with mode.
_DET_MODEL = os.path.join(MODEL_DIR, 'buffalo_sc', 'det_500m.onnx')


class FaceDetector:
    """SCRFD 500M face detector (raw ONNX Runtime). Detection size depends on mode.
    lite  -> det_size (320, 320)  ~3x faster
    heavy -> det_size (640, 640)  more accurate for small faces
    """

    def __init__(self, mode: str = 'heavy'):
        self.mode = mode
        det_size = (320, 320) if mode == 'lite' else (640, 640)
        if not os.path.exists(_DET_MODEL):
            raise FileNotFoundError(
                f'SCRFD detector model not found at {_DET_MODEL}. '
                f'Run "python download_models.py" or set MODEL_DIR in your .env.'
            )
        self.scrfd = SCRFD(_DET_MODEL, providers=ONNX_PROVIDERS, det_size=det_size)

    def detect(self, frame):
        return self.scrfd.detect(frame)

    def align_face(self, frame, face) -> np.ndarray:
        """112x112 keypoint-aligned crop — correct input for ArcFace/MobileFaceNet."""
        return norm_crop(frame, face.kps)
