import os

import cv2
import numpy as np
import onnxruntime as ort


class FaceRecognizer:
    """
    ArcFace embedding extractor. Two backends:
      heavy -> w600k_r50.onnx   (ArcFace R50, 512-dim, accurate)
      lite  -> w600k_mbf.onnx   (MobileFaceNet, 512-dim, ~5x faster)

    Produces L2-normalized 512-dim float32 vectors.
    Similarity search is handled by pgvector in PostgreSQL — not here.
    """
    _MODEL_PATHS = {
        'heavy': os.path.expanduser('~/.insightface/models/buffalo_l/w600k_r50.onnx'),
        'lite':  os.path.expanduser('~/.insightface/models/buffalo_sc/w600k_mbf.onnx'),
    }

    def __init__(self, mode: str = 'heavy'):
        self.mode = mode
        self.sess = ort.InferenceSession(
            self._MODEL_PATHS[mode],
            providers=['CPUExecutionProvider'],
        )
        self.input_name = self.sess.get_inputs()[0].name

    def _preprocess(self, img_112: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor(img_112, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - 127.5) / 127.5
        return np.transpose(img, (2, 0, 1))[np.newaxis]

    def get_embedding(self, aligned_112: np.ndarray) -> np.ndarray | None:
        """Return a 512-dim L2-normalized float32 embedding, or None on failure."""
        if aligned_112 is None or aligned_112.size == 0:
            return None
        if aligned_112.shape[:2] != (112, 112):
            aligned_112 = cv2.resize(aligned_112, (112, 112))
        out = self.sess.run(None, {self.input_name: self._preprocess(aligned_112)})[0][0]
        norm = np.linalg.norm(out)
        if norm == 0:
            return None
        return (out / norm).astype(np.float32)
