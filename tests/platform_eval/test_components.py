#!/usr/bin/env python3
"""
Camber Platform Evaluation - Component Tests

Tests initialization time for each component in the Rythmiq processing stack:
- Pillow (DPI, compression)
- OpenCV (auto-crop, enhancement)  
- PyMuPDF (PDF processing)
- img2pdf (format conversion)
- rembg (background removal) - ML model
- PaddleOCR (OCR) - ML model
- Google Vision API (cloud OCR)

Usage:
    python test_components.py --component pillow
    python test_components.py --component all
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.platform_eval.harness import (
    CamberTestHarness,
    TestResult,
    JobResult,
    create_timing_wrapper,
    parse_timing_from_logs
)


# Component test commands
COMPONENT_TESTS = {
    "pillow": '''
import time
print("=== PILLOW TEST ===")

t0 = time.time()
from PIL import Image, ImageDraw, ImageFilter
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# First operation - create and process image
img = Image.new("RGB", (4000, 3000), "white")
draw = ImageDraw.Draw(img)
draw.rectangle([100, 100, 3900, 2900], outline="black", width=5)
t_create = time.time()
print(f"CREATE_TIME={t_create-t_import:.3f}")

# Resize
img_resized = img.resize((1920, 1080), Image.LANCZOS)
t_resize = time.time()
print(f"RESIZE_TIME={t_resize-t_create:.3f}")

# Apply filter
img_filtered = img_resized.filter(ImageFilter.SHARPEN)
t_filter = time.time()
print(f"FILTER_TIME={t_filter-t_resize:.3f}")

# Save to bytes
import io
buf = io.BytesIO()
img_filtered.save(buf, format="JPEG", quality=85, optimize=True)
output_size = len(buf.getvalue())
t_save = time.time()
print(f"SAVE_TIME={t_save-t_filter:.3f}")

print(f"TOTAL_TIME={t_save-t0:.3f}")
print(f"OUTPUT_SIZE={output_size}")
print("PILLOW_SUCCESS")
''',

    "opencv": '''
import time
print("=== OPENCV TEST ===")

t0 = time.time()
import cv2
import numpy as np
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# Create test image
img = np.zeros((3000, 4000, 3), dtype=np.uint8)
img[:] = (255, 255, 255)  # White background
cv2.rectangle(img, (100, 100), (3900, 2900), (0, 0, 0), 5)
t_create = time.time()
print(f"CREATE_TIME={t_create-t_import:.3f}")

# Grayscale conversion
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
t_gray = time.time()
print(f"GRAYSCALE_TIME={t_gray-t_create:.3f}")

# Gaussian blur (denoise)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
t_blur = time.time()
print(f"BLUR_TIME={t_blur-t_gray:.3f}")

# Edge detection (for auto-crop detection)
edges = cv2.Canny(blurred, 50, 150)
t_edge = time.time()
print(f"EDGE_TIME={t_edge-t_blur:.3f}")

# Find contours
contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
t_contour = time.time()
print(f"CONTOUR_TIME={t_contour-t_edge:.3f}")

# Resize
resized = cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_LANCZOS4)
t_resize = time.time()
print(f"RESIZE_TIME={t_resize-t_contour:.3f}")

# Encode to JPEG
_, encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
output_size = len(encoded)
t_encode = time.time()
print(f"ENCODE_TIME={t_encode-t_resize:.3f}")

print(f"TOTAL_TIME={t_encode-t0:.3f}")
print(f"OUTPUT_SIZE={output_size}")
print("OPENCV_SUCCESS")
''',

    "pymupdf": '''
import time
print("=== PYMUPDF TEST ===")

t0 = time.time()
import fitz  # PyMuPDF
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# Create a simple PDF
doc = fitz.open()
t_open = time.time()
print(f"OPEN_TIME={t_open-t_import:.3f}")

# Add pages
for i in range(5):
    page = doc.new_page(width=612, height=792)  # Letter size
    page.insert_text((72, 72), f"Page {i+1}", fontsize=24)
t_pages = time.time()
print(f"ADD_PAGES_TIME={t_pages-t_open:.3f}")

# Save to bytes
pdf_bytes = doc.tobytes()
t_save = time.time()
print(f"SAVE_TIME={t_save-t_pages:.3f}")

# Reopen and extract
doc2 = fitz.open(stream=pdf_bytes, filetype="pdf")
t_reopen = time.time()
print(f"REOPEN_TIME={t_reopen-t_save:.3f}")

# Extract page as image
page = doc2[0]
pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
img_bytes = pix.tobytes("png")
t_extract = time.time()
print(f"EXTRACT_IMAGE_TIME={t_extract-t_reopen:.3f}")

doc.close()
doc2.close()

print(f"TOTAL_TIME={t_extract-t0:.3f}")
print(f"PDF_SIZE={len(pdf_bytes)}")
print(f"IMAGE_SIZE={len(img_bytes)}")
print("PYMUPDF_SUCCESS")
''',

    "img2pdf": '''
import time
print("=== IMG2PDF TEST ===")

t0 = time.time()
import img2pdf
from PIL import Image
import io
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# Create test image
img = Image.new("RGB", (1920, 1080), "white")
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=85)
img_bytes = buf.getvalue()
t_create = time.time()
print(f"CREATE_IMAGE_TIME={t_create-t_import:.3f}")

# Convert to PDF
pdf_bytes = img2pdf.convert(img_bytes)
t_convert = time.time()
print(f"CONVERT_TIME={t_convert-t_create:.3f}")

print(f"TOTAL_TIME={t_convert-t0:.3f}")
print(f"INPUT_SIZE={len(img_bytes)}")
print(f"OUTPUT_SIZE={len(pdf_bytes)}")
print("IMG2PDF_SUCCESS")
''',

    "rembg": '''
import time
print("=== REMBG TEST ===")
print("WARNING: This test downloads ~170MB U2Net model on first run")

t0 = time.time()
from rembg import remove
from PIL import Image
import io
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# Create test image with "foreground"
img = Image.new("RGB", (800, 600), (200, 200, 200))  # Gray background
from PIL import ImageDraw
draw = ImageDraw.Draw(img)
draw.ellipse([200, 100, 600, 500], fill=(255, 0, 0))  # Red circle as foreground
t_create = time.time()
print(f"CREATE_IMAGE_TIME={t_create-t_import:.3f}")

# Convert to bytes
buf = io.BytesIO()
img.save(buf, format="PNG")
img_bytes = buf.getvalue()

# Remove background (this triggers model load on first call)
t_before_remove = time.time()
result = remove(img_bytes)
t_remove = time.time()
print(f"FIRST_REMOVE_TIME={t_remove-t_before_remove:.3f}")

# Second call (model should be loaded)
result2 = remove(img_bytes)
t_second = time.time()
print(f"SECOND_REMOVE_TIME={t_second-t_remove:.3f}")

print(f"TOTAL_TIME={t_second-t0:.3f}")
print(f"OUTPUT_SIZE={len(result)}")
print("REMBG_SUCCESS")
''',

    "paddleocr": '''
import time
print("=== PADDLEOCR TEST ===")

t0 = time.time()
from paddleocr import PaddleOCR
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# Initialize (this loads the model)
ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
t_init = time.time()
print(f"INIT_TIME={t_init-t_import:.3f}")

# Create test image with text
from PIL import Image, ImageDraw
import numpy as np

img = Image.new("RGB", (800, 200), "white")
draw = ImageDraw.Draw(img)
draw.text((50, 80), "Hello World 12345 Test OCR", fill="black")
img_array = np.array(img)
t_create = time.time()
print(f"CREATE_IMAGE_TIME={t_create-t_init:.3f}")

# First OCR call
result = ocr.ocr(img_array, cls=True)
t_first_ocr = time.time()
print(f"FIRST_OCR_TIME={t_first_ocr-t_create:.3f}")

# Extract text
text = ""
if result and result[0]:
    for line in result[0]:
        text += line[1][0] + " "
print(f"EXTRACTED_TEXT={text.strip()}")

# Second OCR call
result2 = ocr.ocr(img_array, cls=True)
t_second_ocr = time.time()
print(f"SECOND_OCR_TIME={t_second_ocr-t_first_ocr:.3f}")

print(f"TOTAL_TIME={t_second_ocr-t0:.3f}")
print("PADDLEOCR_SUCCESS")
''',

    "google_vision": '''
import time
import os
print("=== GOOGLE VISION TEST ===")

# Check for credentials
creds = os.environ.get("GOOGLE_VISION_CREDENTIALS_JSON")
if not creds:
    print("ERROR: GOOGLE_VISION_CREDENTIALS_JSON not set")
    print("GOOGLE_VISION_SKIP")
    exit(0)

t0 = time.time()
from google.cloud import vision
from google.oauth2 import service_account
import json
t_import = time.time()
print(f"IMPORT_TIME={t_import-t0:.3f}")

# Initialize client
creds_dict = json.loads(creds)
credentials = service_account.Credentials.from_service_account_info(creds_dict)
client = vision.ImageAnnotatorClient(credentials=credentials)
t_init = time.time()
print(f"INIT_TIME={t_init-t_import:.3f}")

# Create test image
from PIL import Image, ImageDraw
import io

img = Image.new("RGB", (800, 200), "white")
draw = ImageDraw.Draw(img)
draw.text((50, 80), "Hello World 12345 Test OCR", fill="black")
buf = io.BytesIO()
img.save(buf, format="PNG")
img_bytes = buf.getvalue()
t_create = time.time()
print(f"CREATE_IMAGE_TIME={t_create-t_init:.3f}")

# First API call
image = vision.Image(content=img_bytes)
response = client.text_detection(image=image)
t_first_api = time.time()
print(f"FIRST_API_TIME={t_first_api-t_create:.3f}")

# Extract text
texts = response.text_annotations
text = texts[0].description if texts else ""
print(f"EXTRACTED_TEXT={text.strip()}")

# Second API call
response2 = client.text_detection(image=image)
t_second_api = time.time()
print(f"SECOND_API_TIME={t_second_api-t_first_api:.3f}")

print(f"TOTAL_TIME={t_second_api-t0:.3f}")
print("GOOGLE_VISION_SUCCESS")
'''
}


class ComponentEvaluator:
    """Runs component-specific evaluation tests."""
    
    def __init__(self, api_key: str, stash_base: str):
        self.harness = CamberTestHarness(api_key, stash_base)
        self.stash_base = stash_base
        
    def test_component(self, component: str, pip_deps: str = "") -> JobResult:
        """Test a single component's initialization time."""
        print(f"\n{'='*60}")
        print(f"Testing: {component.upper()}")
        print('='*60)
        
        if component not in COMPONENT_TESTS:
            raise ValueError(f"Unknown component: {component}")
        
        test_code = COMPONENT_TESTS[component]
        
        # Build the command
        inner_cmd = f'''
export PYTHONPATH=/home/camber/workdir/cached_deps:$PYTHONPATH
{f"pip install {pip_deps} --quiet" if pip_deps else ""}
python3 -c '{test_code}'
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        print("Submitting job...")
        submit_time = time.time()
        job_id = self.harness.create_job(cmd)
        print(f"Job ID: {job_id}")
        
        print("Waiting for completion...")
        status = self.harness.wait_for_job(job_id, timeout=600)  # 10 min timeout for ML models
        end_time = time.time()
        
        logs = self.harness.get_job_logs(job_id)
        timing = parse_timing_from_logs(logs)
        
        # Parse component-specific metrics from logs
        metrics = self._parse_component_metrics(logs)
        
        job_result = JobResult(
            job_id=job_id,
            test_name=f"component_{component}",
            status=status["status"],
            submit_time=submit_time,
            start_time=timing.get("start_time"),
            end_time=timing.get("end_time"),
            duration_seconds=status.get("duration"),
            queue_time_seconds=None,
            logs=logs,
            metadata={
                "component": component,
                "metrics": metrics,
                "wall_clock": end_time - submit_time
            }
        )
        
        # Print summary
        print(f"\nResults for {component}:")
        print(f"  Status: {status['status']}")
        print(f"  Job Duration: {status.get('duration')}s")
        print(f"  Wall Clock: {end_time - submit_time:.1f}s")
        if metrics:
            for key, value in metrics.items():
                print(f"  {key}: {value}")
        
        return job_result
    
    def _parse_component_metrics(self, logs: str) -> Dict:
        """Parse timing metrics from component test logs."""
        metrics = {}
        for line in logs.split("\n"):
            if "=" in line and "_TIME=" in line or "_SIZE=" in line:
                try:
                    key, value = line.split("=", 1)
                    # Try to parse as float
                    try:
                        metrics[key] = float(value)
                    except ValueError:
                        metrics[key] = value
                except:
                    pass
            elif "EXTRACTED_TEXT=" in line:
                metrics["EXTRACTED_TEXT"] = line.split("=", 1)[1]
        return metrics
    
    def test_all_components(self) -> TestResult:
        """Test all components and generate summary."""
        print("\n" + "="*60)
        print("COMPONENT INITIALIZATION BASELINE TEST")
        print("="*60)
        
        started_at = datetime.now().isoformat()
        jobs = []
        
        # Define component dependencies
        component_deps = {
            "pillow": "Pillow",
            "opencv": "opencv-python-headless numpy",
            "pymupdf": "PyMuPDF",
            "img2pdf": "img2pdf Pillow",
            "rembg": "rembg Pillow",
            "paddleocr": "paddlepaddle paddleocr Pillow numpy",
            "google_vision": "google-cloud-vision Pillow",
        }
        
        for component, deps in component_deps.items():
            try:
                job_result = self.test_component(component, deps)
                jobs.append(job_result)
            except Exception as e:
                print(f"Error testing {component}: {e}")
        
        # Build summary
        summary = {
            "total_components": len(component_deps),
            "tested": len(jobs),
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "components": {}
        }
        
        for job in jobs:
            comp = job.metadata.get("component")
            metrics = job.metadata.get("metrics", {})
            summary["components"][comp] = {
                "status": job.status,
                "duration": job.duration_seconds,
                "import_time": metrics.get("IMPORT_TIME"),
                "init_time": metrics.get("INIT_TIME"),
                "total_time": metrics.get("TOTAL_TIME")
            }
        
        result = TestResult(
            test_name="component_baseline",
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        
        # Print final summary
        print("\n" + "="*60)
        print("COMPONENT BASELINE SUMMARY")
        print("="*60)
        print(f"{'Component':<15} {'Status':<12} {'Import':<10} {'Init':<10} {'Total':<10}")
        print("-"*60)
        for comp, data in summary["components"].items():
            import_t = f"{data['import_time']:.2f}s" if data['import_time'] else "N/A"
            init_t = f"{data['init_time']:.2f}s" if data['init_time'] else "N/A"
            total_t = f"{data['total_time']:.2f}s" if data['total_time'] else "N/A"
            print(f"{comp:<15} {data['status']:<12} {import_t:<10} {init_t:<10} {total_t:<10}")
        
        return result


def main():
    parser = argparse.ArgumentParser(description="Component Init Time Tests")
    parser.add_argument("--component", choices=list(COMPONENT_TESTS.keys()) + ["all"],
                       default="all", help="Component to test")
    parser.add_argument("--api-key", default=os.environ.get("CAMBER_API_KEY"))
    parser.add_argument("--stash-path", default="stash://abhinavprakash15151692/eval-test/worker")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: CAMBER_API_KEY not set")
        sys.exit(1)
    
    evaluator = ComponentEvaluator(args.api_key, args.stash_path)
    
    if args.component == "all":
        evaluator.test_all_components()
    else:
        evaluator.test_component(args.component)


if __name__ == "__main__":
    main()
