import json
from unittest.mock import AsyncMock

import pytest

from app.artwork.providers import ArtworkImageProvider
from app.db import Persistence
from app.room.calibration import RoomCalibrationService
from app.samsung.client import SamsungClient
from app.samsung.mock import MockFrameClient, sample


async def test_adapter_never_writes_when_artmode_off(tmp_path):
    c = SamsungClient("192.168.1.50", tmp_path)
    c.get_art_mode = AsyncMock(return_value="off")
    c._call = AsyncMock()
    with pytest.raises(ValueError, match="Art Mode"):
        await c.set_matte("MY-EXAMPLE", "modern_polar")
    c._call.assert_not_called()


async def test_adapter_refuses_stale_artwork(tmp_path):
    c = SamsungClient("192.168.1.50", tmp_path)
    c.get_art_mode = AsyncMock(return_value="on")
    c.get_current_artwork = AsyncMock(return_value={"content_id": "MY-NEW"})
    c._call = AsyncMock()
    with pytest.raises(ValueError, match="changed"):
        await c.set_matte("MY-OLD", "modern_polar")
    c._call.assert_not_called()


async def test_catalog_protocol_variants(tmp_path):
    c = SamsungClient("192.168.1.50", tmp_path)
    c.connect = AsyncMock()
    c.art._send_art_request = AsyncMock(
        return_value={"matte_list": json.dumps([{"matte_id": "modern_polar"}])}
    )
    result = await c.get_available_mattes()
    assert result["matte_types"][0]["matte_id"] == "modern_polar"
    assert result["matte_colors"] == []


async def test_thumbnail_rejects_transfer_to_other_host(tmp_path):
    c = SamsungClient("192.168.1.50", tmp_path)
    c.connect = AsyncMock()
    c.art._send_art_request = AsyncMock(
        return_value={"conn_info": {"ip": "192.168.1.60", "port": 9000}}
    )
    with pytest.raises(ValueError, match="unexpected transfer host"):
        await c.get_artwork_thumbnail("MY-EXAMPLE")


async def test_invalid_thumbnail_uses_local_reference(tmp_path):
    db = Persistence(tmp_path)
    provider = ArtworkImageProvider(db)
    client = MockFrameClient()
    client.get_artwork_thumbnail = AsyncMock(return_value=b"invalid image")
    provider.store_local(client.current, sample())
    acquired = await provider.acquire(client, client.current)
    assert acquired["image_source"] == "local"
    assert acquired["analysis"]["palette"]
    db.close()


async def test_cleanup_refuses_reused_content_id(tmp_path):
    db = Persistence(tmp_path)
    service = RoomCalibrationService(db)
    c = MockFrameClient()
    state = await service.start(c)
    await service.finish(c)
    c.images[state["content_id"]] = sample()
    with pytest.raises(ValueError):
        await service.remove_owned(c, state["content_id"])
    assert state["content_id"] in c.images
    db.close()


async def test_cleanup_refuses_other_tv(tmp_path):
    db = Persistence(tmp_path)
    service = RoomCalibrationService(db)
    c = MockFrameClient()
    state = await service.start(c)
    await service.finish(c)
    db.put("config", "tv_ip", "192.168.1.60")
    with pytest.raises(ValueError, match="different television"):
        await service.remove_owned(c, state["content_id"])
    db.close()
