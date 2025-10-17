import time
import cv2

video = cv2.VideoCapture(0)
# time.sleep(1)

while True:
    check, frame = video.read()
    
    if check == False:
        continue

    cv2.imshow("Camera", frame)

    key = cv2.waitKey(1)

    if key == ord('q'):
        break

video.release()