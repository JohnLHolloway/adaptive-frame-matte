import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.artwork.providers import ArtworkImageProvider
from app.db import Persistence
from app.room.calibration import RoomCalibrationService
from app.samsung.client import SamsungClient
from app.samsung.mock import MockFrameClient, sample


async def test_pair_obtains_remote_token_without_sending_commands(tmp_path, monkeypatch):
    remote = MagicMock()
    remote.open = AsyncMock()
    remote.close = AsyncMock()
    factory = MagicMock(return_value=remote)
    monkeypatch.setattr("app.samsung.client.SamsungTVWSAsyncRemote", factory)
    c = SamsungClient("192.168.1.50", tmp_path)
    c.connect = AsyncMock()
    await c.pair()
    remote.open.assert_awaited_once()
    remote.close.assert_awaited_once()
    remote.send_command.assert_not_called()
    c.connect.assert_awaited_once()


async def test_pair_failure_closes_remote_and_does_not_enter_art(tmp_path, monkeypatch):
    remote = MagicMock()
    remote.open = AsyncMock(side_effect=TimeoutError)
    remote.close = AsyncMock()
    monkeypatch.setattr("app.samsung.client.SamsungTVWSAsyncRemote", lambda *a, **kw: remote)
    c = SamsungClient("192.168.1.50", tmp_path)
    c.connect = AsyncMock()
    with pytest.raises(TimeoutError):
        await c.pair()
    remote.close.assert_awaited_once()
    remote.send_command.assert_not_called()
    c.connect.assert_not_called()


async def test_device_info_falls_back_to_same_tv_tls(monkeypatch):
    from app.samsung import discovery

    seen = []

    def respond(request):
        seen.append(str(request.url))
        if request.url.port == 8001:
            raise httpx.ConnectTimeout("HTTP unavailable", request=request)
        return httpx.Response(
            200, json={"device": {"modelName": "Test Frame", "FrameTVSupport": "true"}}
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        discovery.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    info = await discovery.device_info("192.168.1.50")
    assert info["model"] == "Test Frame"
    assert info["art_supported"] is True
    assert seen == [
        "http://192.168.1.50:8001/api/v2/",
        "https://192.168.1.50:8002/api/v2/",
    ]


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


async def test_probe_restores_distinct_portrait_orientation(tmp_path):
    c = SamsungClient("192.168.1.50", tmp_path)
    original = {
        "content_id": "MY_F0001",
        "matte_id": "none",
        "portrait_matte_id": "shadowbox_polar",
    }
    c.get_art_mode = AsyncMock(return_value="on")
    c.get_current_artwork = AsyncMock(
        side_effect=[
            {**original, "portrait_matte_id": "none"},
            original,
        ]
    )
    c.set_matte = AsyncMock()
    c._call = AsyncMock()
    await c.restore_mattes(original)
    c.set_matte.assert_awaited_once_with("MY_F0001", "none")
    c._call.assert_awaited_once_with(
        c.art.change_matte, "MY_F0001", "none", portrait_matte="shadowbox_polar"
    )


async def test_current_normalizes_matte_case_without_changing_content_id(tmp_path):
    c = SamsungClient("192.168.1.50", tmp_path)
    c._call = AsyncMock(
        return_value={
            "content_id": "SAM-EXAMPLE",
            "matte_id": "NONE",
            "portrait_matte_id": "SHADOWBOX_POLAR",
        }
    )
    assert await c.get_current_artwork() == {
        "content_id": "SAM-EXAMPLE",
        "matte_id": "none",
        "portrait_matte_id": "shadowbox_polar",
    }


async def test_select_waits_for_delayed_readback(tmp_path, monkeypatch):
    c = SamsungClient("192.168.1.50", tmp_path)
    c.get_art_mode = AsyncMock(return_value="on")
    c._call = AsyncMock()
    c.get_current_artwork = AsyncMock(
        side_effect=[{"content_id": "MY-OLD"}, {"content_id": "MY-NEW"}]
    )
    monkeypatch.setattr("app.samsung.client.asyncio.sleep", AsyncMock())
    await c.select_artwork("MY-NEW")
    assert c.get_current_artwork.await_count == 2


@pytest.mark.parametrize("identifier", ["MY-EXAMPLE", "MY_F0004", "MY_F0004.png"])
async def test_upload_accepts_personal_id_variants(tmp_path, identifier):
    c = SamsungClient("192.168.1.50", tmp_path)
    c._call = AsyncMock(return_value=identifier)
    assert await c.upload_artwork(b"test") == identifier.split(".")[0]


@pytest.mark.parametrize("identifier", ["SAM-EXAMPLE", "../MY-example", "MY_F0004/other"])
async def test_upload_rejects_unexpected_identifiers(tmp_path, identifier):
    c = SamsungClient("192.168.1.50", tmp_path)
    c._call = AsyncMock(return_value=identifier)
    with pytest.raises(ValueError, match="personal artwork identifier"):
        await c.upload_artwork(b"test")


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
