#!/usr/bin/env python3
"""
Generate synthetic Indian document images for OCR confidence evaluation.

This creates test images with known ground truth text to validate
OCR confidence correlation with accuracy.

Documents generated:
- Aadhaar-like cards (clean scan, phone good, phone dim)
- PAN-like cards (clean, phone)
- Marksheets with tables
- Forms with mixed content
- ID cards with numbers prone to OCR confusion (0/O, 1/I/l)

Each image has known ground truth for accuracy measurement.
"""

import os
import sys
from pathlib import Path

# Add worker to path for imports
WORKER_DIR = Path(__file__).parent.parent.parent.parent / "worker"
sys.path.insert(0, str(WORKER_DIR))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json


OUTPUT_DIR = Path(__file__).parent
MANIFEST_PATH = OUTPUT_DIR / "dataset_manifest.json"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font - uses system fonts available on macOS."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    
    # Fallback to default
    return ImageFont.load_default()


def create_aadhaar_like(name: str, uid: str, dob: str, quality: str) -> Image.Image:
    """Create Aadhaar-like card image."""
    # Standard card dimensions
    width, height = 856, 540
    
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Header
    header_font = get_font(28, bold=True)
    draw.text((width//2, 40), "GOVERNMENT OF INDIA", fill='navy', 
              font=header_font, anchor='mm')
    
    # Aadhaar title
    title_font = get_font(24)
    draw.text((width//2, 80), "आधार - Aadhaar", fill='#CC5500', 
              font=title_font, anchor='mm')
    
    # Name
    name_font = get_font(32, bold=True)
    draw.text((50, 180), name, fill='black', font=name_font)
    
    # DOB
    label_font = get_font(18)
    draw.text((50, 240), f"DOB: {dob}", fill='gray', font=label_font)
    
    # UID number (large, prominent)
    uid_font = get_font(36, bold=True)
    draw.text((50, 350), uid, fill='black', font=uid_font)
    
    # Add degradation based on quality
    if quality == "phone_good_light":
        img = add_phone_good_degradation(img)
    elif quality == "phone_dim_light":
        img = add_phone_dim_degradation(img)
    
    return img


def create_pan_like(name: str, pan: str, dob: str, quality: str) -> Image.Image:
    """Create PAN card-like image."""
    width, height = 856, 540
    
    img = Image.new('RGB', (width, height), color='#FFFEF0')  # Slight cream
    draw = ImageDraw.Draw(img)
    
    # Header
    header_font = get_font(22, bold=True)
    draw.text((width//2, 30), "INCOME TAX DEPARTMENT", fill='navy', 
              font=header_font, anchor='mm')
    draw.text((width//2, 60), "GOVT. OF INDIA", fill='navy', 
              font=get_font(18), anchor='mm')
    
    # PAN title
    title_font = get_font(20)
    draw.text((width//2, 100), "Permanent Account Number", fill='black', 
              font=title_font, anchor='mm')
    
    # PAN number (large)
    pan_font = get_font(40, bold=True)
    draw.text((width//2, 180), pan, fill='black', font=pan_font, anchor='mm')
    
    # Name
    name_font = get_font(28)
    draw.text((50, 280), name, fill='black', font=name_font)
    
    # DOB
    draw.text((50, 340), f"Date of Birth  {dob}", fill='gray', font=get_font(18))
    
    if quality == "phone_good_light":
        img = add_phone_good_degradation(img)
    
    return img


def create_marksheet(name: str, roll_no: str, total: str, percentage: str, quality: str) -> Image.Image:
    """Create marksheet-like image."""
    width, height = 800, 600
    
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Header
    header_font = get_font(24, bold=True)
    draw.text((width//2, 40), "CENTRAL BOARD OF SECONDARY EDUCATION", fill='navy', 
              font=header_font, anchor='mm')
    draw.text((width//2, 80), "MARK SHEET", fill='black', 
              font=get_font(28, bold=True), anchor='mm')
    
    # Student details
    y_pos = 150
    label_font = get_font(20)
    value_font = get_font(22, bold=True)
    
    fields = [
        ("Name:", name),
        ("Roll No:", roll_no),
        ("Total Marks:", f"{total}/500"),
        ("Percentage:", percentage),
    ]
    
    for label, value in fields:
        draw.text((50, y_pos), label, fill='gray', font=label_font)
        draw.text((200, y_pos), value, fill='black', font=value_font)
        y_pos += 50
    
    # Add a simple table border
    draw.rectangle([40, 130, 500, y_pos + 20], outline='black', width=2)
    
    if quality == "phone_dim_light":
        img = add_phone_dim_degradation(img)
    
    return img


def create_form(name: str, app_no: str, date: str, quality: str) -> Image.Image:
    """Create application form-like image."""
    width, height = 800, 600
    
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Header
    draw.text((width//2, 40), "APPLICATION FORM", fill='black', 
              font=get_font(28, bold=True), anchor='mm')
    
    # Form fields
    y_pos = 120
    label_font = get_font(18)
    value_font = get_font(20)
    
    fields = [
        ("Application No:", app_no),
        ("Date:", date),
        ("Name:", name),
        ("Address:", "123 Main Street, Bangalore"),
    ]
    
    for label, value in fields:
        draw.text((50, y_pos), label, fill='gray', font=label_font)
        draw.text((200, y_pos), value, fill='black', font=value_font)
        # Draw underline
        draw.line([(200, y_pos + 25), (550, y_pos + 25)], fill='lightgray', width=1)
        y_pos += 60
    
    if quality == "phone_slight_blur":
        img = add_blur_degradation(img)
    
    return img


def create_certificate(name: str, cert_no: str, date: str, quality: str) -> Image.Image:
    """Create certificate-like image."""
    width, height = 800, 600
    
    img = Image.new('RGB', (width, height), color='#FFFFF8')
    draw = ImageDraw.Draw(img)
    
    # Border
    draw.rectangle([20, 20, width-20, height-20], outline='gold', width=3)
    draw.rectangle([30, 30, width-30, height-30], outline='navy', width=1)
    
    # Header
    draw.text((width//2, 80), "CERTIFICATE OF COMPLETION", fill='navy', 
              font=get_font(28, bold=True), anchor='mm')
    
    # Body
    draw.text((width//2, 160), "This is to certify that", fill='gray', 
              font=get_font(18), anchor='mm')
    draw.text((width//2, 220), name, fill='black', 
              font=get_font(32, bold=True), anchor='mm')
    
    # Details
    draw.text((width//2, 320), f"Certificate No: {cert_no}", fill='gray', 
              font=get_font(18), anchor='mm')
    draw.text((width//2, 360), f"Date: {date}", fill='gray', 
              font=get_font(18), anchor='mm')
    
    return img


def create_id_card(emp_id: str, dob: str, phone: str, quality: str) -> Image.Image:
    """Create ID card with numbers prone to OCR confusion (0/O, 1/I)."""
    width, height = 540, 340
    
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Header with colored band
    draw.rectangle([0, 0, width, 60], fill='#003366')
    draw.text((width//2, 30), "EMPLOYEE ID CARD", fill='white', 
              font=get_font(22, bold=True), anchor='mm')
    
    # Employee ID (with 0s that might be confused with Os)
    draw.text((50, 90), "Employee ID:", fill='gray', font=get_font(16))
    draw.text((50, 120), emp_id, fill='black', font=get_font(28, bold=True))
    
    # DOB
    draw.text((50, 170), f"DOB: {dob}", fill='gray', font=get_font(16))
    
    # Phone
    draw.text((50, 210), f"Phone: {phone}", fill='gray', font=get_font(16))
    
    # Valid till
    draw.text((50, 260), "Valid Till: 31/12/2026", fill='gray', font=get_font(14))
    
    return img


def create_payment_receipt(name: str, ref_no: str, amount: str, quality: str) -> Image.Image:
    """Create payment receipt form."""
    width, height = 600, 400
    
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Header
    draw.text((width//2, 30), "PAYMENT RECEIPT", fill='black', 
              font=get_font(24, bold=True), anchor='mm')
    
    # Details
    y_pos = 100
    fields = [
        ("Reference No:", ref_no),
        ("Name:", name),
        ("Amount:", f"Rs. {amount}"),
        ("Date:", "27/01/2026"),
    ]
    
    for label, value in fields:
        draw.text((50, y_pos), label, fill='gray', font=get_font(16))
        draw.text((200, y_pos), value, fill='black', font=get_font(18))
        y_pos += 50
    
    if quality == "phone_slight_blur":
        img = add_blur_degradation(img)
    
    return img


def add_phone_good_degradation(img: Image.Image) -> Image.Image:
    """Simulate phone capture in good lighting."""
    # Slight perspective distortion
    arr = np.array(img)
    
    # Add slight noise
    noise = np.random.normal(0, 3, arr.shape).astype(np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Slight color temperature shift
    arr[:, :, 2] = np.clip(arr[:, :, 2] * 1.02, 0, 255).astype(np.uint8)  # Warmer
    
    return Image.fromarray(arr)


def add_phone_dim_degradation(img: Image.Image) -> Image.Image:
    """Simulate phone capture in dim lighting."""
    arr = np.array(img)
    
    # Reduce brightness
    arr = (arr * 0.7).astype(np.uint8)
    
    # Add significant noise
    noise = np.random.normal(0, 12, arr.shape).astype(np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Reduce contrast
    mean = np.mean(arr)
    arr = np.clip((arr - mean) * 0.8 + mean, 0, 255).astype(np.uint8)
    
    # Add slight blur
    img = Image.fromarray(arr)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    
    return img


def add_blur_degradation(img: Image.Image) -> Image.Image:
    """Add blur to simulate shaky phone capture."""
    # Gaussian blur
    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    
    # Add noise
    arr = np.array(img)
    noise = np.random.normal(0, 5, arr.shape).astype(np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    return Image.fromarray(arr)


def generate_dataset():
    """Generate all test images from manifest."""
    with open(MANIFEST_PATH, 'r') as f:
        manifest = json.load(f)
    
    generators = {
        "aadhaar_clean": lambda d: create_aadhaar_like(
            d["critical_fields"]["name"], 
            d["critical_fields"]["uid"],
            d["critical_fields"]["dob"],
            d["source_quality"]
        ),
        "pan_clean": lambda d: create_pan_like(
            d["critical_fields"]["name"],
            d["critical_fields"]["pan"],
            d["critical_fields"]["dob"],
            d["source_quality"]
        ),
        "marksheet_typed": lambda d: create_marksheet(
            d["critical_fields"]["name"],
            d["critical_fields"]["roll_no"],
            d["critical_fields"]["total"],
            d["critical_fields"]["percentage"],
            d["source_quality"]
        ),
        "form_typed": lambda d: create_form(
            d["critical_fields"]["name"],
            d["critical_fields"]["application_no"],
            d["critical_fields"]["date"],
            d["source_quality"]
        ),
        "certificate_clean": lambda d: create_certificate(
            d["critical_fields"]["name"],
            d["critical_fields"]["cert_no"],
            d["critical_fields"]["date"],
            d["source_quality"]
        ),
        "aadhaar_phone_good": lambda d: create_aadhaar_like(
            d["critical_fields"]["name"],
            d["critical_fields"]["uid"],
            d["critical_fields"]["dob"],
            d["source_quality"]
        ),
        "pan_phone_good": lambda d: create_pan_like(
            d["critical_fields"]["name"],
            d["critical_fields"]["pan"],
            d["critical_fields"]["dob"],
            d["source_quality"]
        ),
        "marksheet_phone_dim": lambda d: create_marksheet(
            d["critical_fields"]["name"],
            d["critical_fields"]["roll_no"],
            d["critical_fields"]["total"],
            d["critical_fields"]["percentage"],
            d["source_quality"]
        ),
        "id_mixed_numbers": lambda d: create_id_card(
            d["critical_fields"]["emp_id"],
            d["critical_fields"]["dob"],
            d["critical_fields"]["phone"],
            d["source_quality"]
        ),
        "form_phone_blur": lambda d: create_payment_receipt(
            d["critical_fields"]["name"],
            d["critical_fields"]["ref_no"],
            d["critical_fields"]["amount"],
            d["source_quality"]
        ),
    }
    
    generated = []
    for doc in manifest["documents"]:
        doc_id = doc["id"]
        filename = doc["filename"]
        
        if doc_id in generators:
            print(f"Generating {filename}...")
            img = generators[doc_id](doc)
            output_path = OUTPUT_DIR / filename
            img.save(output_path, "JPEG", quality=92)
            generated.append(filename)
        else:
            print(f"Warning: No generator for {doc_id}")
    
    print(f"\nGenerated {len(generated)} test images")
    return generated


if __name__ == "__main__":
    generate_dataset()
