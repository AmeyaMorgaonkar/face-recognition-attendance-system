import time
import cv2
import functions

faceCascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")

video = cv2.VideoCapture(0)
# time.sleep(1)

while True:
    check, frame = video.read()

    frame = functions.detect_face(frame, faceCascade)
    
    if check == False:
        continue

    cv2.imshow("Camera", frame)

    key = cv2.waitKey(1)

    if key == ord('q'):
        break

video.release()
cv2.destroyAllWindows()