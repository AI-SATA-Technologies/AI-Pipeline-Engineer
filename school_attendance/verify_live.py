"""
Live verification against the CURRENT FAISS index.
Captures 10 frames, prints similarity vs every registered student.
No interactive prompts — countdown then auto-capture.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import faiss, pickle
from pipeline.detector import FaceDetector
from pipeline.recognizer import FaceRecognizer

print("=== Loading models ===")
detector   = FaceDetector()
recognizer = FaceRecognizer(threshold=0.0)

# Show what's registered
idx = recognizer.index
names = recognizer.names
print(f"\nFAISS index: {idx.ntotal} entries")
print(f"Names      : {names}")

if idx.ntotal == 0:
    print("\nERROR: nothing registered. Re-register first.")
    sys.exit(1)

# Get all stored embeddings
stored = idx.reconstruct_n(0, idx.ntotal)
print(f"Stored embeddings shape: {stored.shape}")
print(f"Stored embedding norms : {[round(float(np.linalg.norm(v)),4) for v in stored]}")

# Open camera
cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
for _ in range(8): cap.read()

print("\nCountdown 5s — face the camera …")
deadline = time.time() + 5
while time.time() < deadline:
    ret, frame = cap.read()
    if not ret: continue
    rem = int(deadline - time.time()) + 1
    disp = frame.copy()
    cv2.putText(disp, f"Capturing in {rem}s", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,165,255), 3)
    cv2.imshow("Verify Live (Q=quit)", disp)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        cv2.destroyAllWindows(); sys.exit(0)

print("\n  Frame  faces  best_name        best_sim   sim_to_each_student")
print("  " + "-" * 80)

results_per_name = {n: [] for n in names}
captured = 0
while captured < 10:
    ret, frame = cap.read()
    if not ret: continue
    faces = detector.detect(frame)
    disp = frame.copy()
    for f in faces:
        x1,y1,x2,y2 = f.bbox.astype(int)
        cv2.rectangle(disp,(x1,y1),(x2,y2),(0,255,0),2)
    cv2.putText(disp, f"capturing {captured}/10", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
    cv2.imshow("Verify Live (Q=quit)", disp)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        cv2.destroyAllWindows(); break

    if not faces:
        continue

    face = faces[0]
    aligned = detector.align_face(frame, face)
    emb = recognizer.get_embedding(aligned)
    if emb is None:
        continue

    # Cosine vs each registered embedding
    sims = stored @ emb
    best_i = int(np.argmax(sims))
    captured += 1

    detail = "  ".join([f"{n}={s:.3f}" for n, s in zip(names, sims)])
    print(f"  {captured:>5}  {len(faces):>5}  {names[best_i]:<14}  {sims[best_i]:>8.4f}   {detail}")

    for n, s in zip(names, sims):
        results_per_name[n].append(float(s))

    time.sleep(0.3)

cap.release()
cv2.destroyAllWindows()

print("\n=== Summary ===")
for n, scores in results_per_name.items():
    if scores:
        print(f"  {n:<15}: min={min(scores):.4f}  max={max(scores):.4f}  mean={np.mean(scores):.4f}")

# Pick winner
overall_winner = max(results_per_name.items(), key=lambda kv: np.mean(kv[1]) if kv[1] else -1)
print(f"\n  Best overall match: {overall_winner[0]}  (mean sim={np.mean(overall_winner[1]):.4f})")
print(f"  Current threshold : 0.40  → {'WOULD PASS' if np.mean(overall_winner[1])>=0.40 else 'WOULD FAIL'}")

if np.mean(overall_winner[1]) < 0.40:
    print(f"\n  RECOMMENDATION: lower SIMILARITY_THRESHOLD to {round(np.mean(overall_winner[1])-0.05,2)}")
print()
