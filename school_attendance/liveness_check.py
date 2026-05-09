"""Quick liveness sanity check — 5 frames, prints live scores."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import cv2, time
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from config import LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD

detector = FaceDetector()
liveness = LivenessDetector(LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD)
print(f"Threshold: {LIVENESS_THRESHOLD}\n")

cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
for _ in range(8): cap.read()

print("Capturing 5 frames in 3 seconds … face the camera.")
time.sleep(3)

results = []
while len(results) < 5:
    ret, frame = cap.read()
    if not ret: continue
    faces = detector.detect(frame)
    if not faces: continue
    crop = detector.crop_face(frame, faces[0])
    live_pass, live_score = liveness.check(crop)
    results.append((live_score, live_pass))
    print(f"  Frame {len(results)}: score={live_score:.4f}  pass={live_pass}")

cap.release()
mean = sum(s for s,_ in results) / len(results)
print(f"\n  Mean live score: {mean:.4f}")
print(f"  Result: {'ALL PASS — liveness fixed!' if all(p for _,p in results) else 'SOME FAIL — check scores above'}")
