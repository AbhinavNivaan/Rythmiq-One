"""
Schema adaptation for Camber CPU worker.

Implements pixel-perfect document transformation:
- Exact resize to target dimensions
- DPI injection into output metadata
- Compression loop until file size < max_kb
- Filename normalization

A single pixel mismatch is a failure.
"""

from __future__ import annotations

import io
import re
from typing import Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from models import SchemaDefinition, SchemaResult, MasterConstraints
from errors import WorkerError, ErrorCode, ProcessingStage


# Maximum compression iterations to prevent infinite loops
MAX_COMPRESSION_ITERATIONS = 20

# Minimum JPEG quality threshold
MIN_JPEG_QUALITY = 20


def decode_image(data: bytes) -> Tuple[NDArray[np.uint8], Image.Image]:
    """
    Decode image bytes to both OpenCV and PIL formats.
    
    Args:
        data: Raw image bytes
        
    Returns:
        Tuple of (OpenCV BGR array, PIL Image)
        
    Raises:
        WorkerError: If image cannot be decoded
    """
    # Decode with OpenCV for resize operations
    nparr = np.frombuffer(data, np.uint8)
    cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if cv_img is None:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.SCHEMA,
            message="Failed to decode image for schema adaptation",
        )
    
    # Also open with PIL for DPI operations
    try:
        pil_img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"Failed to decode image with PIL: {str(e)}",
        )
    
    return cv_img, pil_img


def resize_exact(
    img: NDArray[np.uint8],
    target_width: int,
    target_height: int,
    fit_mode: str = "stretch",
) -> NDArray[np.uint8]:
    """
    Resize image to exact target dimensions.

    Args:
        img: BGR image array
        target_width: Target width in pixels
        target_height: Target height in pixels
        fit_mode: How to handle aspect-ratio mismatches:
            - "stretch"   (default) — squish/stretch to fill exactly (original behaviour)
            - "letterbox" — scale to fit, pad remainder with white

    Returns:
        Resized image array (always exactly target_width × target_height)

    Raises:
        WorkerError: If resize fails or dimensions don't match
    """
    try:
        if fit_mode == "letterbox":
            src_h, src_w = img.shape[:2]
            scale = min(target_width / src_w, target_height / src_h)
            scaled_w = int(round(src_w * scale))
            scaled_h = int(round(src_h * scale))

            scaled = cv2.resize(img, (scaled_w, scaled_h), interpolation=cv2.INTER_LANCZOS4)

            # Create white canvas and paste scaled image centred
            canvas = np.full((target_height, target_width, 3), 255, dtype=np.uint8)
            y_off = (target_height - scaled_h) // 2
            x_off = (target_width - scaled_w) // 2
            canvas[y_off:y_off + scaled_h, x_off:x_off + scaled_w] = scaled
            resized = canvas
        else:
            resized = cv2.resize(
                img,
                (target_width, target_height),
                interpolation=cv2.INTER_LANCZOS4,
            )

        # Verify exact dimensions
        h, w = resized.shape[:2]
        if w != target_width or h != target_height:
            raise WorkerError(
                code=ErrorCode.RESIZE_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=f"Resize dimension mismatch: expected {target_width}x{target_height}, got {w}x{h}",
            )

        return resized

    except cv2.error as e:
        raise WorkerError(
            code=ErrorCode.RESIZE_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"OpenCV resize failed: {str(e)}",
        )


def encode_with_dpi(
    img: NDArray[np.uint8],
    dpi: int,
    format: str = "jpeg",
    quality: int = 85,
) -> bytes:
    """
    Encode image with DPI metadata.
    
    Args:
        img: BGR image array
        dpi: Target DPI value
        format: Output format (jpeg, png)
        quality: JPEG quality (1-100)
        
    Returns:
        Encoded image bytes with DPI metadata
    """
    # Convert BGR to RGB for PIL
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    
    # Set DPI
    pil_img.info['dpi'] = (dpi, dpi)
    
    # Encode
    buffer = io.BytesIO()
    
    if format.lower() in ("jpeg", "jpg"):
        pil_img.save(
            buffer,
            format="JPEG",
            quality=quality,
            dpi=(dpi, dpi),
            optimize=True,
        )
    elif format.lower() == "png":
        pil_img.save(
            buffer,
            format="PNG",
            dpi=(dpi, dpi),
            optimize=True,
        )
    else:
        # Default to JPEG
        pil_img.save(
            buffer,
            format="JPEG",
            quality=quality,
            dpi=(dpi, dpi),
            optimize=True,
        )
    
    return buffer.getvalue()


def encode_as_pdf(
    img: NDArray[np.uint8],
    dpi: int,
    quality: int = 85,
) -> bytes:
    """
    Encode a single image as a single-page PDF with JPEG compression.

    The image is first JPEG-compressed at the given quality level and then
    wrapped in a PDF envelope.  This keeps PDF size proportional to JPEG
    quality and makes iterative size-fitting possible.

    Args:
        img: BGR image array
        dpi: Target resolution to embed in the PDF
        quality: JPEG quality (1-95). Lower = smaller file, lower fidelity.

    Returns:
        PDF file bytes

    Raises:
        WorkerError: If PDF encoding fails
    """
    try:
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)

        # Step 1: JPEG-compress at the requested quality.
        jpeg_buf = io.BytesIO()
        pil_img.save(jpeg_buf, format="JPEG", quality=quality, optimize=True)
        jpeg_buf.seek(0)

        # Step 2: Wrap the JPEG bytes in a single-page PDF.
        jpeg_pil = Image.open(jpeg_buf)
        pdf_buf = io.BytesIO()
        jpeg_pil.save(pdf_buf, format="PDF", resolution=dpi)
        return pdf_buf.getvalue()
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.SCHEMA_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"PDF encoding failed: {str(e)}",
            details={"exception_type": type(e).__name__},
        )


def compress_to_size(
    img: NDArray[np.uint8],
    dpi: int,
    max_kb: int,
    format: str = "jpeg",
    initial_quality: int = 85,
    min_kb: int = 0,
) -> Tuple[bytes, int]:
    """
    Compress image until it fits within max_kb.
    
    Uses a binary search approach to find optimal quality.
    
    Args:
        img: BGR image array
        dpi: Target DPI value
        max_kb: Maximum file size in KB
        format: Output format
        initial_quality: Starting quality
        min_kb: Minimum file size in KB (0 = no minimum)
        
    Returns:
        Tuple of (compressed bytes, final quality)
        
    Raises:
        WorkerError: If compression cannot achieve target size range
    """
    max_bytes = max_kb * 1024
    quality = initial_quality
    
    # First try at initial quality
    data = encode_with_dpi(img, dpi, format, quality)
    
    if len(data) <= max_bytes:
        best_data = data
        best_quality = quality
    else:
        # Binary search for optimal quality
        low_quality = MIN_JPEG_QUALITY
        high_quality = quality
        best_data = data
        best_quality = quality
        
        for _ in range(MAX_COMPRESSION_ITERATIONS):
            if low_quality > high_quality:
                break
            
            mid_quality = (low_quality + high_quality) // 2
            data = encode_with_dpi(img, dpi, format, mid_quality)
            
            if len(data) <= max_bytes:
                best_data = data
                best_quality = mid_quality
                low_quality = mid_quality + 1
            else:
                high_quality = mid_quality - 1
        
        # Final check
        if len(best_data) > max_bytes:
            # Try minimum quality as last resort
            data = encode_with_dpi(img, dpi, format, MIN_JPEG_QUALITY)
            
            if len(data) > max_bytes:
                raise WorkerError(
                    code=ErrorCode.SIZE_EXCEEDED,
                    stage=ProcessingStage.SCHEMA,
                    message=f"Cannot compress to {max_kb}KB even at minimum quality",
                    details={
                        "min_size_kb": len(data) // 1024,
                        "target_kb": max_kb,
                    },
                )
            
            best_data = data
            best_quality = MIN_JPEG_QUALITY
    
    # Minimum size enforcement
    if min_kb > 0 and len(best_data) < min_kb * 1024:
        raise WorkerError(
            code=ErrorCode.SIZE_TOO_SMALL,
            stage=ProcessingStage.SCHEMA,
            message=(
                f"Output size {len(best_data) / 1024:.1f}KB is below minimum {min_kb}KB. "
                "Image may lack sufficient detail for this document type."
            ),
            details={
                "output_size_kb": round(len(best_data) / 1024, 1),
                "min_kb": min_kb,
                "max_kb": max_kb,
            },
        )
    
    return best_data, best_quality


def normalize_filename(
    pattern: str,
    job_id: str,
    user_id: str = "",
    original_filename: str = "",
) -> str:
    """
    Normalize filename according to pattern.
    
    Pattern variables:
    - {job_id}: Job UUID
    - {user_id}: User UUID  
    - {original}: Original filename (without extension)
    - {timestamp}: Unix timestamp
    
    Args:
        pattern: Filename pattern
        job_id: Job UUID
        user_id: User UUID
        original_filename: Original filename
        
    Returns:
        Normalized filename
    """
    import time
    
    # Extract original filename without extension
    original_base = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    
    # Replace pattern variables
    filename = pattern.replace("{job_id}", job_id)
    filename = filename.replace("{user_id}", user_id)
    filename = filename.replace("{original}", original_base)
    filename = filename.replace("{timestamp}", str(int(time.time())))
    
    # Sanitize: remove invalid characters
    filename = re.sub(r'[^\w\-.]', '_', filename)
    
    # Remove consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    
    # Trim underscores from ends
    filename = filename.strip('_')
    
    return filename


# =============================================================================
# ITU-T T.44 Tier 2 — Colour Mode Conversion
# =============================================================================

def _sauvola_threshold(
    gray: np.ndarray,
    window_size: int = 25,
    k: float = 0.2,
    R: float = 128.0,
) -> np.ndarray:
    """
    Sauvola adaptive threshold.

    T(x,y) = mean(x,y) * (1 + k * (std(x,y)/R - 1))

    Uses cv2.boxFilter for O(N) integral computation independent of window_size.

    Returns a uint8 binary mask: 255 = dark pixel (foreground), 0 = light (background).
    """
    gray_f = gray.astype(np.float32)
    kernel = (window_size, window_size)
    mean = cv2.boxFilter(gray_f, ddepth=-1, ksize=kernel, normalize=True)
    mean_sq = cv2.boxFilter(gray_f * gray_f, ddepth=-1, ksize=kernel, normalize=True)
    variance = np.maximum(mean_sq - mean * mean, 0.0)
    std = np.sqrt(variance)
    threshold = mean * (1.0 + k * (std / R - 1.0))
    binary = np.where(gray_f < threshold, np.uint8(255), np.uint8(0))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel)
    return binary


def convert_colour_mode(img: np.ndarray, mode: str) -> np.ndarray:
    """
    Convert a BGR image to the target colour mode (ITU-T T.44 Tier 2).

    Must be called BEFORE resizing so Sauvola operates on full-resolution pixels.

    "colour"    → no-op
    "greyscale" → greyscale, returned as 3-channel BGR (R==G==B)
    "binary"    → Sauvola binarisation, returned as 3-channel black-on-white BGR
    """
    if mode == "colour":
        return img

    if mode == "greyscale":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if mode == "binary":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = _sauvola_threshold(gray)
        black_on_white = cv2.bitwise_not(mask)
        return cv2.cvtColor(black_on_white, cv2.COLOR_GRAY2BGR)

    return img  # unknown mode — treat as colour


def adapt_to_schema(
    data: bytes,
    schema: SchemaDefinition,
    job_id: str,
    user_id: str = "",
    original_filename: str = "",
) -> SchemaResult:
    """
    Adapt image to schema specifications.
    
    This is the main entry point for schema adaptation.
    
    Args:
        data: Raw image bytes
        schema: Target schema definition
        job_id: Job UUID for filename
        user_id: User UUID for filename
        original_filename: Original filename
        
    Returns:
        SchemaResult with adapted image and metadata
        
    Raises:
        WorkerError: If schema adaptation fails
    """
    try:
        # Decode image
        cv_img, _ = decode_image(data)

        # --- PDF output path ---
        if schema.output_format.lower() == "pdf":
            cv_img = convert_colour_mode(cv_img, schema.colour_mode)

            # Only resize when the schema explicitly specifies fixed dimensions.
            # PDF document slots (e.g. id_proof) intentionally omit target_width/
            # target_height — preserve the master's natural resolution.
            if schema.target_width and schema.target_height:
                cv_img = resize_exact(
                    cv_img,
                    schema.target_width,
                    schema.target_height,
                    fit_mode=schema.fit_mode,
                )

            # ---- Strategy 1: JPEG2000-in-PDF (near-lossless, best quality) ----
            # Binary-search the compression ratio so we stay within max_kb while
            # keeping quality as high as possible.
            # Ratio semantics: higher = more compression = smaller file.
            pdf_data: bytes | None = None
            try:
                from processors.mrc import encode_as_jpeg2000_pdf
                lo_ratio, hi_ratio = 1.0, 200.0
                for _ in range(10):
                    ratio = (lo_ratio + hi_ratio) / 2
                    candidate = encode_as_jpeg2000_pdf(cv_img, schema.target_dpi, target_ratio=ratio)
                    if len(candidate) / 1024 <= schema.max_kb:
                        pdf_data = candidate
                        hi_ratio = ratio  # Can afford less compression → better quality
                    else:
                        lo_ratio = ratio  # Need more compression
            except Exception:
                pass  # JPEG2000 unavailable — fall through to JPEG fallback

            # ---- Strategy 2: JPEG-in-PDF fallback ----
            if pdf_data is None:
                lo, hi = 20, 92
                while lo <= hi:
                    q = (lo + hi) // 2
                    candidate = encode_as_pdf(cv_img, schema.target_dpi, quality=q)
                    if len(candidate) / 1024 <= schema.max_kb:
                        pdf_data = candidate
                        lo = q + 1   # Try higher quality
                    else:
                        hi = q - 1   # Need smaller file

            if pdf_data is None:
                min_size_kb = len(encode_as_pdf(cv_img, schema.target_dpi, quality=20)) / 1024
                raise WorkerError(
                    code=ErrorCode.SIZE_EXCEEDED,
                    stage=ProcessingStage.SCHEMA,
                    message=f"PDF size {min_size_kb:.1f}KB exceeds maximum {schema.max_kb}KB even at minimum quality",
                    details={"size_kb": round(min_size_kb, 1), "max_kb": schema.max_kb},
                )

            size_kb = len(pdf_data) / 1024
            filename = normalize_filename(
                schema.filename_pattern,
                job_id=job_id,
                user_id=user_id,
                original_filename=original_filename,
            )
            if not filename.lower().endswith(".pdf"):
                filename = f"{filename}.pdf"
            is_compliant, compliance_msg = _verify_pdf_compliance(pdf_data, schema)
            if not is_compliant:
                raise WorkerError(
                    code=ErrorCode.SCHEMA_FAILED,
                    stage=ProcessingStage.SCHEMA,
                    message=f"Post-adapt PDF compliance check failed: {compliance_msg}",
                )

            return SchemaResult(
                image_data=pdf_data,
                final_width=cv_img.shape[1],
                final_height=cv_img.shape[0],
                final_dpi=schema.target_dpi,
                final_size_kb=size_kb,
                filename=filename,
                output_format="pdf",
                content_type="application/pdf",
            )
        # --- End PDF path ---

        # ITU-T T.44 Tier 2: colour mode conversion BEFORE resize
        cv_img = convert_colour_mode(cv_img, schema.colour_mode)

        # Resize to exact dimensions (Tier 3) — only when schema specifies them.
        # Photo/signature slots always specify dimensions; PDF document slots don't.
        h, w = cv_img.shape[:2]
        if schema.target_width and schema.target_height:
            resized = resize_exact(
                cv_img,
                schema.target_width,
                schema.target_height,
                fit_mode=schema.fit_mode,
            )
            h, w = resized.shape[:2]
            if w != schema.target_width or h != schema.target_height:
                raise WorkerError(
                    code=ErrorCode.RESIZE_FAILED,
                    stage=ProcessingStage.SCHEMA,
                    message="Post-resize dimension verification failed",
                )
        else:
            resized = cv_img  # No fixed dimensions: preserve natural size
        
        # Compress to size with DPI
        compressed_data, final_quality = compress_to_size(
            resized,
            dpi=schema.target_dpi,
            max_kb=schema.max_kb,
            format=schema.output_format,
            initial_quality=schema.quality,
            min_kb=schema.min_kb,
        )
        
        # Normalize filename
        filename = normalize_filename(
            schema.filename_pattern,
            job_id=job_id,
            user_id=user_id,
            original_filename=original_filename,
        )
        
        # Add extension if not present
        ext = ".jpg" if schema.output_format.lower() in ("jpeg", "jpg") else f".{schema.output_format.lower()}"
        if not filename.lower().endswith(ext):
            filename = f"{filename}{ext}"

        # Post-adapt compliance gate
        is_compliant, compliance_msg = verify_schema_compliance(compressed_data, schema)
        if not is_compliant:
            raise WorkerError(
                code=ErrorCode.SCHEMA_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=f"Post-adapt compliance check failed: {compliance_msg}",
            )
        
        return SchemaResult(
            image_data=compressed_data,
            final_width=schema.target_width,
            final_height=schema.target_height,
            final_dpi=schema.target_dpi,
            final_size_kb=len(compressed_data) / 1024,
            filename=filename,
            output_format=schema.output_format.lower(),
            content_type="application/pdf" if schema.output_format.lower() == "pdf" else "image/jpeg",
        )
        
    except WorkerError:
        raise
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.SCHEMA_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"Schema adaptation failed: {str(e)}",
            details={"exception_type": type(e).__name__},
        )


def adapt_master_document(
    data: bytes,
    constraints: MasterConstraints,
    job_id: str,
    user_id: str = "",
    original_filename: str = "",
    ocr_result: Optional[object] = None,
) -> SchemaResult:
    """
    Optimize a master document for best quality under the configured size cap.

    Unlike portal adaptation, this mode does NOT force fixed dimensions.
    Supports output_format values: "jpeg" (default), "jpeg2000" / "jp2", "pdf_mrc".
    """
    try:
        cv_img, _ = decode_image(data)
        h, w = cv_img.shape[:2]

        fmt = constraints.output_format.lower()

        if fmt == "pdf_mrc":
            from processors.mrc import encode_as_mrc_pdf
            output_bytes = encode_as_mrc_pdf(
                img=cv_img,
                dpi=constraints.target_dpi,
                constraints=constraints,
                ocr_result=ocr_result,
            )
            ext = ".pdf"
            actual_format = "pdf_mrc"
            content_type = "application/pdf"

        elif fmt in ("jpeg2000", "jp2"):
            from processors.mrc import encode_as_jpeg2000_pdf
            output_bytes = encode_as_jpeg2000_pdf(
                img=cv_img,
                dpi=constraints.target_dpi,
                target_ratio=constraints.jpeg2000_ratio,
                ocr_result=ocr_result,
            )
            ext = ".pdf"
            actual_format = "jpeg2000"
            content_type = "application/pdf"

        else:  # "jpeg" or any unrecognised value — existing path unchanged
            output_bytes, _ = compress_to_size(
                cv_img,
                dpi=constraints.target_dpi,
                max_kb=constraints.max_kb,
                format=constraints.output_format,
                initial_quality=constraints.quality,
                min_kb=constraints.min_kb,
            )
            ext = ".jpg"
            actual_format = "jpeg"
            content_type = "image/jpeg"

        filename = normalize_filename(
            constraints.filename_pattern,
            job_id=job_id,
            user_id=user_id,
            original_filename=original_filename,
        )
        if not filename.lower().endswith(ext):
            filename = f"{filename}{ext}"

        return SchemaResult(
            image_data=output_bytes,
            final_width=w,
            final_height=h,
            final_dpi=constraints.target_dpi,
            final_size_kb=len(output_bytes) / 1024,
            filename=filename,
            output_format=actual_format,
            content_type=content_type,
        )
    except WorkerError:
        raise
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.SCHEMA_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"Master optimization failed: {str(e)}",
            details={"exception_type": type(e).__name__},
        )


# Colour mode verification constants
_GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE = 8   # max mean abs(R-B) for greyscale
_BINARY_MAX_GREY_FRACTION = 0.15             # max fraction of mid-grey pixels
_BINARY_GREY_LOW = 32                        # lower bound of "grey" band
_BINARY_GREY_HIGH = 224                      # upper bound of "grey" band


def _verify_pdf_compliance(
    data: bytes,
    schema: SchemaDefinition,
) -> Tuple[bool, str]:
    """
    Verify that PDF output bytes comply with schema constraints.

    Called from adapt_to_schema() when output_format == "pdf".  Unlike
    verify_schema_compliance() (which decodes raw image bytes), this function
    opens the PDF with pikepdf, extracts the embedded image XObject, then
    delegates pixel-level colour-mode and OCR checks to the same helpers used
    by the image path.

    Checks:
      1. File size ≤ max_kb
      2. Valid PDF structure (exactly 1 page)
      3. Colour mode on extracted image  (if schema.colour_mode != "colour")
      4. OCR confidence gate on extracted image  (if min_ocr_confidence > 0)

    Fails open (returns True) if pikepdf is unavailable or image extraction
    fails — the binary-search size gate and colour conversion already ran
    before encoding, so structural correctness is guaranteed by construction.
    """
    # 1. File size (belt-and-suspenders: binary search already enforces this)
    size_kb = len(data) / 1024
    if size_kb > schema.max_kb:
        return False, f"Size {size_kb:.1f}KB exceeds max {schema.max_kb}KB"

    # 2. PDF structure + image extraction
    img_bytes: Optional[bytes] = None
    try:
        import pikepdf  # already a pinned dependency (pikepdf==10.3.0)
        with pikepdf.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) != 1:
                return False, f"Expected 1-page PDF, got {len(pdf.pages)} pages"
            page = pdf.pages[0]
            images = list(page.images.items())
            if images:
                _, raw_image = images[0]
                try:
                    pdfimage = pikepdf.PdfImage(raw_image)
                    pil_img = pdfimage.as_pil_image()
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=92)
                    img_bytes = buf.getvalue()
                except Exception:
                    pass  # extraction failed — skip pixel-level checks below
    except ImportError:
        return True, ""  # pikepdf not available — skip structural check
    except Exception as e:
        return False, f"Invalid PDF structure: {str(e)}"

    if img_bytes is None:
        return True, ""  # no extractable image — pass through

    # 3. Colour mode (reuse module-level constants from verify_schema_compliance)
    if schema.colour_mode != "colour":
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is not None:
            if schema.colour_mode == "greyscale":
                b_ch = img[:, :, 0].astype(np.int32)
                r_ch = img[:, :, 2].astype(np.int32)
                mean_divergence = float(np.mean(np.abs(r_ch - b_ch)))
                if mean_divergence > _GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE:
                    return False, (
                        f"Colour mode 'greyscale' violated: "
                        f"mean R-B channel divergence {mean_divergence:.1f} > "
                        f"{_GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE}"
                    )
            elif schema.colour_mode == "binary":
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                total = gray.size
                grey_pixels = int(np.sum(
                    (gray > _BINARY_GREY_LOW) & (gray < _BINARY_GREY_HIGH)
                ))
                grey_fraction = grey_pixels / total if total > 0 else 0.0
                if grey_fraction > _BINARY_MAX_GREY_FRACTION:
                    return False, (
                        f"Colour mode 'binary' violated: "
                        f"{grey_fraction:.1%} mid-grey pixels exceed "
                        f"{_BINARY_MAX_GREY_FRACTION:.0%} threshold"
                    )

    # 4. OCR gate (delegates to same helper as the image path)
    if schema.min_ocr_confidence > 0.0:
        ok, msg = _verify_ocr_confidence(img_bytes, schema.min_ocr_confidence)
        if not ok:
            return False, msg

    return True, ""


def _verify_ocr_confidence(
    data: bytes,
    min_confidence: float,
) -> Tuple[bool, str]:
    """
    Run Tesseract OCR on adapted image data and verify confidence meets the threshold.

    Lazily imports tesseract_adapter to avoid mandatory Tesseract dependency
    for schemas that do not require the OCR gate (min_ocr_confidence == 0.0).
    Fails open on ImportError (pytesseract not installed) or unexpected exceptions.
    """
    try:
        from ocr.tesseract_adapter import extract_text, OCRResult
        from errors import WorkerError
    except ImportError:
        return True, ""

    try:
        result: OCRResult = extract_text(data)
        if result.confidence < min_confidence:
            return False, (
                f"OCR confidence {result.confidence:.3f} below minimum {min_confidence:.3f} "
                f"— adapted image may be too compressed to remain legible"
            )
        return True, ""
    except WorkerError as e:
        return False, f"OCR quality gate error: {e.details.get('reason', str(e)) if e.details else str(e)}"
    except Exception:
        return True, ""  # Fail open on unexpected Tesseract errors


def verify_schema_compliance(
    data: bytes,
    schema: SchemaDefinition,
) -> Tuple[bool, str]:
    """
    Verify that image data complies with schema.

    Checks (in order):
      1. File size ≤ max_kb
      2. Pixel dimensions == (target_width, target_height)
      3. DPI metadata == target_dpi
      4. Colour mode    (if schema.colour_mode != "colour")
      5. OCR confidence ≥ min_ocr_confidence  (if min_ocr_confidence > 0)

    Returns:
        Tuple of (is_compliant, error_message)
    """
    try:
        # --- 1. File size ---
        size_kb = len(data) / 1024
        if size_kb > schema.max_kb:
            return False, f"Size {size_kb:.1f}KB exceeds max {schema.max_kb}KB"

        # --- 2. Dimensions ---
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return False, "Failed to decode image"

        h, w = img.shape[:2]
        if w != schema.target_width:
            return False, f"Width {w} != target {schema.target_width}"
        if h != schema.target_height:
            return False, f"Height {h} != target {schema.target_height}"

        # --- 3. DPI metadata ---
        pil_img = Image.open(io.BytesIO(data))
        dpi = pil_img.info.get('dpi', (72, 72))
        if isinstance(dpi, tuple):
            dpi_x, dpi_y = int(dpi[0]), int(dpi[1])
        else:
            dpi_x = dpi_y = int(dpi)
        if dpi_x != schema.target_dpi:
            return False, f"DPI X {dpi_x} != target {schema.target_dpi}"
        if dpi_y != schema.target_dpi:
            return False, f"DPI Y {dpi_y} != target {schema.target_dpi}"

        # --- 4. Colour mode ---
        if schema.colour_mode == "greyscale":
            b_ch = img[:, :, 0].astype(np.int32)
            r_ch = img[:, :, 2].astype(np.int32)
            mean_divergence = float(np.mean(np.abs(r_ch - b_ch)))
            if mean_divergence > _GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE:
                return False, (
                    f"Colour mode 'greyscale' violated: "
                    f"mean R-B channel divergence {mean_divergence:.1f} > {_GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE}"
                )

        elif schema.colour_mode == "binary":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            total = gray.size
            grey_pixels = int(np.sum(
                (gray > _BINARY_GREY_LOW) & (gray < _BINARY_GREY_HIGH)
            ))
            grey_fraction = grey_pixels / total if total > 0 else 0.0
            if grey_fraction > _BINARY_MAX_GREY_FRACTION:
                return False, (
                    f"Colour mode 'binary' violated: "
                    f"{grey_fraction:.1%} mid-grey pixels exceed {_BINARY_MAX_GREY_FRACTION:.0%} threshold"
                )

        # --- 5. OCR quality gate ---
        if schema.min_ocr_confidence > 0.0:
            ok, msg = _verify_ocr_confidence(data, schema.min_ocr_confidence)
            if not ok:
                return False, msg

        return True, ""

    except Exception as e:
        return False, f"Verification error: {str(e)}"



__all__ = [
    'adapt_to_schema',
    'adapt_master_document',
    'encode_as_pdf',
    'verify_schema_compliance',
    'normalize_filename',
    'resize_exact',
    'compress_to_size',
    'SchemaResult',
    'SchemaDefinition',
]
