import numpy as np

from config import ONNX_PROVIDERS
from pipeline import model_files
from pipeline.align import norm_crop
from pipeline.scrfd import SCRFD


class FaceDetector:
    """SCRFD 500M face detector (raw ONNX Runtime). Detection size depends on mode.
    lite  -> det_size (320, 320)  ~3x faster
    heavy -> det_size (640, 640)  more accurate for small faces

    Detection always uses the lightweight SCRFD-500MF model (buffalo_sc); only the
    input resolution changes with mode.
    """

    def __init__(self, mode: str = 'heavy'):
        self.mode = mode
        det_size = (320, 320) if mode == 'lite' else (640, 640)
        model_path = model_files.require(model_files.DETECTOR)
        self.scrfd = SCRFD(model_path, providers=ONNX_PROVIDERS, det_size=det_size)

    def detect(self, frame):
        return self.scrfd.detect(frame)

    def align_face(self, frame, face) -> np.ndarray:
        """112x112 keypoint-aligned crop — correct input for ArcFace/MobileFaceNet."""
        return norm_crop(frame, face.kps)
