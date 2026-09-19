import copy
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.artwork.analyzer import ArtworkAnalyzer
from app.config import DEFAULTS
from app.db import Persistence
from app.matte.catalog import MatteCatalog
from app.matte.scoring import MatteRecommendationEngine
from app.room.calibration import RoomCalibrationService
from app.room.profiles import RoomProfileManager, quick_profile
from app.samsung.mock import MockFrameClient, sample
from app.services.watcher import AutomationWatcher


@pytest.fixture
async def system(tmp_path):
    db = Persistence(tmp_path)
    c = MockFrameClient()
    w = AutomationWatcher(db, c)
    await w.refresh_capabilities()
    db.put("rooms", "day", quick_profile("#d8c5aa"))
    db.put("rooms", "night", quick_profile("#534238"))
    w.save_settings({"profile_mode": "day"})
    yield db, c, w
    await w.stop()
    db.close()


async def test_mock_client(system):
    db, c, w = system
    assert (await c.get_device_info())["art_supported"]
    await c.select_artwork("MY-DEMO-1")
    assert c.changed.is_set()
    await c.set_matte("MY-DEMO-1", "modern_warm")
    assert await c.get_current_matte() == "modern_warm"


async def test_scoring_strategies_and_neutral(system):
    db, c, w = system
    art = ArtworkAnalyzer().analyze(sample())
    scores = []
    for strategy in ("Adaptive", "Subtle", "Contrast", "Gallery"):
        s = {**copy.deepcopy(DEFAULTS), "strategy": strategy}
        ranked = MatteRecommendationEngine().score(art, db.get("rooms", "day"), w.catalog.all(), s)
        scores.append([r["score"] for r in ranked])
        assert all(0 <= r["score"] <= 100 for r in ranked)
        assert len(ranked[0]["reasons"]) == 4
        if strategy == "Gallery":
            assert ranked[0]["matte"]["color"] in ("polar", "warm", "neutral", "black")
    assert len({str(s) for s in scores}) == 4


async def test_neutral_preference_penalizes_saturated(system):
    db, c, w = system
    art = ArtworkAnalyzer().analyze(sample())

    def navy(pref):
        ranked = w.engine.score(
            art, db.get("rooms", "day"), w.catalog.all(), {**w.settings, "neutral_preference": pref}
        )
        return next(r["score"] for r in ranked if r["matte"]["id"] == "modern_navy")

    assert navy(3) < navy(0)


async def test_no_repeated_writes(system):
    db, c, w = system
    w.save_settings({"automation": True, "threshold": 0, "cooldown": 0})
    await w.tick()
    count = len(c.writes)
    for _ in range(3):
        await w.tick()
    assert len(c.writes) == count


async def test_transient_thumbnail_failure_retries_without_poll_hammering(system, monkeypatch):
    db, c, w = system
    clock = [1000.0]
    monkeypatch.setattr("app.services.watcher.time.monotonic", lambda: clock[0])
    acquire = w.provider.acquire
    w.provider.acquire = AsyncMock(return_value=None)
    await w.tick()
    assert not w.state["recommendations"]
    clock[0] += 10
    await w.tick()
    assert w.provider.acquire.await_count == 1
    w.provider.acquire = AsyncMock(side_effect=acquire)
    clock[0] += 51
    await w.tick()
    assert w.state["recommendations"]
    await w.tick()
    assert w.provider.acquire.await_count == 1


async def test_hysteresis(system):
    db, c, w = system
    w.save_settings({"automation": True, "threshold": 100})
    await w.tick()
    assert not c.writes


async def test_day_night_reevaluates_same_art(system):
    db, c, w = system
    await w.tick()
    first = w.state["recommendations"]
    cid = c.current
    w.save_settings({"profile_mode": "night"})
    await w.tick()
    assert c.current == cid
    assert first != w.state["recommendations"]
    assert w.state["profile"] == "night"


async def test_never_modify_including_manual_apply(system):
    db, c, w = system
    db.put("overrides", c.current, {"mode": "never"})
    w.save_settings({"automation": True, "threshold": 0})
    await w.tick(apply=True)
    assert not c.writes


async def test_force_override(system):
    db, c, w = system
    db.put("overrides", c.current, {"mode": "force", "matte": "shadowbox_black"})
    w.save_settings({"automation": True})
    await w.tick()
    assert c.matte == "shadowbox_black"


async def test_artmode_off_no_writes(system):
    db, c, w = system
    c.mode = "off"
    w.save_settings({"automation": True, "threshold": 0})
    await w.tick(apply=True)
    assert not c.writes


async def test_reselect_quirk(system):
    db, c, w = system
    c.requires_reselect = True
    w.save_settings({"requires_reselect": True})
    db.put("overrides", c.current, {"mode": "force", "matte": "shadowbox_black"})
    await w.tick(apply=True)
    assert c.matte == "shadowbox_black"
    assert db.history()[0]["status"] == "verified"


async def test_unverified_write_not_success(system):
    db, c, w = system
    c.requires_reselect = True
    db.put("overrides", c.current, {"mode": "force", "matte": "shadowbox_black"})
    await w.tick(apply=True)
    assert db.history()[0]["status"] == "failed"


async def test_cooldown_and_new_artwork_exception(system):
    db, c, w = system
    w.save_settings({"automation": True, "threshold": 0, "cooldown": 3600})
    db.put("overrides", c.current, {"mode": "force", "matte": "shadowbox_black"})
    await w.tick()
    db.put("overrides", c.current, {"mode": "force", "matte": "modern_warm"})
    await w.tick()
    assert len(c.writes) == 1
    await c.select_artwork("MY-DEMO-1")
    db.put("overrides", c.current, {"mode": "force", "matte": "modern_warm"})
    await w.tick()
    assert len(c.writes) == 2


async def test_calibration_restores_and_only_deletes_owned(system):
    db, c, w = system
    service = RoomCalibrationService(db)
    original = c.current
    state = await service.start(c)
    assert c.current != original
    await w.tick(apply=True)
    assert not c.writes
    with pytest.raises(ValueError):
        await service.remove_owned(c, "MY-DEMO-0")
    await service.finish(c)
    assert c.current == original
    await service.remove_owned(c, state["content_id"])
    assert state["content_id"] not in c.images


def test_schedule_and_sun():
    manager = RoomProfileManager()
    s = {**copy.deepcopy(DEFAULTS), "timezone": "UTC"}
    assert manager.active(s, datetime(2026, 6, 1, 12, tzinfo=UTC)) == "day"
    assert manager.active(s, datetime(2026, 6, 1, 22, tzinfo=UTC)) == "night"
    s.update(schedule="sun", latitude=40, longitude=0)
    assert manager.active(s, datetime(2026, 6, 1, 12, tzinfo=UTC)) == "day"
    assert manager.active(s, datetime(2026, 6, 1, 1, tzinfo=UTC)) == "night"


def test_persistence_restart(tmp_path):
    db = Persistence(tmp_path)
    db.put("overrides", "EXAMPLE", {"mode": "never"})
    db.history({"reason": "test"})
    db.close()
    db = Persistence(tmp_path)
    assert db.get("overrides", "EXAMPLE")["mode"] == "never"
    assert db.history()[0]["reason"] == "test"
    db.close()


async def test_catalog_preserves_edits(system):
    db, c, w = system
    m = db.get("mattes", "modern_polar")
    m["enabled"] = False
    db.put("mattes", "modern_polar", m)
    MatteCatalog(db).refresh(await c.get_available_mattes())
    assert not db.get("mattes", "modern_polar")["enabled"]


async def test_deferred_profile_change_applies_after_cooldown(system, monkeypatch):
    db, c, w = system
    clock = [1000.0]
    monkeypatch.setattr("app.services.watcher.time.monotonic", lambda: clock[0])
    w.save_settings({"automation": True, "cooldown": 300})
    db.put("overrides", c.current, {"mode": "force", "matte": "shadowbox_black"})
    await w.tick()
    db.put("overrides", c.current, {"mode": "force", "matte": "modern_warm"})
    await w.tick()
    assert len(c.writes) == 1
    clock[0] += 301
    await w.tick()
    assert len(c.writes) == 2
    assert c.matte == "modern_warm"


async def test_cooldown_persists_across_watcher_restart(system):
    db, c, w = system
    db.put("overrides", c.current, {"mode": "force", "matte": "shadowbox_black"})
    await w.tick(apply=True)
    restarted = AutomationWatcher(db, c)
    assert restarted.last_written_content == c.current
    assert restarted.last_write > 0
