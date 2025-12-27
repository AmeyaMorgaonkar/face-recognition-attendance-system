import time
import cv2
import functions

# Initialize face recognizer
face_recognizer = functions.FaceRecognizer(known_faces_dir="known_faces")

# Try to load existing model, or train from known_faces directory
print("Loading face recognition model...")
if not face_recognizer.load_model():
    print("No existing model found. Training from known_faces directory...")
    face_recognizer.load_known_faces()
print("Ready!")

video = cv2.VideoCapture(0)
# time.sleep(1)

print("\nControls:")
print("  'q' - Quit")
print("  'c' - Capture and save current face (you'll be prompted for name)")
print("  'r' - Reload/retrain from known_faces directory\n")

while True:
    check, frame = video.read()
    
    if check == False:
        continue

    # Recognize faces in the frame
    frame, recognized = face_recognizer.recognize_faces(frame)
    
    cv2.imshow("Face Recognition Attendance System", frame)

    key = cv2.waitKey(1)

    if key == ord('q'):
        break
    elif key == ord('c'):
        # Capture face - pause video and get name
        cv2.destroyAllWindows()
        person_name = input("Enter the person's name: ").strip()
        if person_name:
            success = face_recognizer.capture_face(frame, person_name)
            if success:
                # Retrain to include the new face
                print("Retraining model with new face...")
                face_recognizer.load_known_faces()
        else:
            print("No name entered, skipping capture.")
    elif key == ord('r'):
        # Reload/retrain from known_faces
        print("Retraining from known_faces directory...")
        face_recognizer.load_known_faces()

video.release()
cv2.destroyAllWindows()