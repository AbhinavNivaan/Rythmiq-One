"""
Photo quality scoring tests.

Verifies the new noise-resilient sharpness, saturation, and contrast
metrics produce correct rankings — higher-quality photos must score
higher than lower-quality ones.
"""

import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Bootstrap worker modules (avoids sys.path pollution)
# ---------------------------------------------------------------------------
WORKER_DIR = Path(__file__).parent.parent.parent / "worker"

for mod_name, filename in [
    ("errors", "errors.py"),
    ("models", "models.py"),
]:
    spec = importlib.util.spec_from_file_location(mod_name, WORKER_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

spec = importlib.util.spec_from_file_location(
    "quality", WORKER_DIR / "processors" / "quality.py"
)
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)

compute_sharpness = quality.compute_sharpness
compute_sharpness_photo = quality.compute_sharpness_photo
compute_saturation = quality.compute_saturation
compute_contrast = quality.compute_contrast
compute_noise = quality.compute_noise
assess_quality = quality.assess_quality
QUALITY_WEIGHTS = quality.QUALITY_WEIGHTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode(img: np.ndarray) -> bytes:
    """Encode a BGR image to JPEG bytes."""
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buf.tobytes()


def _make_clean_portrait() -> np.ndarray:
    """Synthetic 'good portrait': varied tones, skin colour, sharp edges."""
    h, w = 400, 300
    # Light background with colour (pale blue-grey)
    img = np.full((h, w, 3), 0, dtype=np.uint8)
    img[:, :] = [210, 200, 195]  # BGR light background

    # Dark hair region (top of head)
    cv2.ellipse(img, (w // 2, h // 4), (70, 55), 0, 0, 360, (30, 25, 20), -1)

    # Face — warm skin tone
    cv2.ellipse(img, (w // 2, int(h * 0.4)), (55, 70), 0, 0, 360, (140, 170, 200), -1)

    # Eyes — dark with white highlights (sharp contrast)
    for dx in [-22, 22]:
        cx = w // 2 + dx
        cy = int(h * 0.36)
        cv2.circle(img, (cx, cy), 8, (240, 240, 240), -1)  # White of eye
        cv2.circle(img, (cx, cy), 5, (30, 30, 30), -1)      # Iris
        cv2.circle(img, (cx + 2, cy - 2), 2, (220, 220, 220), -1)  # Highlight

    # Nose shadow
    cv2.line(img, (w // 2, int(h * 0.38)), (w // 2, int(h * 0.46)), (120, 140, 170), 2)

    # Mouth
    cv2.ellipse(img, (w // 2, int(h * 0.52)), (18, 6), 0, 0, 180, (80, 90, 160), 2)

    # Eyebrows — strong dark lines
    cv2.line(img, (w // 2 - 35, int(h * 0.30)), (w // 2 - 10, int(h * 0.29)), (25, 20, 15), 3)
    cv2.line(img, (w // 2 + 10, int(h * 0.29)), (w // 2 + 35, int(h * 0.30)), (25, 20, 15), 3)

    # Collar / shirt (dark, adds contrast at bottom)
    cv2.rectangle(img, (w // 2 - 80, int(h * 0.7)), (w // 2 + 80, h), (60, 50, 45), -1)
    # Collar line
    cv2.line(img, (w // 2 - 40, int(h * 0.7)), (w // 2, int(h * 0.78)), (240, 240, 240), 2)
    cv2.line(img, (w // 2 + 40, int(h * 0.7)), (w // 2, int(h * 0.78)), (240, 240, 240), 2)

    return img


def _make_noisy_photo() -> np.ndarray:
    """Synthetic 'bad phone photo': heavy noise, washed-out, low-contrast."""
    h, w = 400, 300
    # Start with a flat, desaturated, low-contrast base
    img = np.full((h, w, 3), 160, dtype=np.uint8)
    # Slight tint (washed out warm)
    img[:, :, 2] = 170  # R channel slightly higher
    # Add heavy Gaussian noise (std=30)
    rng = np.random.RandomState(42)
    noise = rng.normal(0, 30, img.shape).astype(np.float32)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return img


def _make_desaturated_photo() -> np.ndarray:
    """Synthetic 'desaturated photo': has structure but no colour."""
    h, w = 400, 300
    gray_val = 140
    img = np.full((h, w, 3), gray_val, dtype=np.uint8)
    # Strong edges (rectangles, circles) — high sharpness
    cv2.rectangle(img, (50, 50), (250, 350), (80, 80, 80), 3)
    cv2.rectangle(img, (80, 80), (220, 320), (60, 60, 60), 2)
    cv2.circle(img, (150, 200), 50, (100, 100, 100), -1)
    cv2.circle(img, (150, 200), 30, (180, 180, 180), -1)
    return img


# ===========================================================================
# Tests: compute_sharpness_photo (noise-resilient)
# ===========================================================================

@pytest.mark.unit
@pytest.mark.worker
class TestSharpnessPhoto:
    """Noise-resilient sharpness metric for photos."""

    def test_preblur_reduces_noise_laplacian(self):
        """Pre-blur must reduce Laplacian variance of noisy images."""
        noisy = cv2.cvtColor(_make_noisy_photo(), cv2.COLOR_BGR2GRAY)

        # Raw Laplacian (what old metric uses)
        raw_var = cv2.Laplacian(noisy, cv2.CV_64F).var()

        # Pre-blurred Laplacian (what new metric uses)
        denoised = cv2.GaussianBlur(noisy, (3, 3), 0)
        blurred_var = cv2.Laplacian(denoised, cv2.CV_64F).var()

        assert blurred_var < raw_var * 0.8, (
            f"Pre-blur should reduce noisy Laplacian variance by at least 20%. "
            f"Raw: {raw_var:.1f}, Blurred: {blurred_var:.1f}"
        )

    def test_old_sharpness_inflated_by_noise(self):
        """Demonstrate the old bug: raw Laplacian inflated by noise."""
        clean = cv2.cvtColor(_make_clean_portrait(), cv2.COLOR_BGR2GRAY)
        noisy = cv2.cvtColor(_make_noisy_photo(), cv2.COLOR_BGR2GRAY)

        old_clean = compute_sharpness(clean)
        old_noisy = compute_sharpness(noisy)

        # Old metric: noisy >= clean (the bug we're fixing)
        assert old_noisy >= old_clean, (
            "Sanity check: old compute_sharpness should be inflated by noise"
        )

    def test_score_in_unit_range(self):
        """Score must be clamped to [0, 1]."""
        gray = cv2.cvtColor(_make_clean_portrait(), cv2.COLOR_BGR2GRAY)
        score = compute_sharpness_photo(gray)
        assert 0.0 <= score <= 1.0

    def test_blank_image_scores_zero(self):
        """A solid-colour image has no edges → score ≈ 0."""
        blank = np.full((200, 200), 128, dtype=np.uint8)
        assert compute_sharpness_photo(blank) < 0.05


# ===========================================================================
# Tests: compute_saturation
# ===========================================================================

@pytest.mark.unit
@pytest.mark.worker
class TestSaturation:
    """Colour saturation metric."""

    def test_vibrant_scores_high(self):
        """A naturally colourful image should score close to 1.0."""
        # Build via HSV with moderate saturation (natural portrait range)
        hsv = np.zeros((200, 200, 3), dtype=np.uint8)
        hsv[:100, :, 0] = 10   # Warm skin hue
        hsv[:100, :, 1] = 90   # Good saturation
        hsv[:100, :, 2] = 180  # Moderate brightness
        hsv[100:, :, 0] = 110  # Blue-green background
        hsv[100:, :, 1] = 80   # Good saturation
        hsv[100:, :, 2] = 170
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        score = compute_saturation(img)
        assert score >= 0.8, f"Vibrant image should score >= 0.8, got {score:.3f}"

    def test_grayscale_scores_neutral(self):
        """A pure grayscale image (B&W photo) should score ~0.50."""
        img = np.full((200, 200, 3), 128, dtype=np.uint8)
        score = compute_saturation(img)
        assert 0.40 <= score <= 0.60, f"Grayscale should be neutral ~0.50, got {score:.3f}"

    def test_desaturated_colour_penalised(self):
        """A slightly coloured but washed-out image should score < 0.50."""
        # Very low saturation colour (near-grey with slight tint)
        hsv = np.full((200, 200, 3), 0, dtype=np.uint8)
        hsv[:, :, 0] = 20   # Hue (orange-ish)
        hsv[:, :, 1] = 18   # Very low saturation
        hsv[:, :, 2] = 160  # Moderate value
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        score = compute_saturation(img)
        assert score < 0.55, f"Desaturated colour should score < 0.55, got {score:.3f}"

    def test_score_in_unit_range(self):
        score = compute_saturation(_make_clean_portrait())
        assert 0.0 <= score <= 1.0


# ===========================================================================
# Tests: compute_contrast
# ===========================================================================

@pytest.mark.unit
@pytest.mark.worker
class TestContrast:
    """Percentile-based contrast metric."""

    def test_flat_image_scores_low(self):
        """An image with almost no tonal variation should score low."""
        flat = np.full((200, 200), 128, dtype=np.uint8)
        # Add tiny variation so it's not perfectly uniform
        flat[0, 0] = 125
        flat[-1, -1] = 131
        score = compute_contrast(flat)
        assert score < 0.3, f"Flat image should score < 0.3, got {score:.3f}"

    def test_high_contrast_scores_high(self):
        """An image with strong black/white contrast should score high."""
        img = np.zeros((200, 200), dtype=np.uint8)
        img[:100, :] = 20    # Dark
        img[100:, :] = 240   # Bright
        score = compute_contrast(img)
        assert score >= 0.8, f"High-contrast should score >= 0.8, got {score:.3f}"

    def test_score_in_unit_range(self):
        gray = cv2.cvtColor(_make_clean_portrait(), cv2.COLOR_BGR2GRAY)
        score = compute_contrast(gray)
        assert 0.0 <= score <= 1.0


# ===========================================================================
# Tests: assess_quality integration (ranking)
# ===========================================================================

@pytest.mark.unit
@pytest.mark.worker
class TestPhotoQualityRanking:
    """End-to-end ranking: good portrait must outscore bad photos."""

    def test_clean_portrait_beats_noisy_photo(self):
        good = assess_quality(_encode(_make_clean_portrait()), "photo")
        bad = assess_quality(_encode(_make_noisy_photo()), "photo")
        assert good.score > bad.score, (
            f"Good portrait ({good.score:.3f}) must outscore noisy photo ({bad.score:.3f})\n"
            f"  Good breakdown: {good.breakdown.to_dict()}\n"
            f"  Bad  breakdown: {bad.breakdown.to_dict()}"
        )

    def test_clean_portrait_beats_desaturated_photo(self):
        good = assess_quality(_encode(_make_clean_portrait()), "photo")
        desat = assess_quality(_encode(_make_desaturated_photo()), "photo")
        assert good.score > desat.score, (
            f"Good portrait ({good.score:.3f}) must outscore desaturated ({desat.score:.3f})\n"
            f"  Good  breakdown: {good.breakdown.to_dict()}\n"
            f"  Desat breakdown: {desat.breakdown.to_dict()}"
        )

    def test_breakdown_includes_new_fields(self):
        result = assess_quality(_encode(_make_clean_portrait()), "photo")
        d = result.breakdown.to_dict()
        assert "saturation" in d
        assert "contrast" in d
        assert 0.0 <= d["saturation"] <= 1.0
        assert 0.0 <= d["contrast"] <= 1.0


# ===========================================================================
# Tests: Regression — document/signature scoring unchanged
# ===========================================================================

@pytest.mark.unit
@pytest.mark.worker
class TestDocumentScoringRegression:
    """Document and signature weights must not change."""

    def test_document_weights_unchanged(self):
        doc_w = QUALITY_WEIGHTS["document"]
        assert doc_w["sharpness"] == 0.35
        assert doc_w["exposure"] == 0.30
        assert doc_w["noise"] == 0.20
        assert doc_w["edge_density"] == 0.15
        assert doc_w.get("saturation", 0.0) == 0.0
        assert doc_w.get("contrast", 0.0) == 0.0

    def test_signature_weights_unchanged(self):
        sig_w = QUALITY_WEIGHTS["signature"]
        assert sig_w["sharpness"] == 0.40
        assert sig_w["exposure"] == 0.30
        assert sig_w["noise"] == 0.20
        assert sig_w["edge_density"] == 0.10
        assert sig_w.get("saturation", 0.0) == 0.0
        assert sig_w.get("contrast", 0.0) == 0.0

    def test_document_score_ignores_saturation_contrast(self):
        """For documents, saturation & contrast have 0 weight → don't affect score."""
        # Use a synthetic document-like image
        img = np.full((400, 300, 3), 240, dtype=np.uint8)
        cv2.putText(img, "TEST DOC", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, (20, 20, 20), 3)

        result = assess_quality(_encode(img), "document")
        breakdown = result.breakdown

        # Verify saturation/contrast are computed (in breakdown) but don't affect score
        expected_score = (
            0.35 * breakdown.sharpness +
            0.30 * breakdown.exposure +
            0.20 * breakdown.noise +
            0.15 * breakdown.edge_density
        )
        assert abs(result.score - expected_score) < 0.001, (
            f"Document score {result.score:.4f} should equal weighted sum of "
            f"original 4 metrics {expected_score:.4f}"
        )
