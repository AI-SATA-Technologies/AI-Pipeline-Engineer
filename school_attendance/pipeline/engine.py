"""Face pipeline: decode -> detect -> align -> embed.

Shared by the HTTP endpoints and the camera worker. All inference goes through
one bounded semaphore (INFERENCE_CONCURRENCY) so concurrent frames, registrations
and the camera can't oversubscribe the CPU.
"""
import threading

import cv2
import numpy as np

from config import INFERENCE_CONCURRENCY, MODE, REG_MIN_DET_SCORE, REG_MIN_FACE_PX
from pipeline.detector import FaceDetector
from pipeline.recognizer import FaceRecognizer

# One detected face: ([x1, y1, x2, y2], embedding or None if unusable).
FaceResult = tuple[list[int], np.ndarray | None]


class InvalidImage(ValueError):
    """Raised for undecodable, corrupt or oversized (decompression-bomb) images."""


def decode_image(data: bytes) -> np.ndarray:
    try:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as exc:  # e.g. exceeds OPENCV_IO_MAX_IMAGE_PIXELS
        raise InvalidImage('image is corrupt or too large') from exc
    if img is None:
        raise InvalidImage('invalid image data')
    return img


def best_registration_face(faces):
    """Largest face that is confident and big enough, else None.

    Picking the largest (not the highest-scoring) face avoids enrolling a
    bystander in the background of a registration photo.
    """
    candidates = []
    for f in faces:
        x1, y1, x2, y2 = f.bbox
        if f.det_score >= REG_MIN_DET_SCORE and min(x2 - x1, y2 - y1) >= REG_MIN_FACE_PX:
            candidates.append(((x2 - x1) * (y2 - y1), f))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])[1]


class Pipeline:
    def __init__(self, mode: str = MODE):
        self.detector = FaceDetector(mode=mode)
        self.recognizer = FaceRecognizer(mode=mode)
        self.model_name = self.recognizer.model_name
        self._slots = threading.BoundedSemaphore(INFERENCE_CONCURRENCY)

    def embed_image(self, img: np.ndarray) -> list[FaceResult]:
        """Detect + embed every face in a decoded BGR image, in detection order."""
        with self._slots:
            out = []
            for face in self.detector.detect(img):
                aligned = self.detector.align_face(img, face)
                bbox = [int(round(float(v))) for v in face.bbox]
                out.append((bbox, self.recognizer.get_embedding(aligned)))
            return out

    def embed_frame(self, data: bytes) -> list[FaceResult]:
        """Decode an encoded image (JPEG/PNG…) and embed every face. Raises InvalidImage."""
        return self.embed_image(decode_image(data))

    def embed_photos(self, blobs: list[bytes]) -> list[np.ndarray]:
        """One embedding per registration photo that has a usable face."""
        embeddings = []
        with self._slots:
            for data in blobs:
                try:
                    img = decode_image(data)
                except InvalidImage:
                    continue
                face = best_registration_face(self.detector.detect(img))
                if face is None:
                    continue
                emb = self.recognizer.get_embedding(self.detector.align_face(img, face))
                if emb is not None:
                    embeddings.append(emb)
        return embeddings
