from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db import Persistence
from app.main import create_app
from app.tests.test_multitv import headers


async def test_fixed_color_applies_to_each_artwork_without_thumbnail(system):
    db, c, w = system
    w.save_settings(
        {
            "automation": True,
            "color_mode": "fixed",
            "fixed_color": "warm",
            "preferred_family": "shadowbox",
            "threshold": 100,
            "cooldown": 3600,
        }
    )
    w.provider.acquire = AsyncMock(return_value=None)
    db.put("overrides", c.current, {"mode": "force", "matte": "modern_black"})
    await w.tick()
    assert c.matte == "shadowbox_warm"
    count = len(c.writes)
    await w.tick()
    assert len(c.writes) == count
    await c.select_artwork("MY-DEMO-1")
    c.matte = "none"
    await w.tick()
    assert c.matte == "shadowbox_warm"
    assert len(c.writes) == count + 1


async def test_fixed_color_respects_pause_never_modify_and_artmode(system):
    db, c, w = system
    w.save_settings({"color_mode": "fixed", "fixed_color": "warm", "preferred_family": "shadowbox"})
    await w.tick()
    assert not c.writes
    w.save_settings({"automation": True})
    db.put("overrides", c.current, {"mode": "never"})
    await w.tick()
    assert not c.writes
    db.put("overrides", c.current, {"mode": "automatic"})
    c.get_art_mode = AsyncMock(return_value="off")
    await w.tick()
    assert not c.writes
    with pytest.raises(ValueError, match="Fixed color"):
        await w.apply_choice(c.current, "modern_black")


async def test_fixed_color_changes_immediately_and_unavailable_never_falls_back(system):
    db, c, w = system
    w.save_settings(
        {
            "automation": True,
            "color_mode": "fixed",
            "fixed_color": "warm",
            "preferred_family": "shadowbox",
            "cooldown": 3600,
        }
    )
    await w.tick()
    w.save_settings({"fixed_color": "polar"})
    await w.tick()
    assert c.matte == "shadowbox_polar"
    count = len(c.writes)
    w.save_settings({"fixed_color": "invented"})
    await w.tick()
    assert len(c.writes) == count
    assert "unavailable" in w.state["message"]


async def test_finish_is_optional_and_bounded(system):
    db, c, w = system
    await w.tick(force=True)
    art = w.state["artwork"]["analysis"]
    assert all(
        r["finish_adjustment"] == 0 for r in w.engine.score(art, w.catalog.all(), w.settings)
    )
    for finish in ("white", "black", "light_wood", "dark_wood", "warm_metal", "cool_metal"):
        ranks = w.engine.score(art, w.catalog.all(), {**w.settings, "frame_finish": finish})
        assert all(-2 <= r["finish_adjustment"] <= 2 for r in ranks)


def test_removed_room_apis_and_safe_settings_migration(tmp_path):
    db = Persistence(tmp_path)
    db.put(
        "config",
        "settings",
        {
            "requires_reselect": True,
            "use_room": True,
            "latitude": 35,
            "weights": {
                "edge": 30,
                "palette": 15,
                "wall": 25,
                "room": 10,
                "lightness": 10,
                "neutral": 10,
            },
        },
    )
    db.put("rooms", "night", {"photo": "night.png"})
    db.close()
    (tmp_path / "room").mkdir()
    (tmp_path / "room" / "night.png").write_bytes(b"private")
    with TestClient(create_app(tmp_path, mock=True)) as c:
        h = headers(c)
        state = c.get("/api/state").json()
        assert "rooms" not in state and "calibration" not in state
        assert "use_room" not in state["settings"] and "latitude" not in state["settings"]
        assert state["settings"]["requires_reselect"]
        assert set(state["settings"]["weights"]) == {"edge", "palette", "lightness", "neutral"}
        for path in (
            "/room",
            "/calibration-pattern.png",
            "/api/locations",
            "/media/room/night.png",
        ):
            assert c.get(path).status_code == 404
        assert c.post("/api/room/night/snapshot", headers=h).status_code in (404, 405)
        assert c.post("/api/settings", headers=h, json={"use_room": True}).status_code == 422
        assert (
            c.post(
                "/api/settings", headers=h, json={"color_mode": "fixed", "fixed_color": "invented"}
            ).status_code
            == 400
        )
        assert c.post(
            "/api/settings",
            headers=h,
            json={
                "color_mode": "fixed",
                "fixed_color": "warm",
                "preferred_family": "shadowbox",
                "frame_finish": "light_wood",
            },
        ).is_success
    with TestClient(create_app(tmp_path, mock=True)) as c:
        s = c.get("/api/state").json()["settings"]
        assert s["color_mode"] == "fixed" and s["fixed_color"] == "warm"
        assert s["frame_finish"] == "light_wood"
    assert (tmp_path / "room" / "night.png").read_bytes() == b"private"
