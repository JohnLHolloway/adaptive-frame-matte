import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.samsung.discovery import validate_ip


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "169.254.169.254",
        "8.8.8.8",
        "0.0.0.0",
        "224.0.0.1",
        "example.com",
        "file:///etc/passwd",
    ],
)
def test_ip_validation(ip):
    with pytest.raises(ValueError):
        validate_ip(ip)


def test_private_ip():
    assert validate_ip("192.168.1.50") == "192.168.1.50"


def test_web_setup_and_security(tmp_path):
    with TestClient(create_app(tmp_path, mock=True)) as c:
        assert c.get("/healthz").status_code == 200
        page = c.get("/setup")
        assert page.status_code == 200
        csrf = re.search(r'name="csrf-token" content="([^"]+)', page.text)[1]
        assert c.post("/api/action/resume").status_code == 403
        headers = {"x-csrf-token": csrf}
        assert (
            c.post(
                "/api/action/resume", headers={**headers, "origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            c.post("/api/room/day/quick", headers=headers, json={"color": "#d8c5aa"}).status_code
            == 200
        )
        assert (
            c.post("/api/settings", headers=headers, json={"profile_mode": "day"}).status_code
            == 200
        )
        assert c.post("/api/action/evaluate", headers=headers).status_code == 200
        state = c.get("/api/state").json()
        assert state["recommendations"]
        assert "token" not in state
        assert c.get("/media/room/not-a-photo.txt").status_code == 404
        assert (
            c.post("/api/settings", headers=headers, json={"strategy": "invalid"}).status_code
            == 400
        )
        assert c.post(
            "/api/room/../../evil/quick", headers=headers, json={"color": "#ffffff"}
        ).status_code in (404, 405)
        assert (
            c.post(
                "/api/room/day/photo",
                headers=headers,
                files={"file": ("evil.jpg", b"hello", "image/jpeg")},
            ).status_code
            >= 400
        )
