import re

from fastapi.testclient import TestClient

from app.db import Persistence
from app.main import create_app


def headers(client, tv="primary"):
    csrf = re.search(r'name="csrf-token" content="([^"]+)', client.get("/").text)[1]
    return {"x-csrf-token": csrf, "x-frame-id": tv}


def test_tv_settings_profiles_overrides_and_media_are_isolated(tmp_path):
    with TestClient(create_app(tmp_path, mock=True)) as c:
        primary = headers(c)
        added = c.post("/api/televisions", json={"name": "Bedroom"}, headers=primary)
        second = added.json()["id"]
        other = headers(c, second)
        c.post("/api/settings", json={"strategy": "Contrast"}, headers=other)
        c.post("/api/action/evaluate", headers=primary)
        c.post("/api/action/evaluate", headers=other)
        a, b = (
            c.get("/api/state", headers=primary).json(),
            c.get("/api/state", headers=other).json(),
        )
        assert a["settings"]["strategy"] == "Gallery"
        assert b["settings"]["strategy"] == "Contrast"
        cid = b["current"]["content_id"]
        assert c.post(
            "/api/override", json={"content_id": cid, "mode": "never"}, headers=other
        ).is_success
        assert (
            c.get("/api/artworks", headers=other).json()["items"][0]["override"]["mode"] == "never"
        )
        assert (
            c.get("/api/artworks", headers=primary).json()["items"][0]["override"]["mode"]
            == "automatic"
        )
        (tmp_path / "artwork" / "private.png").write_bytes(b"private-primary-image")
        assert c.get("/media/artwork/private.png?tv=primary").status_code == 200
        assert c.get(f"/media/artwork/private.png?tv={second}").status_code == 404
        assert c.get("/api/state", headers={"x-frame-id": "../"}).status_code == 404


def test_existing_single_tv_and_added_tv_survive_restart(tmp_path):
    old = Persistence(tmp_path)
    old.put("config", "settings", {"requires_reselect": True})
    old.put("rooms", "day", {"wall_hex": "#abcdef"})
    old.close()
    with TestClient(create_app(tmp_path, mock=True)) as c:
        added = c.post("/api/televisions", json={"name": "Second"}, headers=headers(c)).json()["id"]
        c.post("/api/settings", json={"strategy": "Subtle"}, headers=headers(c, added))
    with TestClient(create_app(tmp_path, mock=True)) as c:
        primary = c.get("/api/state").json()
        assert primary["settings"]["requires_reselect"] is True
        assert "rooms" not in primary
        assert len(primary["televisions"]) == 2
        secondary = c.get("/api/state", headers={"x-frame-id": added}).json()
        assert secondary["settings"]["strategy"] == "Subtle"
        assert "rooms" not in secondary


def test_large_artwork_library_paginates_and_filters_in_database(tmp_path):
    with TestClient(create_app(tmp_path, mock=True)) as c:
        db = c.app.state.db
        for number in range(300):
            cid = f"MY-TEST-{number:03}"
            db.put("artwork", cid, {"content_id": cid, "last_seen": "2026-01-01"})
            if number % 2 == 0:
                db.put("overrides", cid, {"mode": "never"})
        result = c.get("/api/artworks?q=MY-TEST&behavior=never&page=2&size=24").json()
        assert result["total"] == 150
        assert len(result["items"]) == 24
        assert result["page"] == 2 and result["pages"] == 7
        assert result["items"][0]["content_id"] == "MY-TEST-048"
        assert "artworks" not in c.get("/api/state").json()
        assert c.get("/api/artworks?size=999").status_code == 400


def test_custom_appearance_updates_existing_colors_without_inventing_mattes(tmp_path):
    with TestClient(create_app(tmp_path, mock=True)) as c:
        h = headers(c)
        before = c.get("/api/state").json()["mattes"]
        result = c.post(
            "/api/mattes/bulk",
            json={
                "field": "color",
                "value": "polar",
                "hex": "#eeeecc",
                "preference": "preferred",
                "enabled": True,
            },
            headers=h,
        )
        assert result.is_success
        after = c.get("/api/state").json()["mattes"]
        assert {m["id"] for m in before} == {m["id"] for m in after}
        assert all(m["hex"] == "#eeeecc" for m in after if m["color"] == "polar")
        assert (
            c.post(
                "/api/mattes/bulk",
                json={
                    "field": "color",
                    "value": "invented",
                    "hex": "#123456",
                },
                headers=h,
            ).status_code
            == 400
        )


def test_duplicate_tv_address_is_rejected_before_pairing(tmp_path):
    with TestClient(create_app(tmp_path, mock=False)) as c:
        primary = headers(c)
        c.app.state.db.put("config", "tv_ip", "192.168.1.50")
        second = c.post("/api/televisions", json={"name": "Second"}, headers=primary).json()["id"]
        result = c.post("/api/connect", json={"ip": "192.168.1.50"}, headers=headers(c, second))
        assert result.status_code == 400
        assert "already configured" in result.json()["detail"]
        assert c.app.state.televisions.runtimes[second].watcher.client is None
