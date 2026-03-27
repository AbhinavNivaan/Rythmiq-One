#!/usr/bin/env python3
"""
Initial YOLOv8n-pose training on MIDV-500 for document corner detection.

Produces: runs/pose/doc_corners/weights/best.tflite

Usage:
    python scripts/train_initial_model.py

After completion, copy the output model:
    cp runs/pose/doc_corners/weights/best.tflite app-v2/assets/models/doc_corners.tflite

Model spec:
    - 4 keypoints: TL, TR, BR, BL (in that order)
    - Input: 640x640 RGB
    - Output: [1, 17, 8400] float32 TFLite tensor
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO

# ── Config ───────────────────────────────────────────────────────────────────

DATASET_DIR = Path("datasets/doc_corners")
IMAGES_TRAIN = DATASET_DIR / "images" / "train"
IMAGES_VAL = DATASET_DIR / "images" / "val"
LABELS_TRAIN = DATASET_DIR / "labels" / "train"
LABELS_VAL = DATASET_DIR / "labels" / "val"
YAML_PATH = DATASET_DIR / "doc_corners.yaml"

EPOCHS = 100
IMG_SIZE = 640
BATCH = 16
VAL_SPLIT = 0.15  # 15% of images go to val


# ── MIDV-500 download ─────────────────────────────────────────────────────────

def download_midv500() -> Path:
    """Download MIDV-500 via the midv500 package and return root path."""
    try:
        from midv500 import download_midv500 as _dl
        root = Path("datasets/midv500_raw")
        root.mkdir(parents=True, exist_ok=True)
        _dl(str(root))
        return root
    except ImportError:
        raise SystemExit(
            "midv500 package not installed. Run: pip install midv500"
        )


# ── Annotation conversion ─────────────────────────────────────────────────────

def quad_to_yolo_keypoints(
    corners: list[list[float]],
    img_w: int,
    img_h: int,
) -> str:
    """
    Convert 4 corner points to YOLO keypoint annotation line.

    corners: [[x,y], [x,y], [x,y], [x,y]] in pixel space, order TL TR BR BL
    Returns: YOLO line string
      class cx cy bw bh kp0x kp0y kp0v kp1x kp1y kp1v kp2x kp2y kp2v kp3x kp3y kp3v
      All values normalised to [0,1]. Visibility = 2 (labeled and visible).
    """
    pts = np.array(corners, dtype=float)

    # Normalise to [0,1]
    pts[:, 0] /= img_w
    pts[:, 1] /= img_h

    # Bounding box from keypoints
    cx = float(np.mean(pts[:, 0]))
    cy = float(np.mean(pts[:, 1]))
    bw = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    bh = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))

    kp_str = " ".join(
        f"{pts[k, 0]:.6f} {pts[k, 1]:.6f} 2"
        for k in range(4)
    )
    return f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {kp_str}"


def convert_midv500(raw_root: Path) -> list[tuple[Path, Path]]:
    """
    Walk MIDV-500 directory structure, convert annotations to YOLO keypoint format.

    MIDV-500 structure:
      {raw_root}/{category}/{document_id}/images/*.jpg
      {raw_root}/{category}/{document_id}/ground_truth/*.json
        JSON contains: {"quad": {"tl": [x,y], "tr": [x,y], "br": [x,y], "bl": [x,y]}}

    Returns list of (image_path, label_path) pairs for dataset assembly.
    """
    pairs = []
    tmp_labels = Path("datasets/midv500_labels_tmp")
    tmp_labels.mkdir(parents=True, exist_ok=True)

    for json_path in sorted(raw_root.rglob("*.json")):
        try:
            data = json.loads(json_path.read_text())
            quad = data.get("quad", {})
            if not all(k in quad for k in ("tl", "tr", "br", "bl")):
                continue

            # Corresponding image — same stem, in sibling images/ directory
            img_dir = json_path.parent.parent / "images"
            img_path = img_dir / (json_path.stem + ".jpg")
            if not img_path.exists():
                # Try png
                img_path = img_dir / (json_path.stem + ".png")
                if not img_path.exists():
                    continue

            img = cv2.imread(str(img_path))
            if img is None:
                continue
            h, w = img.shape[:2]

            # MIDV-500 quad order: tl, tr, br, bl — matches our TL TR BR BL order
            corners = [
                quad["tl"],
                quad["tr"],
                quad["br"],
                quad["bl"],
            ]
            label_line = quad_to_yolo_keypoints(corners, w, h)

            label_path = tmp_labels / (json_path.stem + ".txt")
            label_path.write_text(label_line + "\n")
            pairs.append((img_path, label_path))

        except Exception as e:
            print(f"  Skipped {json_path.name}: {e}")

    print(f"Converted {len(pairs)} MIDV-500 annotations")
    return pairs


# ── Dataset assembly ──────────────────────────────────────────────────────────

def assemble_dataset(pairs: list[tuple[Path, Path]]) -> None:
    """Split pairs into train/val and copy to DATASET_DIR."""
    for d in [IMAGES_TRAIN, IMAGES_VAL, LABELS_TRAIN, LABELS_VAL]:
        d.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    indices = rng.permutation(len(pairs))
    val_count = max(1, int(len(pairs) * VAL_SPLIT))
    val_idx = set(indices[:val_count].tolist())

    for i, (img_src, lbl_src) in enumerate(tqdm(pairs, desc="Assembling dataset")):
        split = "val" if i in val_idx else "train"
        img_dst = (IMAGES_VAL if split == "val" else IMAGES_TRAIN) / img_src.name
        lbl_dst = (LABELS_VAL if split == "val" else LABELS_TRAIN) / lbl_src.name
        shutil.copy2(img_src, img_dst)
        shutil.copy2(lbl_src, lbl_dst)

    total = len(pairs)
    print(f"Dataset: {total - val_count} train / {val_count} val")


def write_yaml() -> None:
    """Write dataset YAML for Ultralytics training."""
    content = f"""path: {DATASET_DIR.resolve()}
train: images/train
val: images/val

nc: 1
names: ['document']

kpt_shape: [4, 3]  # 4 keypoints, 3 values each (x, y, visibility)
"""
    YAML_PATH.write_text(content)
    print(f"Wrote {YAML_PATH}")


# ── Training + export ─────────────────────────────────────────────────────────

def train_and_export() -> Path:
    """Train YOLOv8n-pose and export to TFLite. Returns path to .tflite file."""
    model = YOLO("yolov8n-pose.pt")

    model.train(
        data=str(YAML_PATH),
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        name="doc_corners",
        project="runs/pose",
        exist_ok=True,
        device=0 if _has_gpu() else "cpu",
    )

    # Export best weights to TFLite
    best_pt = Path("runs/pose/doc_corners/weights/best.pt")
    export_model = YOLO(str(best_pt))
    export_model.export(format="tflite", imgsz=IMG_SIZE)

    tflite_path = best_pt.with_suffix(".tflite")
    print(f"\nModel exported to: {tflite_path}")
    print(f"\nNext step:")
    print(f"  cp {tflite_path} app-v2/assets/models/doc_corners.tflite")
    return tflite_path


def _has_gpu() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Step 1: Download MIDV-500 ===")
    raw_root = download_midv500()

    print("\n=== Step 2: Convert annotations ===")
    pairs = convert_midv500(raw_root)

    if not pairs:
        raise SystemExit("No annotations found. Check MIDV-500 download.")

    print("\n=== Step 3: Assemble dataset ===")
    assemble_dataset(pairs)
    write_yaml()

    print("\n=== Step 4: Train + export ===")
    tflite_path = train_and_export()
