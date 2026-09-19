from io import BytesIO

import numpy as np
from PIL import Image, ImageCms, ImageDraw

from app.artwork.analyzer import ArtworkAnalyzer, load_image
from app.artwork.palette import to_lab
from app.config import DEFAULTS
from app.db import Persistence
from app.matte.catalog import MatteCatalog
from app.matte.scoring import MatteRecommendationEngine
from app.room.profiles import quick_profile
from app.room.surroundings import surrounding_palette
from app.samsung.mock import MockFrameClient, sample


def test_embedded_profile_is_converted_and_metadata_removed():
    image = Image.new("RGB", (20, 20), (200, 100, 50))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    output = BytesIO()
    image.save(output, "PNG", icc_profile=profile)
    result = load_image(output.getvalue())
    assert np.allclose(np.array(result)[0, 0], [200, 100, 50], atol=1)
    assert not result.info


def test_tv_colors_never_become_room_accents():
    image = Image.new("RGB", (1000, 800), (180, 170, 150))
    draw = ImageDraw.Draw(image)
    draw.rectangle((210, 530, 270, 650), fill=(210, 100, 30))
    corners = np.float32([[300, 200], [800, 200], [800, 480], [300, 480]])
    matrix = np.vstack([np.eye(3), np.zeros(3)])
    results = []
    for color in [(255, 0, 0), (0, 0, 255)]:
        draw.rectangle((300, 200, 800, 480), fill=color)
        results.append(
            surrounding_palette(np.array(image), corners, to_lab([180, 170, 150]), matrix)
        )
    assert results[0] == results[1]
    assert results[0]["accent_palette"]


async def test_accent_influence_is_small_and_can_be_disabled(tmp_path):
    db = Persistence(tmp_path)
    catalog = MatteCatalog(db)
    catalog.refresh(await MockFrameClient().get_available_mattes())
    art = ArtworkAnalyzer().analyze(sample())
    room = quick_profile("#d8c5aa")
    room["accent_palette"] = [{"lab": to_lab([230, 60, 20]).tolist(), "percentage": 100}]
    engine = MatteRecommendationEngine()
    enabled = engine.score(art, room, catalog.all(), DEFAULTS)
    disabled = engine.score(art, room, catalog.all(), {**DEFAULTS, "accent_influence": 0})
    by_id = {r["matte"]["id"]: r for r in disabled}
    assert all(abs(r["score"] - by_id[r["matte"]["id"]]["score"]) <= 2.51 for r in enabled)
    assert all(r["accent_adjustment"] == 0 for r in disabled)
    assert enabled[0]["matte"]["color"] in ("polar", "neutral", "warm", "black")
    db.close()
