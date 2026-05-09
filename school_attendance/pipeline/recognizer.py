import insightface
import faiss
import numpy as np
import pickle
import os


class FaceRecognizer:
    def __init__(self, threshold: float = 0.55,
                 index_path: str = 'embeddings/faiss.index',
                 names_path: str = 'embeddings/names.pkl'):
        self.app = insightface.app.FaceAnalysis(
            name='buffalo_l',
            allowed_modules=['detection', 'recognition']
        )
        self.app.prepare(ctx_id=0)
        self.threshold = threshold
        self.index_path = index_path
        self.names_path = names_path
        self.index = None
        self.names = []
        self._load()

    def _load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.names_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.names_path, 'rb') as f:
                self.names = pickle.load(f)
        else:
            self.index = faiss.IndexFlatIP(512)

    def add_student(self, name: str, embeddings: list):
        avg = np.mean(embeddings, axis=0).astype(np.float32)
        avg /= np.linalg.norm(avg)
        self.index.add(avg[np.newaxis])
        self.names.append(name)
        os.makedirs(os.path.dirname(self.index_path) or '.', exist_ok=True)
        faiss.write_index(self.index, self.index_path)
        with open(self.names_path, 'wb') as f:
            pickle.dump(self.names, f)

    def get_embedding(self, face_img) -> np.ndarray | None:
        faces = self.app.get(face_img)
        if not faces:
            return None
        return faces[0].normed_embedding

    def identify(self, face_img) -> tuple[str, float]:
        if self.index.ntotal == 0:
            return 'Unknown', 0.0
        emb = self.get_embedding(face_img)
        if emb is None:
            return 'Unknown', 0.0
        emb = emb[np.newaxis].astype(np.float32)
        scores, indices = self.index.search(emb, 1)
        score = float(scores[0][0])
        if score >= self.threshold:
            return self.names[indices[0][0]], score
        return 'Unknown', score

    def reload(self):
        self._load()
