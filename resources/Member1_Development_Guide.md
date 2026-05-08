# Member 1 — AI Pipeline Engineer: Development Guide
> School Face Attendance System | SCRFD 500M + MiniFASNet V2 + ArcFace R50

---

## Step 0 — Environment Setup

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# Install required packages
pip install insightface onnxruntime opencv-python numpy
pip install faiss-cpu mysql-connector-python python-dotenv

# Download MiniFASNet V2 model weights
git clone https://github.com/minivision-ai/Silent-Face-Anti-Spoofing.git
mkdir -p models
cp Silent-Face-Anti-Spoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx models/
cp Silent-Face-Anti-Spoofing/resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV2SE.onnx models/
```

**Your folder ownership:**
```
school_attendance/
├── pipeline/
│   ├── detector.py          # SCRFD 500M — you write this
│   ├── liveness.py          # MiniFASNet V2 — you write this
│   ├── recognizer.py        # ArcFace R50 + FAISS — you write this
│   └── attendance_logic.py  # Deduplication logic — you write this
├── models/                  # .onnx files go here
└── embeddings/              # FAISS index files go here
```

---

## Step 1 — Face Detector (`pipeline/detector.py`)

```python
import insightface
import numpy as np


class FaceDetector:
    def __init__(self):
        self.app = insightface.app.FaceAnalysis(
            name='buffalo_sc',
            allowed_modules=['detection']
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def detect(self, frame):
        """Returns list of Face objects with .bbox and .kps"""
        return self.app.get(frame)

    def crop_face(self, frame, face, padding=0.25):
        """Crop face with padding for liveness + recognition"""
        x1, y1, x2, y2 = face.bbox.astype(int)
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(frame.shape[1], x2 + pad_x)
        y2 = min(frame.shape[0], y2 + pad_y)
        return frame[y1:y2, x1:x2]
```

**Test it:**
```python
import cv2
from pipeline.detector import FaceDetector

detector = FaceDetector()
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
faces = detector.detect(frame)
print(f"Detected {len(faces)} face(s)")
cap.release()
```

---

## Step 2 — Liveness Detector (`pipeline/liveness.py`)

```python
import onnxruntime as ort
import numpy as np
import cv2


class LivenessDetector:
    def __init__(self, model_path: str, threshold=0.70):
        self.sess = ort.InferenceSession(
            model_path,
            providers=['CPUExecutionProvider']
        )
        self.threshold = threshold

    def check(self, face_crop) -> tuple[bool, float]:
        img = cv2.resize(face_crop, (80, 80))
        img = img.astype(np.float32) / 255.0
        img = (img - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        img = np.transpose(img, (2, 0, 1))[np.newaxis].astype(np.float32)
        out = self.sess.run(None, {self.sess.get_inputs()[0].name: img})[0][0]
        e = np.exp(out - out.max())
        live_score = float(e[1] / e.sum())
        return live_score >= self.threshold, live_score
```

**Test it:**
```python
import cv2
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector

detector = FaceDetector()
liveness = LivenessDetector('models/2.7_80x80_MiniFASNetV2.onnx')

cap = cv2.VideoCapture(0)
ret, frame = cap.read()
faces = detector.detect(frame)
if faces:
    crop = detector.crop_face(frame, faces[0])
    is_live, score = liveness.check(crop)
    print(f"Live: {is_live}, Score: {score:.3f}")
cap.release()
# Hold a printed photo in front of camera — should print Live: False
```

---

## Step 3 — Face Recognizer with FAISS (`pipeline/recognizer.py`)

```python
import insightface
import faiss
import numpy as np
import pickle
import os


class FaceRecognizer:
    def __init__(self, threshold=0.55,
                 index_path='embeddings/faiss.index',
                 names_path='embeddings/names.pkl'):
        self.app = insightface.app.FaceAnalysis(
            name='buffalo_l',
            allowed_modules=['recognition']
        )
        self.app.prepare(ctx_id=0)
        self.threshold = threshold
        self.index_path = index_path
        self.names_path = names_path
        self.index = None
        self.names = []
        self._load()

    def _load(self):
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.names_path, 'rb') as f:
                self.names = pickle.load(f)
        else:
            self.index = faiss.IndexFlatIP(512)  # cosine on L2-normalized vectors

    def add_student(self, name: str, embeddings: list):
        avg = np.mean(embeddings, axis=0).astype(np.float32)
        avg /= np.linalg.norm(avg)  # L2 normalize
        self.index.add(avg[np.newaxis])
        self.names.append(name)
        faiss.write_index(self.index, self.index_path)
        with open(self.names_path, 'wb') as f:
            pickle.dump(self.names, f)

    def get_embedding(self, face_img):
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
```

**Test it:**
```python
import cv2
from pipeline.detector import FaceDetector
from pipeline.recognizer import FaceRecognizer

detector = FaceDetector()
recognizer = FaceRecognizer()

# Register yourself with 10 frames
cap = cv2.VideoCapture(0)
embeddings = []
for i in range(10):
    ret, frame = cap.read()
    faces = detector.detect(frame)
    if faces:
        crop = detector.crop_face(frame, faces[0])
        emb = recognizer.get_embedding(crop)
        if emb is not None:
            embeddings.append(emb)
            print(f"Captured sample {len(embeddings)}")

recognizer.add_student('TestStudent', embeddings)
print("Registered. Now testing identify...")

ret, frame = cap.read()
faces = detector.detect(frame)
if faces:
    crop = detector.crop_face(frame, faces[0])
    name, score = recognizer.identify(crop)
    print(f"Identified: {name}, Score: {score:.3f}")
cap.release()
```

---

## Step 4 — Attendance Logic (`pipeline/attendance_logic.py`)

```python
from datetime import date
from database import get_db_connection


def mark_attendance(student_id: int, confidence: float, camera_id: str) -> bool:
    """
    Returns True if attendance was marked, False if already marked today.
    UNIQUE KEY on (student_id, date) prevents any duplicate inserts.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT IGNORE INTO attendance
               (student_id, date, confidence, camera_id)
               VALUES (%s, %s, %s, %s)''',
            (student_id, date.today(), confidence, camera_id)
        )
        conn.commit()
        return cursor.rowcount > 0  # 0 = duplicate, 1 = new entry
    finally:
        cursor.close()
        conn.close()


def get_student_id_by_name(name: str) -> int | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM students WHERE name=%s AND is_active=1', (name,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None
```

---

## Step 5 — Full Pipeline Integration Test

Create `test_pipeline.py` in the project root and run it to verify all 4 modules work together end-to-end:

```python
import cv2
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer
from pipeline.attendance_logic import mark_attendance, get_student_id_by_name

detector   = FaceDetector()
liveness   = LivenessDetector('models/2.7_80x80_MiniFASNetV2.onnx')
recognizer = FaceRecognizer()

cap = cv2.VideoCapture(0)
print("Running pipeline on 10 frames...\n")

for i in range(10):
    ret, frame = cap.read()
    if not ret:
        print("Camera read failed"); break

    faces = detector.detect(frame)
    print(f"Frame {i+1}: {len(faces)} face(s) detected")

    for face in faces:
        crop = detector.crop_face(frame, face)

        # Stage 2: Liveness
        is_live, live_score = liveness.check(crop)
        if not is_live:
            print(f"  → SPOOF detected (score: {live_score:.3f})")
            continue

        # Stage 3: Recognition
        name, confidence = recognizer.identify(crop)
        if name == 'Unknown':
            print(f"  → UNKNOWN face (confidence: {confidence:.3f})")
            continue

        # Mark attendance
        student_id = get_student_id_by_name(name)
        if student_id:
            marked = mark_attendance(student_id, confidence, 'test_cam')
            status = 'MARKED' if marked else 'ALREADY MARKED'
            print(f"  → {name} | {status} | confidence: {confidence:.3f} | live: {live_score:.3f}")
        else:
            print(f"  → {name} recognized but not found in DB")

cap.release()
print("\nPipeline test complete.")
```

**Expected output for a registered person:**
```
Frame 1: 1 face(s) detected
  → YourName | MARKED | confidence: 0.712 | live: 0.891
Frame 2: 1 face(s) detected
  → YourName | ALREADY MARKED | confidence: 0.698 | live: 0.874
...
```

---

## Threshold Tuning Reference

| Parameter | Default | Lower if... | Raise if... |
|---|---|---|---|
| `LIVENESS_THRESHOLD` | `0.70` | Real students blocked as spoof | Printed photos pass through |
| `SIMILARITY_THRESHOLD` | `0.55` | Known students not recognized | Wrong student is matched |
| `det_size` in detector | `(640,640)` | Faces missed on slow CPU → use `(320,320)` | — |
| Registration samples | `15 min` | Recognition errors → use 25+ | — |

---

## Day-by-Day Checklist

### Day 1
- [ ] Virtual environment created and all packages installed
- [ ] MiniFASNet `.onnx` files copied to `models/`
- [ ] `detector.py` written and tested — face detected from webcam
- [ ] `liveness.py` written and tested — photo rejected, real face accepted

### Day 2
- [ ] `recognizer.py` written — `add_student()` saves to FAISS, `identify()` returns correct name
- [ ] `attendance_logic.py` written — `mark_attendance()` inserts to MySQL, returns `False` on duplicate
- [ ] `test_pipeline.py` runs successfully on 10 frames with correct JSON output

### Day 3
- [ ] Thresholds tuned in actual classroom lighting
- [ ] Member 2 imports your pipeline modules into `main.py` without errors
- [ ] Multi-face test: 3 people in frame → all recognized correctly
