from io import BytesIO

import cv2
import numpy as np
import pytest
from PIL import Image

from app.artwork.analyzer import ArtworkAnalyzer, load_image
from app.artwork.palette import delta_e, to_lab, to_rgb
from app.room.calibration import (
    RoomCalibrationService,
    apply_correction,
    detect_screen,
    fit_correction,
)
from app.room.masking import automatic_mask
from app.room.pattern import PATCHES, generate
from app.room.profiles import quick_profile
from app.samsung.mock import sample


def test_rgb_lab_reference():
    assert np.allclose(to_lab([255, 255, 255]), [100, 0, 0], atol=0.02)
    assert np.allclose(to_lab([255, 0, 0]), [53.2408, 80.0925, 67.2032], atol=0.02)
    assert np.allclose(to_lab([0, 0, 0]), [0, 0, 0])


@pytest.mark.parametrize("rgb", [[230, 200, 160], [0, 100, 255], [128, 128, 128]])
def test_roundtrip(rgb):
    assert np.allclose(to_rgb(to_lab(rgb)), rgb, atol=1)


def test_ciede2000_published_reference():
    # Sharma et al. supplemental test pair 1, expected Delta E 2.0425.
    assert float(delta_e([50, 2.6772, -79.7751], [50, 0, -82.7485])) == pytest.approx(
        2.0425, abs=0.0001
    )


def test_analysis_palette():
    result = ArtworkAnalyzer().analyze(sample())
    assert 1 <= len(result["palette"]) <= 5
    assert sum(p["percentage"] for p in result["palette"]) == pytest.approx(100, abs=0.03)
    assert result["aspect"] == pytest.approx(16 / 9)


def test_perimeter_is_not_center():
    im = Image.new("RGB", (400, 400), (255, 0, 0))
    im.paste(Image.new("RGB", (280, 280), (0, 0, 255)), (60, 60))
    out = BytesIO()
    im.save(out, "PNG")
    result = ArtworkAnalyzer().analyze(out.getvalue())
    assert result["edge_lab"][2] > 60
    assert result["average_lab"][2] < 10


def test_pattern_detection():
    rgb = np.array(load_image(generate()))
    corners, plane = detect_screen(rgb)
    assert np.allclose(corners, [[0, 0], [3839, 0], [3839, 2159], [0, 2159]], atol=2)
    assert plane.shape == (2160, 3840, 3)


def test_pattern_perspective():
    rgb = np.array(load_image(generate()))
    transform = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [3839, 0], [3839, 2159], [0, 2159]]),
        np.float32([[180, 180], [1380, 120], [1450, 860], [130, 900]]),
    )
    photo = cv2.warpPerspective(rgb, transform, (1600, 1000), borderValue=(200, 190, 175))
    corners, _ = detect_screen(photo)
    assert np.allclose(corners, [[180, 180], [1380, 120], [1450, 860], [130, 900]], atol=8)


def test_pattern_rejects_unrelated_image():
    with pytest.raises(ValueError, match="markers"):
        detect_screen(np.zeros((600, 800, 3), np.uint8))


def test_wall_mask_excludes_tv():
    mask = automatic_mask(
        (1000, 1600, 3), np.array([[400, 300], [1200, 300], [1200, 700], [400, 700]])
    )
    assert not mask[500, 800]
    assert mask[250, 800]
    assert not mask[0, 0]


def test_color_correction_known_transform():
    expected = np.array(PATCHES, dtype=float)
    observed = expected * [0.83, 0.90, 0.95] + [8, 5, 2]
    matrix, error = fit_correction(observed, expected)
    restored = apply_correction(observed, matrix)
    assert np.mean(np.abs(restored - expected)) < 1
    assert error < 1


def test_room_profile_and_mask_edit(tmp_path):
    from app.db import Persistence

    db = Persistence(tmp_path)
    service = RoomCalibrationService(db)
    photo = Image.new("RGB", (1920, 1280), (200, 185, 165))
    pattern = load_image(generate())
    pattern.thumbnail((1280, 720))
    photo.paste(pattern, (320, 280))
    output = BytesIO()
    photo.save(output, "PNG")
    result = service.process(output.getvalue(), "day")
    assert 0 < result["confidence"] <= 0.9
    assert result["wall_lab"][2] > 0
    assert result["source"] == "guided"
    assert result["photo"] == "day.png"
    black = BytesIO()
    Image.new("RGB", photo.size, "black").save(black, "PNG")
    with pytest.raises(ValueError, match="500"):
        service.remask("day", black.getvalue())
    db.close()


def test_quick_profile():
    r = quick_profile("#d0c4ae")
    assert r["source"] == "manual"
    assert r["confidence"] == 0.35
    assert "Warm" in r["descriptors"]


def test_image_validation():
    with pytest.raises(Exception):
        load_image(b"not an image")
    with pytest.raises(ValueError):
        load_image(b"x" * (20 * 1024 * 1024 + 1))
