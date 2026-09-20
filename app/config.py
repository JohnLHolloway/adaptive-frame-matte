import os
from pathlib import Path

DATA = Path(os.environ.get("FRAME_DATA_DIR", "/data"))
MOCK = os.environ.get("FRAME_MOCK_TV", "false").lower() == "true"
MAX_UPLOAD = 20 * 1024 * 1024
DEFAULTS = {
    "automation": False,
    "color_mode": "automatic",
    "fixed_color": "",
    "frame_finish": "unspecified",
    "strategy": "Gallery",
    "threshold": 8.0,
    "cooldown": 300,
    "poll_seconds": 10,
    "neutral_preference": 1.0,
    "weights": {"edge": 30, "palette": 20, "lightness": 15, "neutral": 35},
    "fallback": "retain",
    "safe_matte": "",
    "requires_reselect": False,
    "preferred_family": "",
    "preferred_family_only": False,
    "setup_complete": False,
}
