import copy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from astral import Observer
from astral.sun import sun
from fastapi.testclient import TestClient

from app.config import DEFAULTS
from app.main import create_app
from app.room.profiles import RoomProfileManager
from app.tests.test_multitv import headers


@pytest.mark.parametrize("offset", [-90, 0, 90])
def test_shared_offset_moves_both_boundaries(offset):
    settings = {
        **copy.deepcopy(DEFAULTS),
        "schedule": "sun",
        "timezone": "UTC",
        "latitude": 40,
        "longitude": 0,
        "sun_offset_minutes": offset,
    }
    times = sun(Observer(40, 0), date=datetime(2026, 6, 1).date(), tzinfo=UTC)
    manager = RoomProfileManager()
    for event, before, after in [("sunrise", "night", "day"), ("sunset", "day", "night")]:
        boundary = times[event] + timedelta(minutes=offset)
        assert manager.active(settings, boundary - timedelta(seconds=1)) == before
        assert manager.active(settings, boundary + timedelta(seconds=1)) == after


def test_offset_crosses_midnight():
    settings = {
        **copy.deepcopy(DEFAULTS),
        "schedule": "sun",
        "timezone": "UTC",
        "latitude": 40,
        "longitude": 0,
        "sun_offset_minutes": 360,
    }
    # Yesterday's sunset + six hours occurs early the following morning.
    times = sun(Observer(40, 0), date=datetime(2026, 6, 1).date(), tzinfo=UTC)
    boundary = times["sunset"] + timedelta(hours=6)
    assert boundary.day == 2
    assert RoomProfileManager().active(settings, boundary - timedelta(seconds=1)) == "day"
    assert RoomProfileManager().active(settings, boundary + timedelta(seconds=1)) == "night"


def test_offset_on_dst_transition_and_fixed_schedule():
    settings = {
        **copy.deepcopy(DEFAULTS),
        "schedule": "sun",
        "timezone": "America/New_York",
        "latitude": 40,
        "longitude": -74,
        "sun_offset_minutes": -360,
    }
    times = sun(
        Observer(40, -74), date=datetime(2026, 3, 8).date(), tzinfo=ZoneInfo("America/New_York")
    )
    boundary = times["sunrise"].astimezone(UTC) - timedelta(hours=6)
    manager = RoomProfileManager()
    assert manager.active(settings, boundary - timedelta(seconds=1)) == "night"
    assert manager.active(settings, boundary + timedelta(seconds=1)) == "day"
    settings.update(schedule="fixed", timezone="UTC")
    assert manager.active(settings, datetime(2026, 6, 1, 7, tzinfo=UTC)) == "day"
    assert manager.active(settings, datetime(2026, 6, 1, 19, tzinfo=UTC)) == "night"


def test_offset_api_validation_and_persistence(tmp_path):
    with TestClient(create_app(tmp_path, mock=True)) as client:
        h = headers(client)
        assert client.post("/api/settings", json={"sun_offset_minutes": 30}, headers=h).is_success
        assert (
            client.post("/api/settings", json={"sun_offset_minutes": 361}, headers=h).status_code
            == 422
        )
    with TestClient(create_app(tmp_path, mock=True)) as client:
        assert client.get("/api/state").json()["settings"]["sun_offset_minutes"] == 30
