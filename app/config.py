import os
from pathlib import Path

DATA = Path(os.environ.get("FRAME_DATA_DIR", "/data"))
MOCK = os.environ.get("FRAME_MOCK_TV", "false").lower() == "true"
MAX_UPLOAD = 20 * 1024 * 1024
DEFAULTS = {
    "automation": False,
    "strategy": "Adaptive",
    "threshold": 8.0,
    "cooldown": 300,
    "poll_seconds": 10,
    "neutral_preference": 1.0,
    "weights": {"edge": 30, "wall": 25, "palette": 15, "room": 10, "lightness": 10, "neutral": 10},
    "profile_mode": "auto",
    "schedule": "fixed",
    "day_start": "07:00",
    "night_start": "19:00",
    "timezone": "UTC",
    "latitude": None,
    "longitude": None,
    "fallback": "retain",
    "safe_matte": "",
    "requires_reselect": False,
    "preferred_family": "",
    "setup_complete": False,
}
