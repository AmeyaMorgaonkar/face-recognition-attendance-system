# Copilot / AI Agent Instructions

Summary
- This repository implements a simple Face Recognition Attendance System using OpenCV (LBPH). The runtime entrypoint is `main.py`; core logic lives in `functions.py` as the `FaceRecognizer` class.

Big picture
- `main.py`: CLI/interactive entry. Captures frames from the default camera (`cv2.VideoCapture(0)`), handles keyboard controls (`q`, `c`, `r`) and delegates recognition to `FaceRecognizer`.
- `functions.py`: Contains helper functions and the `FaceRecognizer` implementation. Training, model persistence, capture, and prediction are implemented here.
- Data files: `known_faces/` (directory of subfolders per person), `face_model.yml` (LBPH model file written by `recognizer.write`), and `face_labels.pkl` (pickled label mappings).

How the code flows (quick)
- On startup, `main.py` constructs `FaceRecognizer(known_faces_dir="known_faces")` and calls `load_model()`; if not present, it calls `load_known_faces()` to train from disk.
- `load_known_faces()` expects `known_faces/<PersonName>/*.jpg|png` and will detect faces, resize to 200x200, train an LBPH recognizer and save `face_model.yml` and `face_labels.pkl`.
- During live capture `recognize_faces()` detects faces (Haar cascade), resizes each face to 200x200 and calls `recognizer.predict()`; LBPH returns a label + confidence (lower=better). The code treats confidence < 70 as a match by default.
- `capture_face()` saves the full frame to `known_faces/<PersonName>/` and prompts the user to retrain via `r` or automatically after capture.

Notable project-specific details & patterns
- Uses OpenCV's LBPH implementation via `cv2.face.LBPHFaceRecognizer_create()` (requires `opencv-contrib-python` in `requirements.txt`). If `cv2.face` is missing, the contributor needs the contrib package.
- Images are converted to grayscale and resized to 200x200 for both training and prediction — do not change size without updating both paths.
- Cascades: code uses `cv2.data.haarcascades + "haarcascade_frontalface_default.xml"`. The repo also contains `haarcascade_frontalface_default.xml` and `haarcascade_eye.xml` — these can be used/tested locally.
- Labels mapping is persisted in `face_labels.pkl`. Changing the label filenames will break load/save unless updated together.
- Controls in `main.py`: `q` to quit, `c` to capture a face (prompts for name), `r` to reload/retrain from `known_faces`.

How to run (developer)
- Create a Python 3 environment and install deps from `requirements.txt`.

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

- If your camera index is not `0` (macOS/USB camera differences), update `cv2.VideoCapture(0)` in `main.py`.

Common small tasks for agents
- Add an example person folder to `known_faces/` with 3–5 frontal face images to test training quickly.
- If adding or changing face image handling, update both `load_known_faces()` and `recognize_faces()` to keep preprocessing (grayscale + resize) consistent.
- When editing model persistence, update both `model_path` and `labels_path` usages in `FaceRecognizer`.

Files to inspect for changes
- Entrypoint: `main.py`
- Recognition/training: `functions.py` (class `FaceRecognizer`)
- Requirements: `requirements.txt` (must include `opencv-contrib-python` for LBPH)
- Sample data: `known_faces/` and the included cascade XML files in repo root

Testing & debugging tips
- Run `python3 main.py` and watch the console logs; `load_known_faces()` prints loaded images and training progress.
- If model loading fails, delete `face_model.yml` and `face_labels.pkl` and re-run training from `known_faces/` to repro the fresh-train path.
- If `cv2.face` attribute errors appear, ensure `opencv-contrib-python` is installed in the same interpreter used to run the script.

Tone and response style for Copilot
- Be concise and actionable. When making code edits, include one small focused change per PR and explain risk (e.g., changing image size affects training/prediction). Prefer to run the app locally to confirm camera access and training behavior.

If anything here is unclear or you want extra examples (unit test snippets, CI steps, or a sample `known_faces/` dataset), tell me which part to expand.
