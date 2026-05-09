"""
Active liveness challenges using buffalo_l 2d106det landmarks.

Challenges:
  - blink         : detect rapid drop+rise in Eye-Aspect-Ratio (EAR)
  - smile         : detect rise in Mouth-Aspect-Ratio (smile widens & flattens)
  - turn_left     : nose moves significantly left of face center
  - turn_right    : nose moves significantly right of face center
"""
import os
import insightface
import numpy as np
import cv2


# ── 106-point landmark indices used by InsightFace 2d106det ────────────
# Reference: insightface buffalo_l 2d106 landmarks
LM = {
    # Right eye contour (subject's right, image left)
    'right_eye': [35, 36, 33, 37, 39, 42, 40, 41],
    # Left eye contour
    'left_eye':  [89, 90, 87, 91, 93, 96, 94, 95],
    # Mouth (outer)
    'mouth_left':   52,
    'mouth_right':  61,
    'mouth_top':    72,
    'mouth_bottom': 85,
    # Nose tip
    'nose_tip': 86,
    # Face contour
    'face_left':  1,
    'face_right': 17,
}


class LandmarkExtractor:
    """Loads buffalo_l 2d106det.onnx for 106 facial landmarks."""
    def __init__(self):
        self.app = insightface.app.FaceAnalysis(
            name='buffalo_l',
            allowed_modules=['detection', 'landmark_2d_106']
        )
        self.app.prepare(ctx_id=0, det_size=(320, 320))

    def get_landmarks(self, frame) -> np.ndarray | None:
        faces = self.app.get(frame)
        if not faces:
            return None
        f = faces[0]
        return getattr(f, 'landmark_2d_106', None)


def _eye_aspect_ratio(pts: np.ndarray) -> float:
    """EAR — small when eye closed, large when open."""
    if pts is None or len(pts) < 6:
        return 0.0
    # vertical / horizontal distances
    A = np.linalg.norm(pts[1] - pts[5])
    B = np.linalg.norm(pts[2] - pts[4])
    C = np.linalg.norm(pts[0] - pts[3])
    if C == 0:
        return 0.0
    return (A + B) / (2.0 * C)


def compute_metrics(lm106: np.ndarray) -> dict:
    """Single-frame facial metrics from 106 landmarks."""
    if lm106 is None or len(lm106) < 106:
        return {}

    le = lm106[LM['left_eye'][:6]]
    re = lm106[LM['right_eye'][:6]]
    ear = (_eye_aspect_ratio(le) + _eye_aspect_ratio(re)) / 2.0

    m_l = lm106[LM['mouth_left']]
    m_r = lm106[LM['mouth_right']]
    m_t = lm106[LM['mouth_top']]
    m_b = lm106[LM['mouth_bottom']]
    mouth_w = float(np.linalg.norm(m_r - m_l))
    mouth_h = float(np.linalg.norm(m_b - m_t))

    nose = lm106[LM['nose_tip']]
    f_l = lm106[LM['face_left']]
    f_r = lm106[LM['face_right']]
    face_w = float(np.linalg.norm(f_r - f_l))
    if face_w == 0:
        nose_x_norm = 0.0
    else:
        # 0.5 = nose centered, <0.5 = turned right, >0.5 = turned left
        # (image coords: smaller x = left of image)
        face_center_x = (f_l[0] + f_r[0]) / 2.0
        nose_x_norm = (nose[0] - face_center_x) / face_w

    return {
        'ear': float(ear),
        'mouth_w': mouth_w,
        'mouth_h': mouth_h,
        'mouth_ratio': mouth_w / mouth_h if mouth_h > 0 else 0.0,
        'nose_x_norm': float(nose_x_norm),
        'face_w': face_w,
    }


# ── Challenge state machines ───────────────────────────────────────────

class BlinkChallenge:
    """Pass when EAR drops below low threshold then rises back."""
    EAR_OPEN = 0.22
    EAR_CLOSE = 0.15
    label = 'Please blink your eyes'

    def __init__(self):
        self.saw_close = False
        self.passed = False

    def update(self, m: dict) -> bool:
        if not m:
            return self.passed
        ear = m.get('ear', 0)
        if ear < self.EAR_CLOSE:
            self.saw_close = True
        elif ear > self.EAR_OPEN and self.saw_close:
            self.passed = True
        return self.passed


class SmileChallenge:
    """Pass when mouth ratio (width/height) increases significantly above baseline."""
    BASELINE_FRAMES = 5
    DELTA = 0.6     # mouth_ratio must increase by ≥ 0.6
    label = 'Please smile'

    def __init__(self):
        self.baseline = []
        self.passed = False

    def update(self, m: dict) -> bool:
        if not m:
            return self.passed
        ratio = m.get('mouth_ratio', 0)
        if len(self.baseline) < self.BASELINE_FRAMES:
            self.baseline.append(ratio)
            return False
        base = np.mean(self.baseline)
        if ratio > base + self.DELTA:
            self.passed = True
        return self.passed


class HeadTurnChallenge:
    """Pass when nose moves left or right beyond threshold from baseline."""
    BASELINE_FRAMES = 5
    DELTA = 0.12
    def __init__(self, direction: str):
        assert direction in ('left', 'right')
        self.direction = direction
        self.label = f'Turn your head to the {direction}'
        self.baseline = []
        self.passed = False

    def update(self, m: dict) -> bool:
        if not m:
            return self.passed
        x = m.get('nose_x_norm', 0)
        if len(self.baseline) < self.BASELINE_FRAMES:
            self.baseline.append(x)
            return False
        base = np.mean(self.baseline)
        if self.direction == 'left' and x > base + self.DELTA:
            self.passed = True
        elif self.direction == 'right' and x < base - self.DELTA:
            self.passed = True
        return self.passed


def make_challenge(name: str):
    if name == 'blink':       return BlinkChallenge()
    if name == 'smile':       return SmileChallenge()
    if name == 'turn_left':   return HeadTurnChallenge('left')
    if name == 'turn_right':  return HeadTurnChallenge('right')
    raise ValueError(f'Unknown challenge: {name}')
