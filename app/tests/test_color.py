from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from app.artwork.analyzer import ArtworkAnalyzer, load_image
from app.artwork.palette import delta_e, to_lab, to_rgb
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


def test_image_validation():
    with pytest.raises(Exception):
        load_image(b"not an image")
    with pytest.raises(ValueError):
        load_image(b"x" * (20 * 1024 * 1024 + 1))
