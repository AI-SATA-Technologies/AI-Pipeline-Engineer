import onnxruntime as ort
import numpy as np
import cv2
import os


class LivenessDetector:
    def __init__(self, model_path: str, threshold: float = 0.70):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Liveness model not found: {model_path}")
        self.sess = ort.InferenceSession(
            model_path,
            providers=['CPUExecutionProvider']
        )
        self.threshold = threshold

    def check(self, face_crop) -> tuple[bool, float]:
        img = cv2.resize(face_crop, (80, 80))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = (img - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        img = np.transpose(img, (2, 0, 1))[np.newaxis].astype(np.float32)
        out = self.sess.run(None, {self.sess.get_inputs()[0].name: img})[0][0]
        e = np.exp(out - out.max())
        live_score = float(e[1] / e.sum())
        return live_score >= self.threshold, live_score
