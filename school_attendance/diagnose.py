"""Real-time pipeline diagnostic — shows exactly where recognition fails."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

import cv2
import numpy as np
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer
from config import LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD, SIMILARITY_THRESHOLD, FAISS_INDEX_PATH, FAISS_NAMES_PATH

print("Loading models...")
detector  = FaceDetector()
liveness  = LivenessDetector(LIVENESS_MODEL_PATH, threshold=LIVENESS_THRESHOLD) if os.path.exists(LIVENESS_MODEL_PATH) else None
recognizer = FaceRecognizer(threshold=SIMILARITY_THRESHOLD, index_path=FAISS_INDEX_PATH, names_path=FAISS_NAMES_PATH)

print(f"\nConfig — liveness_threshold={LIVENESS_THRESHOLD}  similarity_threshold={SIMILARITY_THRESHOLD}")
print(f"Students in FAISS index: {recognizer.index.ntotal}")

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Cannot open camera"); sys.exit(1)

print("\nPress Q to quit. Watch the console for live scores.\n")
frame_n = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_n += 1

    faces = detector.detect(frame)
    display = frame.copy()

    if not faces:
        cv2.putText(display, "No face detected", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
    else:
        for i, face in enumerate(faces):
            x1, y1, x2, y2 = face.bbox.astype(int)
            crop = detector.crop_face(frame, face)

            # --- liveness ---
            live_pass = True
            live_score = 1.0
            if liveness:
                live_pass, live_score = liveness.check(crop)

            # --- embedding & similarity ---
            emb = recognizer.get_embedding(crop)
            sim_score = 0.0
            match_name = "No embedding"
            if emb is not None and recognizer.index.ntotal > 0:
                q = emb[np.newaxis].astype(np.float32)
                scores, idxs = recognizer.index.search(q, 1)
                sim_score = float(scores[0][0])
                match_name = recognizer.names[idxs[0][0]]

            # --- decide ---
            if not live_pass:
                label = f"SPOOF live={live_score:.2f}"
                color = (0, 0, 255)
            elif emb is None:
                label = "Embed=None (face too small?)"
                color = (0, 165, 255)
            elif sim_score >= SIMILARITY_THRESHOLD:
                label = f"{match_name} sim={sim_score:.2f}"
                color = (0, 255, 0)
            else:
                label = f"Unknown sim={sim_score:.2f} need>={SIMILARITY_THRESHOLD}"
                color = (0, 165, 255)

            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            cv2.putText(display, label, (x1, max(y1-10,10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # print every 15 frames
            if frame_n % 15 == 0:
                print(f"Face {i}: live={live_score:.3f}(pass={live_pass})  "
                      f"embed={'OK' if emb is not None else 'FAIL'}  "
                      f"sim={sim_score:.3f}(need>={SIMILARITY_THRESHOLD})  "
                      f"match='{match_name}'")

    cv2.imshow("Pipeline Diagnostic — press Q to quit", display)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
