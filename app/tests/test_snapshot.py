from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.artwork.analyzer import load_image
from app.db import Persistence
from app.room.calibration import RoomCalibrationService
from app.room.snapshot import detect_tv, wall_near_tv
from app.samsung.mock import sample


def room_snapshot():
    image = Image.new("RGB", (1280, 1000), (190, 179, 161))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1280, 160), fill=(215, 210, 200))
    draw.rectangle((0, 850, 1280, 1000), fill=(95, 85, 72))
    draw.rectangle((320, 260, 960, 620), fill=(30, 28, 24))
    image.paste(load_image(sample()).resize((624, 344)), (328, 268))
    draw.rectangle((280, 650, 1000, 710), fill=(75, 55, 40))
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def test_ordinary_photo_detects_tv():
    corners, confidence = detect_tv(np.array(load_image(room_snapshot())))
    assert confidence > 0.5
    assert np.allclose(corners, [[320, 260], [960, 260], [960, 620], [320, 620]], atol=12)


def test_wall_sampling_avoids_screen_and_mantel():
    mask = wall_near_tv(
        (1000, 1280, 3), np.float32([[320, 260], [960, 260], [960, 620], [320, 620]])
    )
    assert mask[220, 640]
    assert not mask[400, 640]
    assert not mask[670, 640]


def test_snapshot_profile_does_not_claim_color_correction(tmp_path):
    db = Persistence(tmp_path)
    service = RoomCalibrationService(db)
    profile = service.snapshot(room_snapshot(), "day")
    assert profile["source"] == "snapshot"
    assert profile["color_corrected"] is False
    assert profile["reference_error_delta_e"] is None
    assert profile["ambient_cast"] is None
    assert 0 < profile["confidence"] <= 0.60
    assert (tmp_path / "room" / profile["detection"]).exists()
    remasked = service.remask("day")
    assert remasked["source"] == "snapshot"
    assert remasked["color_corrected"] is False
    db.close()


def test_corner_fallback_and_validation(tmp_path):
    db = Persistence(tmp_path)
    service = RoomCalibrationService(db)
    points = [
        [320 / 1280, 260 / 1000],
        [960 / 1280, 260 / 1000],
        [960 / 1280, 620 / 1000],
        [320 / 1280, 620 / 1000],
    ]
    assert service.snapshot(room_snapshot(), "night", points)["source"] == "snapshot"
    with pytest.raises(ValueError):
        service.snapshot(room_snapshot(), "day", [[2, 2]] * 4)
    db.close()


def test_unrelated_image_requires_corner_confirmation():
    with pytest.raises(ValueError, match="corners"):
        detect_tv(np.full((600, 800, 3), 150, np.uint8))
