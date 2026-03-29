#!/usr/bin/env python3
"""
Submit a Vertex AI custom training job for doc corner detection.

Prerequisites:
    pip install google-cloud-aiplatform

Usage:
    python scripts/vertex/submit_job.py
    python scripts/vertex/submit_job.py --epochs 50 --batch 32

The job runs async — monitor progress at:
    https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=rythmiq-one

When complete, download the model:
    gsutil cp gs://rythmiq-one-dataset/models/doc_corners.tflite \\
              app-v2/assets/models/doc_corners.tflite
"""

from __future__ import annotations

import argparse

PROJECT  = "rythmiq-one"
REGION   = "asia-south1"   # matches rythmiq-one-dataset GCS bucket location
IMAGE    = "asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/doc-corners-trainer:latest"
GCS_OUT  = "gs://rythmiq-one-dataset/models/doc_corners.tflite"


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit Vertex AI training job")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch",  type=int, default=16)
    args = parser.parse_args()

    try:
        from google.cloud import aiplatform
    except ImportError:
        raise SystemExit("google-cloud-aiplatform not installed. Run: pip install google-cloud-aiplatform")

    print(f"Initialising Vertex AI — project={PROJECT}, region={REGION}")
    aiplatform.init(project=PROJECT, location=REGION, staging_bucket="gs://rythmiq-one-dataset")

    job = aiplatform.CustomContainerTrainingJob(
        display_name="doc-corners-yolov8n-pose",
        container_uri=IMAGE,
    )

    print(f"Submitting job (epochs={args.epochs}, batch={args.batch}) ...")
    job.run(
        args=[
            "--output-gcs", GCS_OUT,
            "--epochs",     str(args.epochs),
            "--batch",      str(args.batch),
        ],
        machine_type="n1-standard-8",
        replica_count=1,
        timeout=21600,  # 6 hours — training + MIDV-500 download
        sync=False,
    )

    print()
    print("Job submitted successfully.")
    print()
    print("Monitor:")
    print(f"  https://console.cloud.google.com/vertex-ai/training/custom-jobs?project={PROJECT}")
    print()
    print("When the job shows SUCCEEDED, download the model:")
    print(f"  gsutil cp {GCS_OUT} app-v2/assets/models/doc_corners.tflite")
    print()
    print("Then verify output shape:")
    print("  python3 -c \"")
    print("  import tensorflow as tf")
    print("  i = tf.lite.Interpreter('app-v2/assets/models/doc_corners.tflite')")
    print("  i.allocate_tensors()")
    print("  print('Input:', i.get_input_details()[0]['shape'])   # [1, 640, 640, 3]")
    print("  print('Output:', i.get_output_details()[0]['shape']) # [1, 17, 8400]")
    print("  \"")


if __name__ == "__main__":
    main()
