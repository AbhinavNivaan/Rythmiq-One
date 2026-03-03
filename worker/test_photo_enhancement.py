"""
Quick smoke test for the photo enhancement fix.
Run from the worker/ directory:
    python test_photo_enhancement.py <path-to-photo>
Outputs two files next to the input for visual comparison:
    <name>_doc_mode.jpg   (old behaviour - document type)
    <name>_photo_mode.jpg (new behaviour - photo type)
"""
import sys
import os

# Make sure the worker source is importable
sys.path.insert(0, os.path.dirname(__file__))

from processors.enhancement import enhance_image, EnhancementOptions


def run(photo_path: str) -> None:
    with open(photo_path, "rb") as f:
        data = f.read()

    base, ext = os.path.splitext(photo_path)

    # Old behaviour (document type — triggers white balance + CLAHE)
    doc_result = enhance_image(data, EnhancementOptions(document_type="document"))
    doc_out = base + "_doc_mode.jpg"
    with open(doc_out, "wb") as f:
        f.write(doc_result.image_data)
    print(f"document mode → {doc_out}")

    # New behaviour (photo type — skips white balance + CLAHE)
    photo_result = enhance_image(data, EnhancementOptions(document_type="photo"))
    photo_out = base + "_photo_mode.jpg"
    with open(photo_out, "wb") as f:
        f.write(photo_result.image_data)
    print(f"photo mode    → {photo_out}")

    print("\noperations applied:")
    print(f"  document: orientation={doc_result.orientation_corrected}  "
          f"denoised={doc_result.denoised}  color_normalized={doc_result.color_normalized}")
    print(f"  photo:    orientation={photo_result.orientation_corrected}  "
          f"denoised={photo_result.denoised}  color_normalized={photo_result.color_normalized}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python test_photo_enhancement.py <path-to-photo>")
        sys.exit(1)
    run(sys.argv[1])
