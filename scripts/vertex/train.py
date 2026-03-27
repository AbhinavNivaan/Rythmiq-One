#!/usr/bin/env python3
"""
YOLOv8n-pose training script — runs inside a Vertex AI custom training container.

Downloads MIDV-500, converts annotations to YOLO keypoint format,
trains YOLOv8n-pose (4 corners: TL TR BR BL), exports to TFLite,
and uploads the model to GCS.

Usage (inside container):
    python train.py --output-gcs gs://rythmiq-one-dataset/models/doc_corners.tflite
    python train.py --output-gcs gs://... --epochs 50 --batch 32

Environment: Vertex AI n1-standard-8 + T4 GPU.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DATASET_DIR = Path("/tmp/doc_corners")
IMAGES_TRAIN = DATASET_DIR / "images" / "train"
IMAGES_VAL   = DATASET_DIR / "images" / "val"
LABELS_TRAIN = DATASET_DIR / "labels" / "train"
LABELS_VAL   = DATASET_DIR / "labels" / "val"
YAML_PATH    = DATASET_DIR / "doc_corners.yaml"

IMG_SIZE  = 640
VAL_SPLIT = 0.15


# ── MIDV-500 download ─────────────────────────────────────────────────────────

def download_midv500() -> Path:
    """Download MIDV-500 using the midv500 package. Returns raw root path."""
    try:
        from midv500 import download_midv500 as _dl
    except ImportError:
        raise SystemExit("midv500 not installed. Dockerfile must include: pip install midv500")

    raw_root = Path("/tmp/midv500_raw")
    raw_root.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading MIDV-500 to %s ...", raw_root)
    _dl(str(raw_root))
    logger.info("MIDV-500 download complete")
    return raw_root


# ── Annotation conversion ─────────────────────────────────────────────────────

def quad_to_yolo_keypoints(corners: list[list[float]], img_w: int, img_h: int) -> str:
    """
    Convert 4 corner points (pixel space, TL TR BR BL) to a YOLO keypoint line.

    Format: class cx cy bw bh kp0x kp0y kp0v kp1x kp1y kp1v kp2x kp2y kp2v kp3x kp3y kp3v
    All values normalised to [0,1]. Visibility = 2.
    """
    pts = np.array(corners, dtype=float)
    pts[:, 0] /= img_w
    pts[:, 1] /= img_h

    cx = float(np.mean(pts[:, 0]))
    cy = float(np.mean(pts[:, 1]))
    bw = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    bh = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))

    kp_str = " ".join(f"{pts[k, 0]:.6f} {pts[k, 1]:.6f} 2" for k in range(4))
    return f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {kp_str}"


def convert_midv500(raw_root: Path) -> list[tuple[Path, Path]]:
    """
    Walk MIDV-500 tree, produce (image_path, label_path) pairs.

    MIDV-500 structure:
        {root}/{category}/{doc_id}/images/*.jpg
        {root}/{category}/{doc_id}/ground_truth/*.json
            → {"quad": {"tl":[x,y], "tr":[x,y], "br":[x,y], "bl":[x,y]}}
    """
    tmp_labels = Path("/tmp/midv500_labels")
    tmp_labels.mkdir(parents=True, exist_ok=True)
    pairs: list[tuple[Path, Path]] = []

    json_files = sorted(raw_root.rglob("*.json"))
    logger.info("Found %d annotation files", len(json_files))

    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text())
            quad = data.get("quad", {})
            if not all(k in quad for k in ("tl", "tr", "br", "bl")):
                continue

            img_dir = json_path.parent.parent / "images"
            img_path = img_dir / (json_path.stem + ".jpg")
            if not img_path.exists():
                img_path = img_dir / (json_path.stem + ".png")
                if not img_path.exists():
                    continue

            img = cv2.imread(str(img_path))
            if img is None:
                continue
            h, w = img.shape[:2]

            corners = [quad["tl"], quad["tr"], quad["br"], quad["bl"]]
            label_line = quad_to_yolo_keypoints(corners, w, h)

            label_path = tmp_labels / (json_path.stem + ".txt")
            label_path.write_text(label_line + "\n")
            pairs.append((img_path, label_path))

        except Exception as exc:
            logger.debug("Skipped %s: %s", json_path.name, exc)

    logger.info("Converted %d annotations", len(pairs))
    return pairs


# ── Dataset assembly ──────────────────────────────────────────────────────────

def assemble_dataset(pairs: list[tuple[Path, Path]]) -> None:
    """Split into train/val and copy files to DATASET_DIR."""
    for d in [IMAGES_TRAIN, IMAGES_VAL, LABELS_TRAIN, LABELS_VAL]:
        d.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    indices = rng.permutation(len(pairs))
    val_count = max(1, int(len(pairs) * VAL_SPLIT))
    val_idx = set(indices[:val_count].tolist())

    for i, (img_src, lbl_src) in enumerate(tqdm(pairs, desc="Assembling dataset")):
        is_val = i in val_idx
        img_dst = (IMAGES_VAL if is_val else IMAGES_TRAIN) / img_src.name
        lbl_dst = (LABELS_VAL if is_val else LABELS_TRAIN) / lbl_src.name
        shutil.copy2(img_src, img_dst)
        shutil.copy2(lbl_src, lbl_dst)

    total = len(pairs)
    logger.info("Dataset: %d train / %d val", total - val_count, val_count)


def write_yaml() -> None:
    content = f"""path: {DATASET_DIR}
train: images/train
val: images/val

nc: 1
names: ['document']

kpt_shape: [4, 3]
"""
    YAML_PATH.write_text(content)
    logger.info("Wrote %s", YAML_PATH)


# ── Training + export ─────────────────────────────────────────────────────────

def train_and_export(epochs: int, batch: int) -> Path:
    """Train YOLOv8n-pose and export to TFLite. Returns local .tflite path."""
    device = "0" if _has_gpu() else "cpu"
    logger.info("Training on device: %s", device)

    model = YOLO("yolov8n-pose.pt")
    model.train(
        data=str(YAML_PATH),
        epochs=epochs,
        imgsz=IMG_SIZE,
        batch=batch,
        name="doc_corners",
        project="/tmp/runs/pose",
        exist_ok=True,
        device=device,
    )

    best_pt = Path("/tmp/runs/pose/doc_corners/weights/best.pt")
    export_model = YOLO(str(best_pt))
    export_model.export(format="tflite", imgsz=IMG_SIZE)

    tflite_path = best_pt.with_suffix(".tflite")
    logger.info("TFLite model at: %s (%.1f MB)", tflite_path, tflite_path.stat().st_size / 1e6)
    return tflite_path


def _has_gpu() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ── GCS upload ────────────────────────────────────────────────────────────────

def upload_to_gcs(local_path: Path, gcs_uri: str) -> None:
    """Upload file to GCS. gcs_uri format: gs://bucket/path/to/file."""
    from google.cloud import storage

    assert gcs_uri.startswith("gs://"), f"Expected gs:// URI, got: {gcs_uri}"
    without_scheme = gcs_uri[len("gs://"):]
    bucket_name, blob_path = without_scheme.split("/", 1)

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(str(local_path), content_type="application/octet-stream")
    logger.info("Uploaded %s → %s", local_path.name, gcs_uri)


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-gcs",
        default="gs://rythmiq-one-dataset/models/doc_corners.tflite",
        help="GCS URI to write the exported TFLite model",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch",  type=int, default=16)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    logger.info("=== Step 1: Download MIDV-500 ===")
    raw_root = download_midv500()

    logger.info("=== Step 2: Convert annotations ===")
    pairs = convert_midv500(raw_root)
    if not pairs:
        sys.exit("No annotations found. MIDV-500 download may have failed.")

    logger.info("=== Step 3: Assemble dataset ===")
    assemble_dataset(pairs)
    write_yaml()

    logger.info("=== Step 4: Train (epochs=%d, batch=%d) ===", args.epochs, args.batch)
    tflite_path = train_and_export(args.epochs, args.batch)

    logger.info("=== Step 5: Upload to GCS ===")
    upload_to_gcs(tflite_path, args.output_gcs)

    logger.info("Done. Model at: %s", args.output_gcs)
    logger.info("Next: gsutil cp %s app-v2/assets/models/doc_corners.tflite", args.output_gcs)
