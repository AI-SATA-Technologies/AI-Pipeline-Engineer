"""
Active liveness challenges using the 5 keypoints already returned by the
main SCRFD face detector — no extra model required.

Keypoint layout (InsightFace):
  kps[0] = left eye,  kps[1] = right eye,  kps[2] = nose tip
  kps[3] = left mouth corner,  kps[4] = right mouth corner

Challenges:
  - smile       : mouth widens relative to neutral baseline
  - turn_left   : nose shifts left of eye midpoint
  - turn_right  : nose shifts right of eye midpoint
  - nod         : face center drops then returns (head nod)
"""
import numpy as np


def compute_metrics(face) -> dict:
    """Return challenge metrics from a detected face object."""
    kps = getattr(face, 'kps', None)
    bbox = getattr(face, 'bbox', None)
    if kps is None or bbox is None or len(kps) < 5:
        return {}

    left_eye, right_eye, nose, left_mouth, right_mouth = [np.array(p, dtype=float) for p in kps[:5]]
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    face_w = x2 - x1
    face_h = y2 - y1
    if face_w <= 0 or face_h <= 0:
        return {}

    eye_mid_x = (left_eye[0] + right_eye[0]) / 2.0

    # Positive = nose right of eye midpoint (head turned left in image)
    # Negative = nose left of eye midpoint (head turned right in image)
    nose_x_norm = (float(nose[0]) - eye_mid_x) / face_w

    # Face bounding-box vertical centre (pixels) — shifts when person nods
    face_center_y = (y1 + y2) / 2.0

    # Mouth width as fraction of face width — increases when smiling
    mouth_width = float(np.linalg.norm(right_mouth - left_mouth))
    mouth_ratio = mouth_width / face_w

    return {
        'nose_x_norm': nose_x_norm,
        'face_center_y': face_center_y,
        'face_h': face_h,
        'mouth_ratio': mouth_ratio,
        'face_w': face_w,
    }


# ── Challenge state machines ───────────────────────────────────────────────

class SmileChallenge:
    BASELINE_FRAMES = 8
    DELTA = 0.08    # mouth_ratio must rise ≥ 8 pp above neutral baseline
    label = 'Please smile'

    def __init__(self):
        self.baseline = []
        self.passed = False

    def update(self, m: dict) -> bool:
        if not m:
            return self.passed
        ratio = m.get('mouth_ratio', 0.0)
        if len(self.baseline) < self.BASELINE_FRAMES:
            self.baseline.append(ratio)
            return False
        if ratio > float(np.mean(self.baseline)) + self.DELTA:
            self.passed = True
        return self.passed


class HeadTurnChallenge:
    BASELINE_FRAMES = 8
    DELTA = 0.07    # nose must shift ≥ 7% of face width from neutral

    def __init__(self, direction: str):
        assert direction in ('left', 'right')
        self.direction = direction
        self.label = f'Turn your head to the {direction}'
        self.baseline = []
        self.passed = False

    def update(self, m: dict) -> bool:
        if not m:
            return self.passed
        x = m.get('nose_x_norm', 0.0)
        if len(self.baseline) < self.BASELINE_FRAMES:
            self.baseline.append(x)
            return False
        base = float(np.mean(self.baseline))
        if self.direction == 'left' and x > base + self.DELTA:
            self.passed = True
        elif self.direction == 'right' and x < base - self.DELTA:
            self.passed = True
        return self.passed


class NodChallenge:
    """Pass when face centre drops ≥ 5% of face height then returns up."""
    BASELINE_FRAMES = 8
    DELTA = 0.05
    label = 'Please nod your head'

    def __init__(self):
        self.baseline_y = []
        self.baseline_h = []
        self.saw_down = False
        self.passed = False

    def update(self, m: dict) -> bool:
        if not m:
            return self.passed
        cy = m.get('face_center_y', 0.0)
        fh = m.get('face_h', 1.0)
        if len(self.baseline_y) < self.BASELINE_FRAMES:
            self.baseline_y.append(cy)
            self.baseline_h.append(fh)
            return False
        base_y = float(np.mean(self.baseline_y))
        base_h = float(np.mean(self.baseline_h)) or 1.0
        offset = (cy - base_y) / base_h   # positive = moved down
        if offset > self.DELTA:
            self.saw_down = True
        elif self.saw_down and offset < self.DELTA / 2:
            self.passed = True
        return self.passed


def make_challenge(name: str):
    if name == 'smile':       return SmileChallenge()
    if name == 'turn_left':   return HeadTurnChallenge('left')
    if name == 'turn_right':  return HeadTurnChallenge('right')
    if name == 'nod':         return NodChallenge()
    raise ValueError(f'Unknown challenge: {name}')
