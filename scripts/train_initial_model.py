#!/usr/bin/env python3
"""
Initial YOLOv8n-pose training on MIDV-500 subset for document corner detection.

Downloads 10 representative document types (~12GB), trains on MPS/CPU, then
auto-deletes raw data. Net disk cost after cleanup: ~1GB (model + run artifacts).

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

import ftplib
import json
import os
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO

# ── Config ───────────────────────────────────────────────────────────────────

DATASET_DIR  = Path("datasets/doc_corners")
RAW_DIR      = Path("datasets/midv500_raw")
IMAGES_TRAIN = DATASET_DIR / "images" / "train"
IMAGES_VAL   = DATASET_DIR / "images" / "val"
LABELS_TRAIN = DATASET_DIR / "labels" / "train"
LABELS_VAL   = DATASET_DIR / "labels" / "val"
YAML_PATH    = DATASET_DIR / "doc_corners.yaml"

EPOCHS    = 100
IMG_SIZE  = 640
BATCH     = 8       # safe for MPS/CPU
VAL_SPLIT = 0.15

# 10 types: mix of IDs, passports, driver's licenses, different aspect ratios
SUBSET_URLS = [
    "ftp://smartengines.com/midv-500/dataset/04_aut_id.zip",         # ID card
    "ftp://smartengines.com/midv-500/dataset/06_bra_passport.zip",   # passport
    "ftp://smartengines.com/midv-500/dataset/12_deu_drvlic_new.zip", # driver's licence
    "ftp://smartengines.com/midv-500/dataset/14_deu_id_new.zip",     # ID card
    "ftp://smartengines.com/midv-500/dataset/20_esp_id_new.zip",     # ID card
    "ftp://smartengines.com/midv-500/dataset/05_aze_passport.zip",   # passport
    "ftp://smartengines.com/midv-500/dataset/09_chn_id.zip",         # ID card
    "ftp://smartengines.com/midv-500/dataset/16_deu_passport_new.zip", # passport
    "ftp://smartengines.com/midv-500/dataset/18_dza_passport.zip",   # passport
    "ftp://smartengines.com/midv-500/dataset/19_esp_drvlic.zip",     # driver's licence
]


# ── Download ──────────────────────────────────────────────────────────────────

def _ftp_download(ftp_url: str, dest_dir: Path) -> Path:
    """Download a single file via FTP with retry. Skip if already present."""
    parsed   = urlparse(ftp_url)
    host     = parsed.netloc
    remote   = parsed.path
    filename = Path(remote).name
    local    = dest_dir / filename

    if local.exists():
        return local

    print(f"  Downloading {filename} ...")
    for attempt in range(3):
        try:
            with ftplib.FTP(host, timeout=300) as ftp:
                ftp.login()
                try:
                    total = ftp.size(remote)
                except ftplib.error_perm:
                    total = None
                with open(local, "wb") as f, tqdm(
                    total=total, unit="B", unit_scale=True, desc=filename, leave=False
                ) as bar:
                    def _cb(chunk: bytes) -> None:
                        f.write(chunk)
                        bar.update(len(chunk))
                    ftp.retrbinary(f"RETR {remote}", _cb, blocksize=1 << 20)
            return local
        except (TimeoutError, ftplib.Error) as e:
            local.unlink(missing_ok=True)
            if attempt == 2:
                raise
            print(f"  Retry {attempt + 1}/3 after error: {e}")
    return local


def download_subset() -> Path:
    """Download the 10 selected MIDV-500 zip files. Returns raw root dir."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(SUBSET_URLS, 1):
        filename = Path(urlparse(url).path).name
        dest = RAW_DIR / Path(filename).stem
        print(f"[{i}/{len(SUBSET_URLS)}]", end=" ")
        if dest.exists():
            print(f"  Already extracted: {dest.name}")
            continue
        zip_path = _ftp_download(url, RAW_DIR)
        print(f"  Extracting {zip_path.name} ...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(RAW_DIR)
        zip_path.unlink(missing_ok=True)
    return RAW_DIR


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
    Walk MIDV-500 directory structure, convert annotations to YOLO keypoint format.

    Actual MIDV-500 structure:
      {raw_root}/{doc_type}/images/{scene}/{stem}.tif
      {raw_root}/{doc_type}/ground_truth/{scene}/{stem}.json
        JSON: {"quad": [[x,y],[x,y],[x,y],[x,y]]}  (TL TR BR BL order)

    Returns list of (image_path, label_path) pairs.
    """
    pairs = []
    tmp_labels = Path("datasets/midv500_labels_tmp")
    tmp_labels.mkdir(parents=True, exist_ok=True)

    for json_path in sorted(raw_root.rglob("ground_truth/**/*.json")):
        try:
            data = json.loads(json_path.read_text())
            quad = data.get("quad")
            if not quad or len(quad) != 4:
                continue

            # ground_truth/{scene}/{stem}.json → images/{scene}/{stem}.tif
            scene    = json_path.parent.name
            doc_dir  = json_path.parent.parent.parent  # {doc_type}/
            img_path = doc_dir / "images" / scene / (json_path.stem + ".tif")
            if not img_path.exists():
                continue

            img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
            if img is None:
                continue
            h, w = img.shape[:2]

            # quad is [[x,y],[x,y],[x,y],[x,y]] in TL TR BR BL order
            corners = [list(pt) for pt in quad]
            label_line = quad_to_yolo_keypoints(corners, w, h)

            label_path = tmp_labels / (json_path.stem + ".txt")
            label_path.write_text(label_line + "\n")
            pairs.append((img_path, label_path))

        except Exception as e:
            print(f"  Skipped {json_path.name}: {e}")

    print(f"Converted {len(pairs)} annotations")
    return pairs


# ── Dataset assembly (symlinks — no copying) ──────────────────────────────────

def assemble_dataset(pairs: list[tuple[Path, Path]]) -> None:
    """Split pairs into train/val and symlink into DATASET_DIR (no copy)."""
    for d in [IMAGES_TRAIN, IMAGES_VAL, LABELS_TRAIN, LABELS_VAL]:
        d.mkdir(parents=True, exist_ok=True)

    rng       = np.random.default_rng(42)
    indices   = rng.permutation(len(pairs))
    val_count = max(1, int(len(pairs) * VAL_SPLIT))
    val_idx   = set(indices[:val_count].tolist())

    for i, (img_src, lbl_src) in enumerate(tqdm(pairs, desc="Assembling dataset")):
        split   = "val" if i in val_idx else "train"
        # Convert .tif → .jpg (YOLO requires JPEG/PNG)
        img_dst = (IMAGES_VAL if split == "val" else IMAGES_TRAIN) / (img_src.stem + ".jpg")
        lbl_dst = (LABELS_VAL if split == "val" else LABELS_TRAIN) / lbl_src.name
        if not img_dst.exists():
            img = cv2.imread(str(img_src), cv2.IMREAD_UNCHANGED)
            cv2.imwrite(str(img_dst), img)
        if not lbl_dst.exists():
            lbl_dst.symlink_to(lbl_src.resolve())

    total = len(pairs)
    print(f"Dataset: {total - val_count} train / {val_count} val")


def write_yaml() -> None:
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

def _get_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


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
        device=_get_device(),
    )

    best_pt      = Path("runs/pose/doc_corners/weights/best.pt")
    export_model = YOLO(str(best_pt))
    export_model.export(format="tflite", imgsz=IMG_SIZE)

    tflite_path = best_pt.with_suffix(".tflite")
    print(f"\nModel exported to: {tflite_path}")
    return tflite_path


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup() -> None:
    """Delete raw MIDV-500 data and temp labels to reclaim disk space."""
    print("\n=== Cleanup: removing raw dataset ===")
    for path in [RAW_DIR, Path("datasets/midv500_labels_tmp")]:
        if path.exists():
            shutil.rmtree(path)
            print(f"  Deleted {path}")
    # Remove symlink dirs (symlinks are gone since targets deleted)
    shutil.rmtree(DATASET_DIR, ignore_errors=True)
    print("  Deleted datasets/doc_corners (symlinks)")
    print("Cleanup complete. Disk reclaimed.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Step 1: Download MIDV-500 subset (10 types) ===")
    raw_root = download_subset()

    print("\n=== Step 2: Convert annotations ===")
    pairs = convert_midv500(raw_root)

    if not pairs:
        raise SystemExit("No annotations found. Check download.")

    print("\n=== Step 3: Assemble dataset (symlinks) ===")
    assemble_dataset(pairs)
    write_yaml()

    print(f"\n=== Step 4: Train + export (device: {_get_device()}) ===")
    tflite_path = train_and_export()

    print("\n=== Step 5: Cleanup ===")
    cleanup()

    print(f"\nDone. Copy model to app:")
    print(f"  cp {tflite_path} app-v2/assets/models/doc_corners.tflite")
