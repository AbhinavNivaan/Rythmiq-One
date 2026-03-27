# Training container for YOLOv8n-pose document corner detection.
# Base: ultralytics/ultralytics — includes PyTorch, CUDA, OpenCV, ultralytics.
# Adds: midv500 dataset downloader + google-cloud-storage for model upload.

FROM ultralytics/ultralytics:latest

RUN pip install --no-cache-dir \
    midv500 \
    google-cloud-storage>=2.0.0

COPY train.py /app/train.py
WORKDIR /app

ENTRYPOINT ["python", "train.py"]
