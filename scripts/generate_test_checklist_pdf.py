#!/usr/bin/env python3
"""Generate the edge-case test checklist PDF for the transformation pipeline."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, KeepTogether,
)

PAGE = landscape(A4)
MARGIN = 15 * mm
OUTPUT = "docs/Edge_Case_Test_Checklist.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("CellText", parent=styles["Normal"], fontSize=8, leading=10))
styles.add(ParagraphStyle("CellBold", parent=styles["Normal"], fontSize=8, leading=10, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("HeaderWhite", parent=styles["Normal"], fontSize=8, leading=10, fontName="Helvetica-Bold", textColor=colors.white))
styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13, spaceAfter=6, spaceBefore=12))
styles.add(ParagraphStyle("AnnexHead", parent=styles["Heading3"], fontSize=11, spaceAfter=4, spaceBefore=10))
styles.add(ParagraphStyle("AnnexBody", parent=styles["Normal"], fontSize=9, leading=12, spaceAfter=4))
styles.add(ParagraphStyle("AnnexTerm", parent=styles["Normal"], fontSize=9, leading=12, fontName="Helvetica-Bold", spaceAfter=1))
styles.add(ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=18, spaceAfter=4))
styles.add(ParagraphStyle("SubtitleStyle", parent=styles["Normal"], fontSize=11, textColor=colors.grey, spaceAfter=16))

# ---------------------------------------------------------------------------
# Checkbox: leave cells empty; the grid border IS the checkbox
# ---------------------------------------------------------------------------
CHK = ""


# ---------------------------------------------------------------------------
# Data: (section_title, job_type, [(id, document, surface, lighting, notes)])
# ---------------------------------------------------------------------------

def _rows():
    """Return all test-case sections."""

    sections = []

    # ── MASTER CREATION ──────────────────────────────────────────────────

    # -- Portrait Photos --------------------------------------------------
    rows = [
        ("M-PH-01", "Passport Photo", "White A4 paper", "Normal tube light", "Near-zero contrast boundary for face crop"),
        ("M-PH-02", "Passport Photo", "Light wood table", "Normal tube light", "Low contrast with beige card area"),
        ("M-PH-03", "Passport Photo", "Dark wood table", "Normal tube light", "Table may bleed into crop"),
        ("M-PH-04", "Passport Photo", "Patterned bedsheet", "Normal tube light", "Background noise vs face detection"),
        ("M-PH-05", "Passport Photo", "White bedsheet (flat)", "Normal tube light", "Texture mimics paper grain"),
        ("M-PH-06", "Passport Photo", "Dark / black paper", "Normal tube light", "High contrast but inverted Otsu polarity"),
        ("M-PH-07", "Passport Photo", "Red coloured paper", "Normal tube light", "Saturation blob strategy stressed"),
        ("M-PH-08", "Passport Photo", "Green coloured paper", "Normal tube light", "Saturation blob strategy stressed"),
        ("M-PH-09", "Passport Photo", "Blue coloured paper", "Normal tube light", "Saturation blob strategy stressed"),
        ("M-PH-10", "Passport Photo", "Glass surface", "Normal tube light", "Specular reflections create false edges"),
        ("M-PH-11", "Passport Photo", "Granite / marble counter", "Normal tube light", "Speckled texture adds noise"),
        ("M-PH-12", "Passport Photo", "Cluttered desk", "Normal tube light", "Multiple contour candidates"),
        ("M-PH-13", "Passport Photo", "Hand-held (fingers visible)", "Normal tube light", "Skin-tone blobs near boundary"),
        ("M-PH-14", "Passport Photo", "Lap / dark trousers", "Normal tube light", "Curved surface + fabric texture"),
        ("M-PH-15", "Passport Photo", "Floor tile (white/beige)", "Normal tube light", "Grout lines = false quad candidates"),
        ("M-PH-16", "Passport Photo", "Clipboard / exam desk", "Normal tube light", "Clip shadow, partially occluded edges"),
        ("M-PH-17", "Passport Photo", "Car dashboard", "Harsh direct sunlight", "Curved surface + overexposure"),
        ("M-PH-18", "Passport Photo", "Dark wood table", "Low indoor light", "Underexposed + noisy"),
        ("M-PH-19", "Passport Photo", "White A4 paper", "Fluorescent tube (yellow cast)", "Colour cast affects face detection"),
        ("M-PH-20", "Passport Photo", "Light wood table", "Mixed lighting (window + tube)", "Uneven exposure across photo"),
        ("M-PH-21", "Passport Photo", "White bedsheet (flat)", "Flash on (hotspot)", "Centre wash-out on face"),
        ("M-PH-22", "Passport Photo", "Dark wood table", "Shadow across document", "Partial face in shadow"),
        ("M-PH-23", "ID Photo", "White A4 paper", "Normal tube light", "Standard ID photo format"),
        ("M-PH-24", "ID Photo", "Dark wood table", "Low indoor light", "Dark surface + dim light combo"),
        ("M-PH-25", "Profile Photo", "Cluttered desk", "Mixed lighting", "Non-frontal face possible"),
        ("M-PH-26", "Passport Photo (baby)", "White bedsheet (flat)", "Normal tube light", "Small face, Haar cascade min size"),
        ("M-PH-27", "Passport Photo (hijab/turban)", "White A4 paper", "Normal tube light", "Partial face, head covering"),
        ("M-PH-28", "Passport Photo (glasses)", "Light wood table", "Low indoor light", "Haar cascade may miss face"),
        ("M-PH-29", "Passport Photo (pre-framed studio)", "N/A (already cropped)", "Studio lighting", "Should NOT double-crop"),
        ("M-PH-30", "Passport Photo (very high-res 4000x6000)", "White A4 paper", "Normal tube light", "GUARD-001 skip + compression loop"),
    ]
    sections.append(("Master Creation: Portrait Photos", "Master", rows))

    # -- Postcard / Landscape Photos --------------------------------------
    rows = [
        ("M-PC-01", "Postcard Photo", "White A4 paper", "Normal tube light", "Document crop path (not face crop)"),
        ("M-PC-02", "Postcard Photo", "Cluttered desk", "Normal tube light", "Contour competition"),
        ("M-PC-03", "Postcard Photo", "Dark wood table", "Harsh direct sunlight", "Overexposed + dark surface"),
        ("M-PC-04", "Postcard Photo (portrait orientation)", "Light wood table", "Normal tube light", "Large rotation detection needed"),
    ]
    sections.append(("Master Creation: Postcard / Landscape Photos", "Master", rows))

    # -- Signatures --------------------------------------------------------
    rows = [
        ("M-SG-01", "Signature (blue ink)", "White A4 paper on white bedsheet", "Normal tube light", "Double white-on-white boundary"),
        ("M-SG-02", "Signature (blue ink)", "Ruled notebook paper", "Normal tube light", "Rule lines vs ink in Otsu binarization"),
        ("M-SG-03", "Signature (black ink)", "Off-white / yellowed paper", "Normal tube light", "Colour cast in binarization"),
        ("M-SG-04", "Signature (pencil, faint)", "White A4 paper", "Normal tube light", "Very low contrast strokes"),
        ("M-SG-05", "Signature (blue ink)", "Dark / black paper", "Normal tube light", "Inverted polarity"),
        ("M-SG-06", "Signature (wet / smudged)", "White A4 paper", "Normal tube light", "Binarization fragments strokes"),
        ("M-SG-07", "Signature + thumb impression", "White A4 paper", "Normal tube light", "Extra blob near boundary"),
        ("M-SG-08", "Signature on printed form", "Cluttered desk", "Mixed lighting", "Text above/below, uneven exposure"),
        ("M-SG-09", "Signature (thick marker)", "White A4 paper", "Normal tube light", "Thick strokes may merge at small size"),
        ("M-SG-10", "Signature (blue ink)", "Red coloured paper", "Normal tube light", "Colour interference with binarization"),
        ("M-SG-11", "Signature (blue ink)", "Light wood table", "Flash on (hotspot)", "Reflection on paper surface"),
        ("M-SG-12", "Signature (blue ink)", "Granite / marble counter", "Normal tube light", "Speckled texture noise"),
    ]
    sections.append(("Master Creation: Signatures", "Master", rows))

    # -- Identity Documents ------------------------------------------------
    rows = [
        ("M-ID-01", "PAN Card", "Dark wood table", "Normal tube light", "Reference master job case"),
        ("M-ID-02", "PAN Card", "Light wood table", "Normal tube light", "Low contrast with beige card area"),
        ("M-ID-03", "PAN Card", "White A4 paper", "Normal tube light", "Card edge vs paper edge confusion"),
        ("M-ID-04", "PAN Card", "White bedsheet (flat)", "Normal tube light", "Texture mimics card edge"),
        ("M-ID-05", "PAN Card", "Patterned bedsheet", "Normal tube light", "Pattern vs card contour"),
        ("M-ID-06", "PAN Card", "Dark / black paper", "Normal tube light", "High contrast, inverted polarity"),
        ("M-ID-07", "PAN Card", "Red coloured paper", "Normal tube light", "Saturation strategy stressed"),
        ("M-ID-08", "PAN Card", "Glass surface", "Normal tube light", "Specular reflections on laminate"),
        ("M-ID-09", "PAN Card", "Cluttered desk", "Normal tube light", "Multiple contour candidates"),
        ("M-ID-10", "PAN Card", "Hand-held (fingers visible)", "Normal tube light", "Fingers overlap card edges"),
        ("M-ID-11", "PAN Card", "Lap / dark trousers", "Low indoor light", "Curved surface + dim"),
        ("M-ID-12", "PAN Card", "Car dashboard", "Harsh direct sunlight", "Overexposure + curve"),
        ("M-ID-13", "PAN Card", "Floor tile (white/beige)", "Normal tube light", "Grout lines as false edges"),
        ("M-ID-14", "PAN Card", "Clipboard / exam desk", "Normal tube light", "Clip shadow on card"),
        ("M-ID-15", "PAN Card", "Granite / marble counter", "Normal tube light", "Speckled texture"),
        ("M-ID-16", "PAN Card (new e-PAN on plain paper)", "Dark wood table", "Normal tube light", "Looks like document, not card"),
        ("M-ID-17", "PAN Card", "Dark wood table", "Flash on (hotspot)", "Laminate reflection + dark wood"),
        ("M-ID-18", "PAN Card", "White A4 paper", "Mixed lighting (window + tube)", "Uneven exposure on card"),
        ("M-ID-19", "PAN Card", "Light wood table", "Shadow across document", "Partial card in shadow"),
        ("M-ID-20", "PAN Card", "Green coloured paper", "Normal tube light", "Green background vs card"),
        ("M-ID-21", "Aadhaar Card (laminated)", "Dark wood table", "Flash on (hotspot)", "Specular reflection on laminate"),
        ("M-ID-22", "Aadhaar Card (laminated)", "White bedsheet (flat)", "Normal tube light", "Low contrast + reflective surface"),
        ("M-ID-23", "Aadhaar Card (old blue format)", "Light wood table", "Normal tube light", "Non-standard aspect ratio"),
        ("M-ID-24", "Aadhaar Card", "Hand-held (fingers visible)", "Low indoor light", "Fingers + dim light"),
        ("M-ID-25", "Voter ID (booklet, open to photo page)", "Dark wood table", "Normal tube light", "Non-rectangular document shape"),
        ("M-ID-26", "Voter ID (booklet, open to photo page)", "White A4 paper", "Fluorescent tube (yellow cast)", "Colour cast on booklet"),
        ("M-ID-27", "Driving Licence (new smart card)", "Dark wood table", "Normal tube light", "Small credit-card sized"),
        ("M-ID-28", "Driving Licence (old paper, laminated)", "Light wood table", "Flash on (hotspot)", "Large format, yellowed, reflective"),
        ("M-ID-29", "Ration Card (folded, creased)", "Dark wood table", "Normal tube light", "Fold lines as false edges"),
        ("M-ID-30", "Ration Card", "Patterned bedsheet", "Low indoor light", "Pattern + dim + creases"),
        ("M-ID-31", "Two ID cards on same surface", "Dark wood table", "Normal tube light", "Must pick correct one or reject"),
        ("M-ID-32", "ID card partially under a book", "Light wood table", "Normal tube light", "Occluded edges, incomplete quad"),
    ]
    sections.append(("Master Creation: Identity Documents", "Master", rows))

    # -- Academic Documents ------------------------------------------------
    rows = [
        ("M-AC-01", "Class 10 Marksheet (A4)", "White bedsheet (flat)", "Normal tube light", "Near-zero contrast boundary"),
        ("M-AC-02", "Class 10 Marksheet (A4)", "Dark wood table", "Normal tube light", "Standard case"),
        ("M-AC-03", "Class 10 Marksheet (A4)", "Light wood table", "Normal tube light", "Low contrast edge"),
        ("M-AC-04", "Class 10 Marksheet (A4)", "White A4 paper", "Normal tube light", "White on white"),
        ("M-AC-05", "Class 12 Marksheet (coloured security paper)", "Dark wood table", "Normal tube light", "Saturation blob strategy needed"),
        ("M-AC-06", "Class 12 Marksheet (coloured security paper)", "Red coloured paper", "Normal tube light", "Both surfaces coloured"),
        ("M-AC-07", "Marksheet (folded, then unfolded)", "Dark wood table", "Normal tube light", "Crease line across middle"),
        ("M-AC-08", "Marksheet (old, yellowed)", "White A4 paper", "Normal tube light", "Colour cast in binary conversion"),
        ("M-AC-09", "Marksheet (laminated)", "Light wood table", "Flash on (hotspot)", "Reflection + perspective"),
        ("M-AC-10", "Marksheet (laminated)", "Dark wood table", "Normal tube light + angle 15-30 deg", "Angled perspective warp"),
        ("M-AC-11", "Marksheet", "Clipboard / exam desk", "Normal tube light", "Clip and desk edges compete"),
        ("M-AC-12", "Migration Certificate (smaller than A4)", "Dark wood table", "Normal tube light", "Different aspect ratio"),
        ("M-AC-13", "Handwritten marksheet (rural format)", "White bedsheet (flat)", "Low indoor light", "Low print quality, dim light"),
        ("M-AC-14", "Marksheet", "Granite / marble counter", "Mixed lighting", "Speckled texture + uneven light"),
        ("M-AC-15", "Class 10 Marksheet (A4)", "Patterned bedsheet", "Normal tube light", "Pattern interferes with edges"),
        ("M-AC-16", "Class 10 Marksheet (A4)", "Floor tile (white/beige)", "Normal tube light", "Grout lines as false edges"),
    ]
    sections.append(("Master Creation: Academic Documents (Marksheets)", "Master", rows))

    # -- Certificates ------------------------------------------------------
    rows = [
        ("M-CT-01", "Caste Certificate (stamp paper)", "Dark wood table", "Normal tube light", "Textured paper confuses edge detection"),
        ("M-CT-02", "Caste Certificate", "White bedsheet (flat)", "Normal tube light", "Low contrast"),
        ("M-CT-03", "PwD Medical Certificate (stamps/seals)", "Light wood table", "Normal tube light", "Stamps overlap text, OCR drops"),
        ("M-CT-04", "Certificate with wet seal (red/blue ink)", "Dark wood table", "Normal tube light", "Colour bleed in binarization"),
        ("M-CT-05", "Certificate (thin paper, show-through)", "White A4 paper", "Normal tube light", "Reverse side text visible"),
        ("M-CT-06", "Category Certificate", "Patterned bedsheet", "Mixed lighting", "Pattern + uneven exposure"),
        ("M-CT-07", "Category Certificate", "Dark / black paper", "Normal tube light", "High contrast background"),
        ("M-CT-08", "Category Certificate", "Glass surface", "Flash on (hotspot)", "Reflection on glass"),
    ]
    sections.append(("Master Creation: Certificates (Caste / Category / Medical)", "Master", rows))

    # -- Financial / Address -----------------------------------------------
    rows = [
        ("M-FN-01", "Bank Statement (thermal print)", "Dark wood table", "Normal tube light", "Fading thermal text"),
        ("M-FN-02", "Utility Bill (glossy colour)", "Light wood table", "Flash on (hotspot)", "Colour glare on glossy paper"),
        ("M-FN-03", "Rent Agreement (multi-page, stapled)", "Dark wood table", "Normal tube light", "Staple shadow + page curl"),
        ("M-FN-04", "Bank Statement", "White bedsheet (flat)", "Low indoor light", "Low contrast + dim"),
        ("M-FN-05", "Utility Bill", "Cluttered desk", "Mixed lighting", "Contour competition + uneven light"),
    ]
    sections.append(("Master Creation: Financial / Address Documents", "Master", rows))

    # ── ADAPTATION JOBS ──────────────────────────────────────────────────

    # -- Portrait Photo Adaptations ----------------------------------------
    rows = [
        ("A-PH-01", "Passport Photo -> NEET 400x400 letterbox", "White A4 paper", "Normal tube light", "Letterbox padding symmetry"),
        ("A-PH-02", "Passport Photo -> Passport Seva 413x531 300dpi", "Dark wood table", "Normal tube light", "DPI upscale from 200dpi source"),
        ("A-PH-03", "Passport Photo -> UPSC (stretch fit)", "Light wood table", "Normal tube light", "Stretch vs letterbox correctness"),
        ("A-PH-04", "Small photo 200x200 -> 400x400 target", "White A4 paper", "Normal tube light", "Upscaling quality on small source"),
        ("A-PH-05", "Large photo 6000x4000 -> 400x400 target", "Dark wood table", "Normal tube light", "Downscaling preserves face"),
        ("A-PH-06", "Landscape photo -> portrait schema", "Light wood table", "Normal tube light", "Rotation detection + letterbox"),
        ("A-PH-07", "Photo already at exact target dimensions", "N/A (pre-processed)", "N/A", "Pass-through without re-encoding artifacts"),
        ("A-PH-08", "Postcard Photo -> 800x1200 letterbox", "Dark wood table", "Normal tube light", "Landscape preserved, white bars"),
        ("A-PH-09", "Passport Photo -> NEET 400x400 letterbox", "Patterned bedsheet", "Flash on (hotspot)", "Worst-case combo: pattern + flash"),
        ("A-PH-10", "Passport Photo -> Aadhaar 165x213 200dpi", "White bedsheet (flat)", "Normal tube light", "Extreme downscale, face must be clear"),
    ]
    sections.append(("Adaptation: Portrait Photos", "Adapt", rows))

    # -- Signature Adaptations ---------------------------------------------
    rows = [
        ("A-SG-01", "Blue signature -> 362x178 binary", "White A4 paper", "Normal tube light", "Ink density at small size"),
        ("A-SG-02", "Thick marker signature -> 362x178 binary", "White A4 paper", "Normal tube light", "Strokes may merge"),
        ("A-SG-03", "Very thin/light signature -> binary", "White A4 paper", "Normal tube light", "Strokes may vanish"),
        ("A-SG-04", "Signature on ruled paper -> binary", "Light wood table", "Normal tube light", "Rule lines must be suppressed"),
        ("A-SG-05", "Already-binarized signature -> re-adapt", "N/A (pre-processed)", "N/A", "Should not double-process"),
    ]
    sections.append(("Adaptation: Signatures", "Adapt", rows))

    # -- Document Adaptations ----------------------------------------------
    rows = [
        ("A-DC-01", "A4 Marksheet -> JPEG max 200KB", "Dark wood table", "Normal tube light", "Compression loop, text readable"),
        ("A-DC-02", "A4 Marksheet -> PDF output", "Dark wood table", "Normal tube light", "PDF wrapping, single page"),
        ("A-DC-03", "A4 Marksheet -> greyscale colour mode", "Light wood table", "Normal tube light", "Coloured seals/stamps lost"),
        ("A-DC-04", "A4 Marksheet -> binary colour mode", "Light wood table", "Mixed lighting", "Sauvola threshold + uneven light"),
        ("A-DC-05", "Small ID card -> large target dims", "White A4 paper", "Normal tube light", "Upscale + quality preservation"),
        ("A-DC-06", "Document at min_kb boundary", "Dark wood table", "Normal tube light", "Rejection if too small"),
        ("A-DC-07", "Document at max_kb boundary", "Dark wood table", "Normal tube light", "Compression loop convergence"),
        ("A-DC-08", "PAN master (already cropped) -> re-adapt", "N/A (pre-processed)", "N/A", "No double-crop"),
        ("A-DC-09", "Encrypted master -> adapt", "N/A (encrypted)", "N/A", "Decrypt-enhance-adapt-encrypt roundtrip"),
        ("A-DC-10", "Marksheet -> OCR gate (min_confidence=0.8)", "Dark wood table", "Normal tube light", "Should pass clean doc"),
        ("A-DC-11", "Blurry marksheet -> OCR gate", "Dark wood table", "Low indoor light", "Should fail gate"),
        ("A-DC-12", "Handwritten cert -> OCR gate", "Light wood table", "Normal tube light", "Low confidence expected"),
        ("A-DC-13", "PAN card -> OCR skip", "Dark wood table", "Normal tube light", "OCR_SKIP_CATEGORIES honoured"),
    ]
    sections.append(("Adaptation: Documents", "Adapt", rows))

    # -- Cross-Cutting Edge Cases ------------------------------------------
    rows = [
        ("X-01", "Any document (HEIC/HEIF input from iPhone)", "Any surface", "Any lighting", "Format decode support"),
        ("X-02", "Any document (PNG with alpha channel)", "Any surface", "Any lighting", "Alpha -> white background"),
        ("X-03", "Scanned document (PDF input)", "N/A (digital)", "N/A", "Image extraction from PDF"),
        ("X-04", "Corrupted / truncated JPEG", "N/A", "N/A", "Graceful error, not crash"),
        ("X-05", "Zero-byte file", "N/A", "N/A", "Error handling"),
        ("X-06", "1x1 pixel image", "N/A", "N/A", "Early rejection"),
        ("X-07", "Very large image (20MP+)", "Any surface", "Any lighting", "Memory + timeout pressure"),
        ("X-08", "No EXIF data", "Any surface", "Any lighting", "Should not crash, assume upright"),
        ("X-09", "Wrong EXIF orientation tag", "Any surface", "Any lighting", "Rotation applied but content inverted"),
        ("X-10", "Encrypted input + encrypted output", "Any surface", "Any lighting", "AES-256-GCM roundtrip"),
        ("X-11", "Same image: master then re-adapt 5x", "Any surface", "Any lighting", "Quality must not degrade"),
        ("X-12", "Vision API timeout during Stage 0", "Any surface", "Any lighting", "Graceful fallback to Stage 1"),
    ]
    sections.append(("Cross-Cutting Edge Cases", "Both", rows))

    return sections


# ---------------------------------------------------------------------------
# Build the PDF
# ---------------------------------------------------------------------------

def build_checklist_table(section_rows):
    """Build a Table for one section."""
    hdr = styles["HeaderWhite"]
    header = [
        Paragraph("#", hdr),
        Paragraph("Document / Input", hdr),
        Paragraph("Surface / Background", hdr),
        Paragraph("Lighting Condition", hdr),
        Paragraph("Notes / Risk", hdr),
        Paragraph("Doc", hdr),
        Paragraph("Surface", hdr),
        Paragraph("Light", hdr),
        Paragraph("Photo", hdr),
        Paragraph("Master", hdr),
        Paragraph("Adapt", hdr),
        Paragraph("Pass", hdr),
    ]
    data = [header]

    for row_id, doc, surface, lighting, notes in section_rows:
        data.append([
            Paragraph(row_id, styles["CellText"]),
            Paragraph(doc, styles["CellText"]),
            Paragraph(surface, styles["CellText"]),
            Paragraph(lighting, styles["CellText"]),
            Paragraph(notes, styles["CellText"]),
            CHK, CHK, CHK, CHK, CHK, CHK, CHK,
        ])

    col_widths = [44, 124, 106, 98, 148, 38, 38, 38, 38, 38, 38, 38]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (5, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        # Checkbox columns: heavier border to form clear tick boxes
        ("BOX", (5, 1), (5, -1), 0.8, colors.HexColor("#444444")),
        ("BOX", (6, 1), (6, -1), 0.8, colors.HexColor("#444444")),
        ("BOX", (7, 1), (7, -1), 0.8, colors.HexColor("#444444")),
        ("BOX", (8, 1), (8, -1), 0.8, colors.HexColor("#444444")),
        ("BOX", (9, 1), (9, -1), 0.8, colors.HexColor("#444444")),
        ("BOX", (10, 1), (10, -1), 0.8, colors.HexColor("#444444")),
        ("BOX", (11, 1), (11, -1), 0.8, colors.HexColor("#444444")),
        ("INNERGRID", (5, 1), (-1, -1), 0.8, colors.HexColor("#444444")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_annexure():
    """Build the glossary / annexure section."""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("Annexure: Definitions & Glossary", styles["Title"]))
    elements.append(Spacer(1, 8))

    # -- Surfaces --
    elements.append(Paragraph("A. Surfaces & Backgrounds", styles["SectionHead"]))

    terms = [
        ("White A4 paper",
         "A standard 75-80 gsm white copier/printer paper (A4 size) placed flat under the document. "
         "This tests near-zero contrast boundaries where document edges blend into the paper beneath. "
         "The paper should be clean, unlined, and uncrumpled."),

        ("Light wood table",
         "A wooden surface with a light or honey-coloured finish (e.g., pine, birch, light oak). "
         "The warm beige tone closely matches the background colour of many Indian documents (PAN cards, old marksheets), "
         "creating a low-contrast boundary that challenges edge detection."),

        ("Dark wood table",
         "A wooden surface with a dark brown or walnut finish. Provides high contrast against light documents, "
         "but the dark tone can fool blob detection into treating the entire frame as the document area. "
         "Test with both matte and glossy finishes."),

        ("White bedsheet (flat)",
         "A plain white cotton or polyester bedsheet laid flat on a bed or surface, with the document placed on top. "
         "The fabric texture (weave pattern) can mimic paper grain and create micro-edges that confuse contour detection. "
         "The sheet should be smooth, not bunched or wrinkled."),

        ("Patterned bedsheet",
         "A bedsheet with visible printed patterns — floral, geometric, striped, or any repeating motif. "
         "The colours and lines in the pattern bleed into contour detection algorithms, creating competing edge candidates. "
         "Use a sheet with moderate-to-busy pattern density."),

        ("Dark / black paper",
         "A sheet of dark-coloured paper (black, dark grey, or deep navy) placed under the document. "
         "Creates maximum contrast but can invert the expected polarity in Otsu thresholding — the algorithm "
         "may treat the dark background as foreground. Tests the inverted-Otsu strategy (Strategy C)."),

        ("Red coloured paper",
         "A sheet of bright red or maroon paper. Stresses the saturation-based blob detection strategy (Strategy B) "
         "because the red hue creates strong saturation signals that compete with the document boundary. "
         "Use a solid, saturated red, not pastel."),

        ("Green coloured paper",
         "A sheet of bright green paper. Similar to red, tests saturation-based detection, but green specifically "
         "interferes with Aadhaar card designs (which use green tones) and certain certificate borders. "
         "Use a solid, saturated green."),

        ("Blue coloured paper",
         "A sheet of bright blue paper. Tests saturation strategy; particularly problematic for old-format Aadhaar cards "
         "(blue design) and blue-ink signatures. Ensures the pipeline doesn't merge document colour with background."),

        ("Glass surface",
         "A glass tabletop or glass-covered desk. The transparent/reflective surface creates specular highlights "
         "and reflections (of the camera, hands, ceiling lights) that appear as bright spots or false edges. "
         "The document may also show a faint double image from the glass reflection beneath."),

        ("Granite / marble counter",
         "A kitchen or bathroom countertop with a speckled or veined stone pattern. The natural grain of the stone "
         "adds high-frequency noise to edge detection. Veins in marble can appear as straight lines, creating "
         "false quad candidates in the contour detection stages."),

        ("Cluttered desk",
         "A desk or table surface with multiple objects visible — pens, phone, keys, papers, books, coffee cup, etc. "
         "Multiple rectangular objects create competing contour candidates. The pipeline must select the correct "
         "document among several plausible rectangular shapes. Include at least 3-4 non-document objects."),

        ("Hand-held (fingers visible)",
         "The document is held in one or both hands, with fingers visible at 1-4 edges. Skin-tone blobs near the "
         "document boundary can be incorrectly included in the crop region, or fingers can occlude document edges, "
         "preventing clean quad detection."),

        ("Lap / dark trousers",
         "The document rests on the user's lap (typically wearing dark trousers or a skirt). The fabric texture "
         "is curved (following the leg), which means the document is not perfectly flat, introducing a mild warp "
         "that challenges perspective correction. Dark fabric provides decent contrast but with texture noise."),

        ("Car dashboard",
         "The document is placed on a car dashboard or car seat. The surface is curved, often in direct sunlight "
         "through the windshield (causing overexposure), and the interior materials (leather, plastic, fabric) "
         "have varied textures. Tests extreme real-world conditions."),

        ("Floor tile (white/beige)",
         "The document is placed on a tiled floor. Grout lines between tiles create strong, regular straight lines "
         "that are detected as quad candidates by the contour detection algorithm. White/beige tiles also present "
         "a low-contrast boundary similar to white paper. Use tiles with clearly visible grout lines."),

        ("Clipboard / exam desk",
         "The document is clipped to a clipboard or lies on a standard examination desk with a lip or clip. "
         "The clipboard clip creates a shadow at the top edge, and the desk edge may partially occlude "
         "the document boundary. Common scenario for exam hall photography."),
    ]

    for term, defn in terms:
        elements.append(Paragraph(term, styles["AnnexTerm"]))
        elements.append(Paragraph(defn, styles["AnnexBody"]))
        elements.append(Spacer(1, 2))

    # -- Lighting --
    elements.append(Paragraph("B. Lighting Conditions", styles["SectionHead"]))

    terms = [
        ("Normal tube light",
         "Standard white fluorescent tube light (CFL or LED tube) in an indoor room, providing even, diffused "
         "illumination from above. Colour temperature approximately 4000-5000K (neutral white). No strong shadows "
         "or colour cast. This is the baseline 'good' condition."),

        ("Harsh direct sunlight",
         "Outdoors or near a window with strong, direct sunlight falling on the document. Causes overexposure "
         "(blown-out highlights), hard shadows with sharp edges, and potential lens flare. The bright areas "
         "may clip to pure white, losing document content. Test near a window between 10am-2pm."),

        ("Low indoor light",
         "A dimly lit room — single low-wattage bulb, distant light source, or evening without overhead lighting. "
         "The image will be underexposed (dark), with elevated sensor noise (grain) and potentially motion blur "
         "from longer exposure times. The camera may auto-raise ISO, increasing noise further."),

        ("Fluorescent tube (yellow/green cast)",
         "Older fluorescent tube lighting that emits a noticeable yellow or green colour cast. Common in government "
         "offices, schools, and older buildings. The colour shift affects skin tone accuracy in photos and can "
         "interfere with colour-based document detection. Colour temperature approximately 3000-3500K."),

        ("Mixed lighting (window + tube light)",
         "A room lit by both natural daylight from a window AND an artificial tube light. The two light sources "
         "have different colour temperatures (daylight ~5500K, tube ~4000K), creating uneven colour and exposure "
         "across the document — one side may be bluish-white (daylight) and the other yellowish (tube)."),

        ("Flash on (hotspot)",
         "The phone camera flash fires directly at the document. On laminated cards and glossy paper, this creates "
         "a bright specular hotspot (circular or oval white area) where the flash reflects back. The hotspot "
         "can wash out text and faces. On matte paper, flash creates a less severe but still uneven bright centre."),

        ("Shadow across document",
         "A shadow from the photographer's hand, phone, or a nearby object falls across part of the document, "
         "creating a visible dark band. The shadow edge can be misdetected as a document boundary. CLAHE must "
         "handle the two exposure zones (lit and shadowed) without over-brightening the shadow region."),

        ("Normal tube light + angle 15-30 degrees",
         "Standard tube lighting, but the photo is taken at a moderate angle (15-30 degrees from perpendicular) "
         "rather than straight-on. This introduces mild keystone distortion (trapezoidal warping) that the "
         "perspective correction stages must handle."),

        ("Studio lighting",
         "Professional or semi-professional studio lighting — typically two softbox lights or a ring light. "
         "Even, flattering illumination with no harsh shadows. Used for pre-framed studio passport photos. "
         "When this lighting is specified, the input is likely already well-exposed and should not be re-processed."),
    ]

    for term, defn in terms:
        elements.append(Paragraph(term, styles["AnnexTerm"]))
        elements.append(Paragraph(defn, styles["AnnexBody"]))
        elements.append(Spacer(1, 2))

    # -- Document Types --
    elements.append(Paragraph("C. Document Types", styles["SectionHead"]))

    terms = [
        ("Passport Photo",
         "A 35mm x 45mm (or 2x2 inch) portrait photograph of a person's face, taken against a plain background. "
         "Used for passports, visa applications, and exam forms. The pipeline uses Haar cascade face detection "
         "to locate the face and crop to standard passport proportions."),

        ("ID Photo",
         "A standard identification photograph, typically showing face and upper shoulders. May be larger or "
         "differently proportioned than a passport photo. Used for employee badges, student IDs, and some "
         "government forms."),

        ("Profile Photo",
         "A more informal portrait photo used for online profiles or less formal ID purposes. May not have "
         "a plain background and the person may not be facing perfectly forward."),

        ("Postcard Photo",
         "A 4x6 inch (102mm x 152mm) photo in landscape or portrait orientation. Typically a full-body or "
         "group photo. Processed through the document crop path rather than face detection."),

        ("Personal Signature",
         "A handwritten signature on paper. The pipeline binarizes this to black-on-white using Otsu thresholding. "
         "Can be written in any ink colour (blue, black, or other). The output is always binary (two-tone)."),

        ("PAN Card",
         "The Indian Permanent Account Number card issued by the Income Tax Department. A laminated, credit-card-sized "
         "card with a photo, PAN number, name, date of birth, and father's name. The newer 'e-PAN' variant is "
         "printed on plain A4 paper and is not laminated."),

        ("Aadhaar Card",
         "The 12-digit unique identification card issued by UIDAI. Available in laminated PVC card format, "
         "paper letter format, and the old blue-coloured format. The laminated version is highly reflective under flash."),

        ("Voter ID",
         "The Election Photo Identity Card (EPIC) issued by the Election Commission of India. Available as a "
         "booklet format (older) that opens to reveal the photo page, and a newer PVC card format. "
         "The booklet format is non-rectangular when open."),

        ("Driving Licence",
         "Issued by the Regional Transport Office (RTO). The new smart-card format is credit-card-sized PVC. "
         "The old format is a larger laminated paper document that is often yellowed with age."),

        ("Ration Card",
         "A government-issued document for subsidised food grains. Typically a multi-page folded paper document. "
         "Often creased, worn, and with fold lines that create false edges in contour detection."),

        ("Class 10 / Class 12 Marksheet",
         "Academic result documents issued by education boards (CBSE, ICSE, state boards). Typically A4-sized. "
         "Some are printed on special coloured security paper (pink, green, or blue). They may carry watermarks, "
         "holograms, or embossed seals."),

        ("Migration Certificate",
         "A certificate issued by a university or board when a student transfers. Usually smaller than A4 "
         "and may have a different aspect ratio than standard documents."),

        ("Caste / Category Certificate",
         "A certificate issued by a district magistrate or tehsildar confirming a person's caste or category "
         "(SC/ST/OBC). Often printed on non-judicial stamp paper, which has a textured, brownish surface. "
         "May carry multiple stamps and wet seals."),

        ("PwD Medical Certificate",
         "A disability certificate issued by a government medical board, certifying the nature and extent "
         "of disability. Often contains multiple doctor stamps, seals, and overlapping text that can lower "
         "OCR confidence."),

        ("Certificate with wet seal",
         "Any certificate bearing a wet rubber stamp (red or blue ink). The ink often bleeds slightly into "
         "the paper, creating soft-edged coloured regions that can interfere with binarization. "
         "The seal may overlap text content."),

        ("Certificate (thin paper, show-through)",
         "A certificate printed on thin paper (below 60 gsm) where text from the reverse side is faintly visible "
         "through the paper. This 'show-through' creates ghost text that confuses OCR and binarization."),

        ("Bank Statement (thermal print)",
         "A bank account statement printed on thermal paper from an ATM or bank passbook printer. Thermal prints "
         "fade rapidly (weeks to months), making text very low contrast — pale grey on white. "
         "The paper also yellows with age."),

        ("Utility Bill (glossy)",
         "An electricity, gas, or water bill printed on glossy paper with colour graphics (logos, bar charts, "
         "promotional material). The glossy surface creates specular reflections under flash. "
         "The colour printing can interfere with text extraction."),

        ("Rent Agreement",
         "A rental agreement document, often multi-page and stapled. Photographing a stapled document creates "
         "staple shadows and page curl at the binding edge. Individual pages may not lie flat."),

        ("Handwritten marksheet (rural format)",
         "Some rural or older school systems issue handwritten marksheets on plain paper. Low print quality, "
         "inconsistent layout, and handwritten entries make this one of the hardest documents for the pipeline."),
    ]

    for term, defn in terms:
        elements.append(Paragraph(term, styles["AnnexTerm"]))
        elements.append(Paragraph(defn, styles["AnnexBody"]))
        elements.append(Spacer(1, 2))

    # -- Special Conditions --
    elements.append(Paragraph("D. Special Conditions & Document States", styles["SectionHead"]))

    terms = [
        ("Pre-framed studio photo",
         "A passport or ID photo that has already been professionally cropped and formatted by a studio. "
         "The pipeline should detect that the image is already framed (via the framing guard) and skip "
         "document crop to avoid double-processing."),

        ("HEIC/HEIF input",
         "The default image format on iPhones (iOS 11+). High Efficiency Image Format uses HEVC compression. "
         "The pipeline must be able to decode this format before any processing begins."),

        ("PNG with alpha channel",
         "A PNG image with transparency (alpha channel). Before processing, the transparent regions must be "
         "composited onto a white background to prevent artefacts in edge detection and binarization."),

        ("Encrypted input",
         "An image that has been encrypted using AES-256-GCM before upload. The pipeline must decrypt it "
         "using the provided SEK (Session Encryption Key) before processing, and may need to re-encrypt "
         "the output."),

        ("Folded / creased document",
         "A document that has been folded (once or multiple times) and then unfolded for photography. "
         "The fold lines appear as strong straight edges that can be detected as document boundaries."),

        ("Laminated document",
         "A document sealed in plastic lamination. Under any direct light source (especially flash), "
         "the lamination creates specular reflections. The edges of the lamination pouch may extend "
         "beyond the document itself."),

        ("Old / yellowed document",
         "A document that has aged and the paper has turned yellow or brown. This colour cast must be "
         "accounted for in binarization (so that the yellowed paper is treated as 'white') and in "
         "greyscale conversion."),

        ("Angled shot (15-30 degrees)",
         "The camera is held at a moderate angle to the document surface, rather than perpendicular. "
         "Introduces trapezoidal (keystone) distortion that the perspective warp stages must correct."),

        ("Steep angle (40-60 degrees)",
         "An extreme camera angle that causes severe keystone distortion. The far edge of the document "
         "appears much narrower than the near edge. Tests the limits of the perspective correction algorithm."),
    ]

    for term, defn in terms:
        elements.append(Paragraph(term, styles["AnnexTerm"]))
        elements.append(Paragraph(defn, styles["AnnexBody"]))
        elements.append(Spacer(1, 2))

    # -- Pipeline Terminology --
    elements.append(Paragraph("E. Pipeline Terminology", styles["SectionHead"]))

    terms = [
        ("Master Creation",
         "The first processing mode. Takes a raw uploaded photo and produces a high-quality 'master' version "
         "that preserves maximum detail under a 2000KB size limit. The master is the archival version that all "
         "future adaptations are derived from. Output can be JPEG, JPEG2000, or MRC-PDF."),

        ("Adaptation",
         "The second processing mode. Takes a master (or fresh upload) and transforms it to meet a specific "
         "portal or exam form schema — enforcing exact dimensions, DPI, colour mode, file size limits, and "
         "output format. This is what gets submitted to the target portal."),

        ("GUARD-001",
         "A quality gate that skips NLM (Non-Local Means) denoising and CLAHE (Contrast-Limited Adaptive "
         "Histogram Equalisation) when the input image quality score is above 0.75 (75%). This prevents "
         "over-processing of images that are already sharp and well-exposed."),

        ("Framing guard",
         "A three-check system that detects whether a photo has already been professionally framed "
         "(studio passport photo). Checks border intensity standard deviation, centre/border contrast ratio, "
         "and border texture (Laplacian variance). If all three pass, document crop is skipped."),

        ("OCR confidence gate",
         "For text documents, the pipeline runs OCR (Optical Character Recognition) and checks the confidence "
         "score against a minimum threshold. If confidence is too low (e.g., blurry text), the adaptation is "
         "rejected rather than producing an unreadable output."),

        ("Otsu binarization",
         "An automatic thresholding algorithm that converts a greyscale image to pure black and white. "
         "It finds the optimal threshold that minimises intra-class variance. Used for signatures."),

        ("Sauvola binarization",
         "An adaptive thresholding algorithm that computes a different threshold for each pixel based on "
         "the local neighbourhood mean and standard deviation. Better than Otsu for documents with "
         "uneven lighting. Used for binary colour mode adaptation."),

        ("Perspective warp",
         "A geometric transformation that corrects the trapezoidal distortion caused by photographing "
         "a flat document at an angle. Maps the four detected corners of the document to a perfect rectangle."),

        ("Haar cascade (face detection)",
         "A classical computer vision algorithm for detecting faces in images. Uses a cascade of increasingly "
         "complex feature classifiers trained on face images. Runs locally (no API call), making it fast. "
         "Used for portrait photo cropping."),

        ("Letterbox fit",
         "A resizing strategy that scales the image to fit within the target dimensions while preserving "
         "the original aspect ratio, then fills the remaining space with white padding. "
         "Prevents distortion of faces and text."),

        ("Stretch fit",
         "A resizing strategy that scales the image to exactly match the target dimensions, regardless of "
         "the original aspect ratio. May distort content. Some portals require this."),
    ]

    for term, defn in terms:
        elements.append(Paragraph(term, styles["AnnexTerm"]))
        elements.append(Paragraph(defn, styles["AnnexBody"]))
        elements.append(Spacer(1, 2))

    return elements


def build_pdf():
    """Generate the full PDF."""
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=PAGE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Rythmiq Transformation Pipeline - Edge Case Test Checklist",
        author="Rythmiq Engineering",
    )

    story = []

    # Title page
    story.append(Spacer(1, 40))
    story.append(Paragraph("Transformation Pipeline", styles["TitleStyle"]))
    story.append(Paragraph("Edge Case Test Checklist", styles["TitleStyle"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Comprehensive sourcing and testing checklist for embarrassment-proof ship readiness. March 2026.",
        styles["SubtitleStyle"],
    ))
    story.append(Spacer(1, 12))

    # Legend
    legend_data = [
        [Paragraph("<b>Column</b>", styles["CellBold"]), Paragraph("<b>Meaning</b>", styles["CellBold"])],
        ["Doc Sourced", "The physical document (PAN card, marksheet, etc.) has been obtained"],
        ["Surface Sourced", "The background surface (wood table, bedsheet, etc.) is available for photography"],
        ["Lighting Sourced", "The lighting setup (tube light, flash, sunlight position, etc.) is arranged"],
        ["Photo Taken", "The test photo has been captured with the document + surface + lighting combination"],
        ["Master Tested", "The master creation job has been run and the output visually inspected"],
        ["Adapt Tested", "The adaptation job has been run against all relevant schemas and output verified"],
        ["Pass", "The entire test case passes acceptance criteria"],
    ]
    legend = Table(legend_data, colWidths=[100, 660])
    legend.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(legend)
    story.append(PageBreak())

    # Sections
    sections = _rows()
    for title, job_type, rows in sections:
        story.append(Paragraph(f"{title}  <font size=9 color='grey'>[{job_type}]</font>", styles["SectionHead"]))
        story.append(Spacer(1, 4))
        story.append(build_checklist_table(rows))
        story.append(Spacer(1, 8))
        story.append(PageBreak())

    # Annexure
    story.extend(build_annexure())

    doc.build(story)
    print(f"PDF generated: {OUTPUT}")
    print(f"Total test cases: {sum(len(r) for _, _, r in sections)}")


if __name__ == "__main__":
    build_pdf()
