"""
Full pipeline integration test.
Uses test_face.jpg if present; falls back to a synthetic image.
Run: python test_pipeline.py
"""
import os
import sys
import numpy as np
import cv2

from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer


def make_test_image():
    img = np.ones((480, 640, 3), dtype=np.uint8) * 200
    cv2.putText(img, "Test Image (no face)", (120, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (80, 80, 80), 2)
    return img


def main():
    print("=" * 50)
    print("Pipeline Integration Test")
    print("=" * 50)

    print("\n[1] Loading FaceDetector (SCRFD 500M)...")
    detector = FaceDetector()
    print("    OK")

    liveness = None
    model_path = 'models/2.7_80x80_MiniFASNetV2.onnx'
    print(f"\n[2] Loading LivenessDetector...")
    if os.path.exists(model_path):
        liveness = LivenessDetector(model_path, threshold=0.70)
        print("    OK")
    else:
        print(f"    SKIPPED — model not found at {model_path}")
        print("    Run 'python setup_liveness.py' to enable liveness detection.")

    print("\n[3] Loading FaceRecognizer (ArcFace R50)...")
    recognizer = FaceRecognizer(threshold=0.55)
    print(f"    OK — {recognizer.index.ntotal} student(s) in index")

    img_path = 'test_face.jpg'
    if os.path.exists(img_path):
        frame = cv2.imread(img_path)
        print(f"\n[4] Using image: {img_path}")
    else:
        frame = make_test_image()
        print("\n[4] Using synthetic test image (no real face)")

    faces = detector.detect(frame)
    print(f"\nDetected {len(faces)} face(s)")

    for i, face in enumerate(faces):
        crop = detector.crop_face(frame, face)
        print(f"\n  Face {i + 1}:")
        print(f"    BBox: {face.bbox.astype(int).tolist()}")
        print(f"    Crop shape: {crop.shape}")

        if liveness:
            is_live, score = liveness.check(crop)
            print(f"    Liveness: {'LIVE' if is_live else 'SPOOF'} (score={score:.3f})")
            if not is_live:
                continue

        name, conf = recognizer.identify(crop)
        print(f"    Identity: {name} (confidence={conf:.3f})")

    if not faces:
        print("  (No faces to process — pipeline loaded successfully)")

    print("\n" + "=" * 50)
    print("All pipeline components loaded OK.")
    if not os.path.exists(model_path):
        print("NOTE: Run 'python setup_liveness.py' to enable liveness detection.")
    print("=" * 50)


if __name__ == '__main__':
    main()
