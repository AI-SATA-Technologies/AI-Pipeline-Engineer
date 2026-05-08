import onnxruntime as ort
import numpy as np
import cv2


class LivenessDetector:
    def __init__(self, model_path):
        # Use CPU provider for maximum compatibility
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

    def is_live(self, face_crop, threshold=0.9):
        """
        Check if the face crop is live or a spoof.
        Returns: (is_live: bool, score: float)
        """
        # Preprocessing: resize to 80x80 as required by MiniFASNet V2
        img = cv2.resize(face_crop, (80, 80))
        img = img.astype(np.float32)
        # Normalization
        img = (img - 127.5) / 128.0
        # HWC to CHW
        img = np.transpose(img, (2, 0, 1))
        # Batch dimension
        img = np.expand_dims(img, axis=0)

        # Run inference
        outputs = self.session.run(None, {self.session.get_inputs()[0].name: img})
        
        # Softmax to get probability
        # outputs[0][0] shape is (3,) for [fake, real, real_v2] or similar depending on model
        # For MiniFASNet V2, index 1 is usually the "real" score
        score = np.exp(outputs[0][0]) / np.sum(np.exp(outputs[0][0]))
        liveness_score = score[1]
        
        return liveness_score > threshold, liveness_score
