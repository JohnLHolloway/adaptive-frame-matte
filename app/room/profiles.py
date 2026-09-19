from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from astral import Observer
from astral.sun import sun

from app.artwork.palette import to_lab
from app.room.calibration import describe


def quick_profile(color):
    if len(color) != 7 or color[0] != "#":
        raise ValueError("Use #RRGGBB")
    rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    lab = to_lab(rgb)
    return {
        "wall_hex": color,
        "wall_lab": lab.tolist(),
        "lightness": float(lab[0]),
        "chroma": float(np.linalg.norm(lab[1:])),
        "warmth": float(lab[2]),
        "brightness": float(lab[0]),
        "ambient_cast": [0, 0, 0],
        "confidence": 0.35,
        "descriptors": describe(lab, 0),
        "palette": [],
        "neutral_palette": [],
        "variability": 0,
        "contrast": 0,
        "source": "manual",
    }


class RoomProfileManager:
    def active(self, settings, instant=None):
        mode = settings["profile_mode"]
        if mode in ("day", "night"):
            return mode
        zone = ZoneInfo(settings["timezone"])
        local = instant.astimezone(zone) if instant else datetime.now(zone)
        if settings["schedule"] == "sun" and settings.get("latitude") is not None:
            try:
                # Shift the observation instead of just today's boundaries: this also
                # handles offsets that move sunrise/sunset across midnight and DST.
                solar_local = (
                    local.astimezone(UTC) - timedelta(minutes=settings.get("sun_offset_minutes", 0))
                ).astimezone(zone)
                times = sun(
                    Observer(settings["latitude"], settings["longitude"]),
                    date=solar_local.date(),
                    tzinfo=zone,
                )
                return "day" if times["sunrise"] <= solar_local < times["sunset"] else "night"
            except ValueError:
                pass  # Polar-day/night calculation failure: documented fixed schedule fallback.
        start, end = (
            time.fromisoformat(settings["day_start"]),
            time.fromisoformat(settings["night_start"]),
        )
        t = local.time().replace(tzinfo=None)
        is_day = start <= t < end if start < end else t >= start or t < end
        return "day" if is_day else "night"
