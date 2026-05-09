"""
Live registration + verification test.
Bypasses FastAPI entirely. No interactive prompts — uses countdown timers.

Run:
  python live_test.py

Phase 1: 5-second countdown, then captures 20 frames for registration.
Phase 2: 5-second countdown, then captures 10 frames for verification.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import time
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer
from config import LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD

# ── Load models ───────────────────────────────────────────────
print("\n=== Loading models ===")
detector   = FaceDetector()
liveness   = LivenessDetector(LIVENESS_MODEL_PATH, LIVENESS_THRESHOLD) if os.path.exists(LIVENESS_MODEL_PATH) else None
recognizer = FaceRecognizer(threshold=0.0)   # threshold=0 → always show best score
print(f"  Liveness  : {'loaded threshold=' + str(LIVENESS_THRESHOLD) if liveness else 'NOT FOUND'}")
print(f"  Recognizer: w600k_r50.onnx (ArcFace R50 direct)")

# ── Camera helper ──────────────────────────────────────────────
def open_camera():
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print("ERROR: cannot open camera."); sys.exit(1)
    for _ in range(8):          # discard first frames (auto-exposure settle)
        cap.read()
    return cap

def countdown_and_capture(cap, phase_label, n_frames, countdown_secs=5, interval_ms=300):
    """Show countdown overlay, then capture n_frames that contain a face."""
    deadline = time.time() + countdown_secs
    print(f"\n  {phase_label}: face the camera — capturing in {countdown_secs}s …")

    # Countdown
    while time.time() < deadline:
        ret, frame = cap.read()
        if not ret: continue
        remaining = int(deadline - time.time()) + 1
        display = frame.copy()
        cv2.putText(display, f"{phase_label}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.putText(display, f"Starting in {remaining}s ...", (20, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
        cv2.imshow("Live Test — press Q to quit", display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cv2.destroyAllWindows(); sys.exit(0)

    # Capture
    captured = []
    while len(captured) < n_frames:
        ret, frame = cap.read()
        if not ret: continue
        faces = detector.detect(frame)
        display = frame.copy()
        for f in faces:
            x1,y1,x2,y2 = f.bbox.astype(int)
            cv2.rectangle(display,(x1,y1),(x2,y2),(0,255,0),2)
        cv2.putText(display, f"{phase_label}  {len(captured)}/{n_frames}", (20,40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
        cv2.imshow("Live Test — press Q to quit", display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cv2.destroyAllWindows(); sys.exit(0)
        if faces:
            captured.append((frame.copy(), faces))
            time.sleep(interval_ms / 1000)

    return captured


# ═══════════════════════════════════════════════════════════════
#  PHASE 1 — REGISTRATION
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  PHASE 1 — REGISTRATION  (20 frames)")
print("="*60)

cap = open_camera()
reg_captured = countdown_and_capture(cap, "REGISTRATION", n_frames=20, countdown_secs=5)
cap.release()
cv2.destroyAllWindows()
print(f"  Captured {len(reg_captured)} frames.")

reg_embeddings = []
reg_liveness_scores = []
reg_aligned_samples = []   # save a few for visual inspection later
reg_embed_fails = 0

for i, (frame, faces) in enumerate(reg_captured):
    face    = faces[0]
    crop    = detector.crop_face(frame, face)
    aligned = detector.align_face(frame, face)

    live_pass, live_score = (True, 1.0)
    if liveness:
        live_pass, live_score = liveness.check(crop)
    reg_liveness_scores.append(live_score)

    emb = recognizer.get_embedding(aligned)
    if emb is not None:
        reg_embeddings.append(emb)
        if len(reg_aligned_samples) < 3:
            reg_aligned_samples.append(aligned.copy())
    else:
        reg_embed_fails += 1

    print(f"  Frame {i+1:2d}: live={live_score:.3f}(pass={live_pass}) "
          f"embed={'OK  norm='+str(round(float(np.linalg.norm(emb)),4)) if emb is not None else 'FAIL'}")

print(f"\n  --- Registration stats ---")
print(f"  Liveness  : min={min(reg_liveness_scores):.3f}  max={max(reg_liveness_scores):.3f}  mean={np.mean(reg_liveness_scores):.3f}")
print(f"  Embeddings: {len(reg_embeddings)} OK / {reg_embed_fails} FAIL")

if not reg_embeddings:
    print("\n  FATAL: No embeddings generated. Pipeline broken at get_embedding().")
    sys.exit(1)

avg_emb = np.mean(reg_embeddings, axis=0).astype(np.float32)
avg_emb /= np.linalg.norm(avg_emb)
print(f"  Avg emb norm: {np.linalg.norm(avg_emb):.4f}  dim={avg_emb.shape[0]}")

cosines = [float(np.dot(e, avg_emb)) for e in reg_embeddings]
print(f"  Intra-reg cosine: min={min(cosines):.3f}  max={max(cosines):.3f}  mean={np.mean(cosines):.3f}")
print(f"  (healthy intra-reg should be > 0.85)")


# ═══════════════════════════════════════════════════════════════
#  PHASE 2 — VERIFICATION  (10-second gap, then capture)
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  PHASE 2 — VERIFICATION  (10 frames, 10s gap)")
print("="*60)

cap = open_camera()
ver_captured = countdown_and_capture(cap, "VERIFICATION", n_frames=10, countdown_secs=10)
cap.release()
cv2.destroyAllWindows()

ver_similarities = []
ver_liveness_scores = []
ver_embed_fails = 0

print(f"\n  {'Frame':>5}  {'Live':>6}  {'Pass':>5}  {'Embed':>5}  {'Cosine':>8}  {'@0.40':>7}  {'@0.30':>7}")
print(f"  {'-'*58}")

for i, (frame, faces) in enumerate(ver_captured):
    face    = faces[0]
    crop    = detector.crop_face(frame, face)
    aligned = detector.align_face(frame, face)

    live_pass, live_score = (True, 1.0)
    if liveness:
        live_pass, live_score = liveness.check(crop)
    ver_liveness_scores.append(live_score)

    emb = recognizer.get_embedding(aligned)
    if emb is None:
        ver_embed_fails += 1
        print(f"  {i+1:>5}  {live_score:>6.3f}  {str(live_pass):>5}  {'FAIL':>5}  {'---':>8}  {'---':>7}  {'---':>7}")
        continue

    cosine = float(np.dot(emb, avg_emb))
    ver_similarities.append(cosine)
    print(f"  {i+1:>5}  {live_score:>6.3f}  {str(live_pass):>5}  {'OK':>5}  {cosine:>8.4f}"
          f"  {'PASS' if cosine>=0.40 else 'FAIL':>7}  {'PASS' if cosine>=0.30 else 'FAIL':>7}")


# ═══════════════════════════════════════════════════════════════
#  PHASE 3 — DIAGNOSIS
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  PHASE 3 — DIAGNOSIS")
print("="*60)

if ver_similarities:
    mean_c = np.mean(ver_similarities)
    print(f"\n  Cosine similarity (reg vs ver):")
    print(f"    min={min(ver_similarities):.4f}  max={max(ver_similarities):.4f}  mean={mean_c:.4f}")
    print(f"    threshold 0.40 → {'PASS' if mean_c>=0.40 else 'FAIL'}")
    print(f"    threshold 0.35 → {'PASS' if mean_c>=0.35 else 'FAIL'}")
    print(f"    threshold 0.30 → {'PASS' if mean_c>=0.30 else 'FAIL'}")
    print(f"    threshold 0.25 → {'PASS' if mean_c>=0.25 else 'FAIL'}")

print(f"\n  Liveness (verification frames):")
print(f"    min={min(ver_liveness_scores):.3f}  max={max(ver_liveness_scores):.3f}  mean={np.mean(ver_liveness_scores):.3f}")
print(f"    current threshold={LIVENESS_THRESHOLD}  → {'PASS' if np.mean(ver_liveness_scores)>=LIVENESS_THRESHOLD else 'FAILING'}")

print(f"\n  Issues found:")
issues = []

if not ver_similarities:
    issues.append("CRITICAL — get_embedding() returns None during verification.")
else:
    mean_c = np.mean(ver_similarities)
    if mean_c < 0.10:
        issues.append(f"CRITICAL — cosine={mean_c:.3f} near zero: embeddings are essentially random. "
                      "Likely ArcFace preprocessing bug (wrong channel order or normalization).")
    elif mean_c < 0.25:
        issues.append(f"HIGH — cosine={mean_c:.3f}: very low. Face alignment inconsistency "
                      "OR model receiving wrong input format.")
    elif mean_c < 0.40:
        issues.append(f"MEDIUM — cosine={mean_c:.3f}: below threshold 0.40. "
                      f"Lower threshold to {round(mean_c-0.05,2)} to fix.")
    else:
        issues.append(f"OK — cosine={mean_c:.3f}: verification should pass at threshold 0.40.")

if liveness and np.mean(ver_liveness_scores) < LIVENESS_THRESHOLD:
    issues.append(f"LIVENESS BLOCKING — mean={np.mean(ver_liveness_scores):.3f} < threshold={LIVENESS_THRESHOLD}. "
                  f"Lower to {round(np.mean(ver_liveness_scores)-0.05,2)}.")

if np.mean(cosines) < 0.80:
    issues.append(f"INCONSISTENT REGISTRATION — intra-reg mean cosine={np.mean(cosines):.3f} < 0.80. "
                  "Registration samples vary too much (lighting/angle). Expected >0.85.")

for i, iss in enumerate(issues, 1):
    print(f"  [{i}] {iss}")

if not issues:
    print("  None — pipeline looks healthy.")

print("\n" + "="*60 + "\n")
