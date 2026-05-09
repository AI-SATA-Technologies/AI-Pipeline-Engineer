import onnxruntime as ort
import numpy as np
import faiss
import pickle
import os
import cv2


class FaceRecognizer:
    """ArcFace recognizer. Two backends:
       heavy -> w600k_r50.onnx   (174 MB, R50, slow but accurate)
       lite  -> w600k_mbf.onnx   (13 MB, MobileFaceNet, ~5x faster)
    Both produce 512-dim embeddings, but they live in DIFFERENT spaces — never mix.
    """
    _MODEL_PATHS = {
        'heavy': os.path.expanduser('~/.insightface/models/buffalo_l/w600k_r50.onnx'),
        'lite':  os.path.expanduser('~/.insightface/models/buffalo_sc/w600k_mbf.onnx'),
    }

    def __init__(self, mode: str = 'heavy', threshold: float = 0.40,
                 index_path: str = 'embeddings/faiss.index',
                 names_path: str = 'embeddings/names.pkl'):
        self.mode = mode
        self.sess = ort.InferenceSession(
            self._MODEL_PATHS[mode],
            providers=['CPUExecutionProvider'],
        )
        self.input_name = self.sess.get_inputs()[0].name
        self.threshold = threshold
        self.index_path = index_path
        self.names_path = names_path
        self.index = None
        self.names = []
        self._load()

    def _preprocess(self, img_112: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor(img_112, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - 127.5) / 127.5
        return np.transpose(img, (2, 0, 1))[np.newaxis]

    def get_embedding(self, aligned_112: np.ndarray) -> np.ndarray | None:
        if aligned_112 is None or aligned_112.size == 0:
            return None
        if aligned_112.shape[:2] != (112, 112):
            aligned_112 = cv2.resize(aligned_112, (112, 112))
        out = self.sess.run(None, {self.input_name: self._preprocess(aligned_112)})[0][0]
        norm = np.linalg.norm(out)
        if norm == 0:
            return None
        return (out / norm).astype(np.float32)

    def identify(self, aligned_112: np.ndarray) -> tuple[str, float]:
        if self.index is None or self.index.ntotal == 0:
            return 'Unknown', 0.0
        emb = self.get_embedding(aligned_112)
        if emb is None:
            return 'Unknown', 0.0
        scores, indices = self.index.search(emb[np.newaxis], 1)
        score = float(scores[0][0])
        if score >= self.threshold:
            return self.names[indices[0][0]], score
        return 'Unknown', score

    def add_student(self, name: str, embeddings: list):
        avg = np.mean(embeddings, axis=0).astype(np.float32)
        avg /= np.linalg.norm(avg)
        self.index.add(avg[np.newaxis])
        self.names.append(name)
        os.makedirs(os.path.dirname(self.index_path) or '.', exist_ok=True)
        faiss.write_index(self.index, self.index_path)
        with open(self.names_path, 'wb') as f:
            pickle.dump(self.names, f)

    def _load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.names_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.names_path, 'rb') as f:
                self.names = pickle.load(f)
        else:
            self.index = faiss.IndexFlatIP(512)

    def reload(self):
        self._load()
