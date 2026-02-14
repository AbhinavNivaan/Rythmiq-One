"""
PDF creation and image combining processor.

Creates master documents from multiple images:
- Combines images into single PDF
- Maintains original quality
- Optimizes file size
- Supports A4 and Letter formats

CPU-only, deterministic output.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from errors import WorkerError, ErrorCode, ProcessingStage


logger = logging.getLogger(__name__)

# Standard page sizes in points (72 points = 1 inch)
PAGE_SIZES = {
    "a4": (595, 842),      # 210mm x 297mm
    "letter": (612, 792),  # 8.5" x 11"
    "legal": (612, 1008),  # 8.5" x 14"
}

# Default DPI for PDF
DEFAULT_DPI = 150


@dataclass
class PDFOptions:
    """Configuration for PDF creation."""
    page_size: Literal["a4", "letter", "legal"] = "a4"
    dpi: int = DEFAULT_DPI
    quality: int = 85
    fit_mode: Literal["contain", "cover", "stretch"] = "contain"
    background_color: Tuple[int, int, int] = (255, 255, 255)  # White
    margin_pts: int = 36  # 0.5 inch margin
    title: Optional[str] = None
    author: str = "Rythmiq One"


@dataclass
class PDFResult:
    """Result from PDF creation."""
    pdf_bytes: bytes
    page_count: int
    total_size_bytes: int
    pages_info: List[dict]


def decode_image_pil(data: bytes) -> Image.Image:
    """
    Decode image bytes to PIL Image.
    
    Args:
        data: Raw image bytes
        
    Returns:
        PIL Image in RGB mode
        
    Raises:
        WorkerError: If image cannot be decoded
    """
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.ENHANCE,
            message=f"Failed to decode image: {str(e)}",
        )


def fit_image_to_page(
    img: Image.Image,
    page_width: int,
    page_height: int,
    margin: int,
    fit_mode: str,
) -> Tuple[Image.Image, Tuple[int, int]]:
    """
    Resize image to fit within page bounds.
    
    Args:
        img: PIL Image
        page_width: Page width in points
        page_height: Page height in points
        margin: Margin in points
        fit_mode: How to fit image ('contain', 'cover', 'stretch')
        
    Returns:
        Tuple of (resized image, position on page)
    """
    available_width = page_width - (2 * margin)
    available_height = page_height - (2 * margin)
    
    img_width, img_height = img.size
    
    if fit_mode == "stretch":
        # Stretch to fill available area
        new_size = (available_width, available_height)
        position = (margin, margin)
    elif fit_mode == "cover":
        # Scale to cover, may crop
        scale = max(available_width / img_width, available_height / img_height)
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        new_size = (new_width, new_height)
        # Center the image
        x = margin + (available_width - new_width) // 2
        y = margin + (available_height - new_height) // 2
        position = (x, y)
    else:
        # Contain (default) - fit within bounds, maintain aspect ratio
        scale = min(available_width / img_width, available_height / img_height)
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        new_size = (new_width, new_height)
        # Center the image
        x = margin + (available_width - new_width) // 2
        y = margin + (available_height - new_height) // 2
        position = (x, y)
    
    resized = img.resize(new_size, Image.Resampling.LANCZOS)
    return resized, position


def create_pdf_from_images(
    images: List[bytes],
    options: Optional[PDFOptions] = None,
) -> PDFResult:
    """
    Create a PDF document from multiple images.
    
    Each image becomes one page in the PDF.
    Images are fitted to the page while maintaining aspect ratio.
    
    Args:
        images: List of image bytes
        options: PDF creation options
        
    Returns:
        PDFResult with PDF bytes and metadata
        
    Raises:
        WorkerError: If PDF creation fails
    """
    if not images:
        raise WorkerError(
            code=ErrorCode.INVALID_PAYLOAD,
            stage=ProcessingStage.ENHANCE,
            message="No images provided for PDF creation",
        )
    
    opts = options or PDFOptions()
    page_size = PAGE_SIZES.get(opts.page_size, PAGE_SIZES["a4"])
    
    logger.info(f"Creating PDF with {len(images)} pages, size={opts.page_size}")
    
    pil_images: List[Image.Image] = []
    pages_info: List[dict] = []
    
    for idx, img_bytes in enumerate(images):
        try:
            # Decode image
            img = decode_image_pil(img_bytes)
            original_size = img.size
            
            # Fit to page
            fitted_img, position = fit_image_to_page(
                img,
                page_size[0],
                page_size[1],
                opts.margin_pts,
                opts.fit_mode,
            )
            
            # Create page canvas with background
            page = Image.new("RGB", page_size, opts.background_color)
            page.paste(fitted_img, position)
            
            pil_images.append(page)
            pages_info.append({
                "page": idx + 1,
                "original_size": {"width": original_size[0], "height": original_size[1]},
                "fitted_size": {"width": fitted_img.size[0], "height": fitted_img.size[1]},
            })
            
        except WorkerError:
            raise
        except Exception as e:
            raise WorkerError(
                code=ErrorCode.ENHANCE_FAILED,
                stage=ProcessingStage.ENHANCE,
                message=f"Failed to process image {idx + 1}: {str(e)}",
            )
    
    # Create PDF
    try:
        pdf_buffer = io.BytesIO()
        
        # Save first image as PDF with remaining images appended
        if len(pil_images) == 1:
            pil_images[0].save(
                pdf_buffer,
                format="PDF",
                resolution=opts.dpi,
            )
        else:
            pil_images[0].save(
                pdf_buffer,
                format="PDF",
                resolution=opts.dpi,
                save_all=True,
                append_images=pil_images[1:],
            )
        
        pdf_bytes = pdf_buffer.getvalue()
        
        logger.info(f"PDF created: {len(pil_images)} pages, {len(pdf_bytes)} bytes")
        
        return PDFResult(
            pdf_bytes=pdf_bytes,
            page_count=len(pil_images),
            total_size_bytes=len(pdf_bytes),
            pages_info=pages_info,
        )
        
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.ENHANCE_FAILED,
            stage=ProcessingStage.ENHANCE,
            message=f"Failed to create PDF: {str(e)}",
        )


def create_master_image(
    images: List[bytes],
    layout: Literal["vertical", "horizontal", "grid"] = "vertical",
    spacing: int = 20,
    background_color: Tuple[int, int, int] = (255, 255, 255),
) -> bytes:
    """
    Combine multiple images into a single master image.
    
    Useful for creating a single document image from multiple captures.
    
    Args:
        images: List of image bytes
        layout: How to arrange images
        spacing: Pixels between images
        background_color: Background fill color
        
    Returns:
        Combined image as JPEG bytes
    """
    if not images:
        raise WorkerError(
            code=ErrorCode.INVALID_PAYLOAD,
            stage=ProcessingStage.ENHANCE,
            message="No images provided for master creation",
        )
    
    # Decode all images
    pil_images: List[Image.Image] = []
    for img_bytes in images:
        pil_images.append(decode_image_pil(img_bytes))
    
    if layout == "vertical":
        # Stack vertically
        max_width = max(img.width for img in pil_images)
        total_height = sum(img.height for img in pil_images) + spacing * (len(pil_images) - 1)
        
        canvas = Image.new("RGB", (max_width, total_height), background_color)
        y_offset = 0
        
        for img in pil_images:
            # Center horizontally
            x_offset = (max_width - img.width) // 2
            canvas.paste(img, (x_offset, y_offset))
            y_offset += img.height + spacing
            
    elif layout == "horizontal":
        # Stack horizontally
        total_width = sum(img.width for img in pil_images) + spacing * (len(pil_images) - 1)
        max_height = max(img.height for img in pil_images)
        
        canvas = Image.new("RGB", (total_width, max_height), background_color)
        x_offset = 0
        
        for img in pil_images:
            # Center vertically
            y_offset = (max_height - img.height) // 2
            canvas.paste(img, (x_offset, y_offset))
            x_offset += img.width + spacing
            
    else:
        # Grid layout (2 columns)
        cols = 2
        rows = (len(pil_images) + 1) // 2
        
        # Normalize all images to same width
        target_width = max(img.width for img in pil_images)
        
        resized = []
        for img in pil_images:
            if img.width != target_width:
                ratio = target_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
            resized.append(img)
        
        max_height = max(img.height for img in resized)
        total_width = target_width * cols + spacing * (cols - 1)
        total_height = max_height * rows + spacing * (rows - 1)
        
        canvas = Image.new("RGB", (total_width, total_height), background_color)
        
        for idx, img in enumerate(resized):
            row = idx // cols
            col = idx % cols
            x = col * (target_width + spacing)
            y = row * (max_height + spacing)
            canvas.paste(img, (x, y))
    
    # Encode as JPEG
    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def extract_images_from_pdf(pdf_bytes: bytes) -> List[bytes]:
    """
    Extract images from a PDF document.
    
    Useful for processing existing PDFs.
    
    Args:
        pdf_bytes: PDF file bytes
        
    Returns:
        List of image bytes (one per page)
    """
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images: List[bytes] = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render page to image at 150 DPI
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            images.append(img_bytes)
        
        doc.close()
        return images
        
    except ImportError:
        raise WorkerError(
            code=ErrorCode.INTERNAL_ERROR,
            stage=ProcessingStage.ENHANCE,
            message="PyMuPDF (fitz) not available for PDF extraction",
        )
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.ENHANCE,
            message=f"Failed to extract images from PDF: {str(e)}",
        )
