import cv2
import os
import numpy as np
from pipeline.detector import FaceDetector
from pipeline.liveness import LivenessDetector
from pipeline.recognizer import FaceRecognizer
from pipeline.attendance import mark_attendance

def main():
    print("Initializing Pipeline...")
    detector = FaceDetector()
    
    # Graceful handling for missing liveness models
    liveness = None
    if os.path.exists('models/2.7_80x80_MiniFASNetV2.onnx'):
        liveness = LivenessDetector('models/2.7_80x80_MiniFASNetV2.onnx')
        print("Liveness module loaded.")
    else:
        print("Warning: Liveness model not found. Liveness check will be bypassed.")
        
    recognizer = FaceRecognizer()
    print("Recognizer module loaded.")

    # Create dummy image for testing if no inputs provided
    test_img_path = 'test_face.jpg'
    if not os.path.exists(test_img_path):
        # Create a black image with a white square as a placeholder
        dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(dummy_img, "No Input Camera/Image", (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imwrite(test_img_path, dummy_img)
        print(f"Created placeholder test image: {test_img_path}")

    # Process test image
    frame = cv2.imread(test_img_path)
    faces = detector.detect(frame)
    print(f"Detected {len(faces)} faces.")

    for i, face in enumerate(faces):
        crop = detector.crop_face(frame, face)
        
        # 1. Liveness Check
        is_live = True
        l_score = 1.0
        if liveness:
            is_live, l_score = liveness.is_live(crop)
            print(f"Face {i}: Liveness Score: {l_score:.4f} (Live: {is_live})")
        
        if is_live:
            # 2. Recognition Check
            embedding = recognizer.get_embedding(crop)
            if embedding is not None:
                student_id = recognizer.search(embedding)
                if student_id:
                    print(f"Face {i}: Identified as Student ID: {student_id}")
                    # 3. Mark Attendance (Requires DB connection)
                    # mark_attendance(student_id)
                else:
                    print(f"Face {i}: Unknown Student")
            else:
                print(f"Face {i}: Failed to extract embedding")
        else:
            print(f"Face {i}: Spoof detected!")

    print("Pipeline Test Completed.")

if __name__ == "__main__":
    main()
