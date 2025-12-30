import time
import cv2
import os
import numpy as np
import pickle

def draw(img, classifier, scaleFactor, minNeighbors, color, text):
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    parts = classifier.detectMultiScale(gray_img, scaleFactor, minNeighbors)
    coords = []
    for (x, y, w, h) in parts:
        cv2.rectangle(img, (x, y), (x+w, y+h), color, thickness=2)
        cv2.putText(img, text, (x, y-4), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 1, cv2.LINE_AA)
        coords = [x, y, w, h]

    return coords

def detect_face(img, faceCascade, eyeCascade):
    coords = draw(img, faceCascade, 1.1, 4, (255, 0, 0), "Face")
    
    if len(coords) == 4:
        roi_image = img[coords[1]: coords[1] + coords[3], coords[0]: coords[0] + coords[2]]
        coords = draw(roi_image, eyeCascade, 1.1, 8, (0, 0, 255), "Eyes")

    return img


class FaceRecognizer:
    """Face recognizer using OpenCV's LBPH algorithm - pip installable only"""
    
    def __init__(self, known_faces_dir="known_faces", model_path="face_model.yml"):
        self.known_faces_dir = known_faces_dir
        self.model_path = model_path
        self.labels_path = "face_labels.pkl"
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        # Improved LBPH parameters for better lighting tolerance
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=2,        # Larger radius captures more texture
            neighbors=16,    # More neighbors for better accuracy
            grid_x=8,        # Finer grid for more detail
            grid_y=8
        )
        self.label_to_name = {}
        self.name_to_label = {}
        self.is_trained = False
        # CLAHE for lighting normalization
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    
    def preprocess_face(self, gray_face):
        """Apply preprocessing to normalize lighting variations."""
        # Apply CLAHE for adaptive histogram equalization
        normalized = self.clahe.apply(gray_face)
        # Optional: Gaussian blur to reduce noise
        normalized = cv2.GaussianBlur(normalized, (3, 3), 0)
        return normalized
        
    def load_known_faces(self):
        """
        Load and train the recognizer with faces from the known_faces directory.
        
        Directory structure:
        known_faces/
            Person1/
                image1.jpg
                image2.jpg
            Person2/
                image1.jpg
        """
        faces = []
        labels = []
        current_label = 0
        self.label_to_name = {}
        self.name_to_label = {}
        
        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir)
            print(f"Created '{self.known_faces_dir}' directory. Please add subfolders with person names containing their images.")
            return False
        
        for person_name in os.listdir(self.known_faces_dir):
            person_dir = os.path.join(self.known_faces_dir, person_name)
            
            if not os.path.isdir(person_dir):
                continue
            
            # Assign label to this person
            if person_name not in self.name_to_label:
                self.name_to_label[person_name] = current_label
                self.label_to_name[current_label] = person_name
                current_label += 1
            
            label = self.name_to_label[person_name]
            
            for image_name in os.listdir(person_dir):
                image_path = os.path.join(person_dir, image_name)
                
                # Check if it's an image file
                if not image_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    continue
                    
                try:
                    # Load image and convert to grayscale
                    image = cv2.imread(image_path)
                    if image is None:
                        continue
                        
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    
                    # Detect faces in image
                    detected_faces = self.face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                    )
                    
                    for (x, y, w, h) in detected_faces:
                        # Extract and resize face region
                        face_roi = gray[y:y+h, x:x+w]
                        face_roi = cv2.resize(face_roi, (200, 200))
                        # Apply preprocessing for lighting normalization
                        face_roi = self.preprocess_face(face_roi)
                        faces.append(face_roi)
                        labels.append(label)
                        print(f"Loaded face for {person_name} from {image_name}")
                        
                except Exception as e:
                    print(f"Error loading {image_path}: {e}")
        
        if len(faces) == 0:
            print("No faces found to train! Add images to known_faces/<PersonName>/ folders.")
            return False
        
        # Train the recognizer
        print(f"Training recognizer with {len(faces)} face(s) for {len(self.label_to_name)} person(s)...")
        self.recognizer.train(faces, np.array(labels))
        self.is_trained = True
        
        # Save the model and labels
        self.recognizer.write(self.model_path)
        with open(self.labels_path, 'wb') as f:
            pickle.dump((self.label_to_name, self.name_to_label), f)
        
        print("Training complete!")
        return True
    
    def load_model(self):
        """Load a previously trained model."""
        if os.path.exists(self.model_path) and os.path.exists(self.labels_path):
            try:
                self.recognizer.read(self.model_path)
                with open(self.labels_path, 'rb') as f:
                    self.label_to_name, self.name_to_label = pickle.load(f)
                self.is_trained = True
                print(f"Loaded model with {len(self.label_to_name)} person(s)")
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
        return False
    
    def recognize_faces(self, frame, confidence_threshold=70):
        """
        Recognize faces in a frame.
        
        Args:
            frame: BGR image from OpenCV (video frame)
            confidence_threshold: Lower value = stricter matching (0-100, lower is more confident)
        
        Returns:
            frame: Image with rectangles and names drawn on recognized faces
            recognized_names: List of names recognized in this frame
        """
        recognized_names = []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        detected_faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        
        for (x, y, w, h) in detected_faces:
            name = "Unknown"
            label_text = "Unknown"
            color = (0, 0, 255)  # Red for unknown
            
            if self.is_trained:
                # Extract and resize face for recognition
                face_roi = gray[y:y+h, x:x+w]
                face_roi = cv2.resize(face_roi, (200, 200))
                # Apply same preprocessing as training
                face_roi = self.preprocess_face(face_roi)
                
                # Predict
                label, confidence = self.recognizer.predict(face_roi)
                
                # Lower confidence = better match in LBPH
                # Increased threshold since preprocessing makes matching more consistent
                if confidence < confidence_threshold:
                    name = self.label_to_name.get(label, "Unknown")
                    recognized_names.append(name)
                    color = (0, 255, 0)  # Green for recognized
                    label_text = name  # Just show the name, no percentage
            
            # Draw rectangle around face
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            
            # Draw label with name (background matches box color, black text)
            cv2.rectangle(frame, (x, y+h), (x+w, y+h+35), color, cv2.FILLED)
            cv2.putText(frame, label_text, (x+6, y+h+25), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        return frame, recognized_names
    
    def capture_face(self, frame, person_name):
        """
        Capture and save a face from the current frame.
        
        Args:
            frame: Current video frame
            person_name: Name of the person to save
        
        Returns:
            success: Boolean indicating if face was captured successfully
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detected_faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        
        if len(detected_faces) == 0:
            print("No face detected in frame!")
            return False
        
        if len(detected_faces) > 1:
            print("Multiple faces detected! Please ensure only one face is in frame.")
            return False
        
        # Create directory for the person if it doesn't exist
        person_dir = os.path.join(self.known_faces_dir, person_name)
        os.makedirs(person_dir, exist_ok=True)
        
        # Save the image
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{person_name}_{timestamp}.jpg"
        filepath = os.path.join(person_dir, filename)
        
        cv2.imwrite(filepath, frame)
        print(f"Saved face image to {filepath}")
        
        return True
