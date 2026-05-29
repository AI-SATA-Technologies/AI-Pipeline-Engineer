import os

import cv2
import numpy as np
import onnxruntime as ort

from config import MODEL_DIR, ONNX_PROVIDERS


class FaceRecognizer:
    """
    ArcFace embedding extractor. Two backends:
      heavy -> buffalo_l/w600k_r50.onnx   (ArcFace R50, 512-dim, accurate)
      lite  -> buffalo_sc/w600k_mbf.onnx  (MobileFaceNet, 512-dim, ~5x faster)

    Produces L2-normalized 512-dim float32 vectors.
    Similarity search is handled in-process by EmbeddingCache (numpy dot product).
    Execution providers come from config.ONNX_PROVIDERS (CPU by default; set GPU
    providers there for acceleration).
    """
    _MODEL_FILES = {
        'heavy': ('buffalo_l', 'w600k_r50.onnx'),
        'lite':  ('buffalo_sc', 'w600k_mbf.onnx'),
    }

    def __init__(self, mode: str = 'heavy'):
        self.mode = mode
        subdir, fname = self._MODEL_FILES[mode]
        model_path = os.path.join(MODEL_DIR, subdir, fname)
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f'Recognition model not found at {model_path}. '
                f'Run "python download_models.py" or set MODEL_DIR in your .env.'
            )
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(model_path, sess_options=so, providers=ONNX_PROVIDERS)
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
