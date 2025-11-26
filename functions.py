import time
import cv2

def draw(img, classifier, scaleFactor, minNeighbors, color, text):
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    parts = classifier.detectMultiScale(gray_img, scaleFactor, minNeighbors)
    coords = []
    for (x, y, w, h) in parts:
        cv2.rectangle(img, (x, y), (x+w, y+h), color, thickness=2)
        cv2.putText(img, text, (x, y-4), cv2.FACE_RECOGNIZER_SF_FR_COSINE, 0.8, color, 1, cv2.LINE_AA)
        coords = [x, y, w, h]

    return coords, img

def detect_face(img, faceCascade):
    coords, img = draw(img, faceCascade, 1.1, 2, (255, 0, 0), "Face")

    return img
