import asyncio
import contextlib
import copy
import json
import logging
import time
from datetime import UTC, datetime

from app.artwork.providers import ArtworkImageProvider
from app.config import DEFAULTS
from app.db import now
from app.matte.catalog import MatteCatalog
from app.matte.scoring import MatteRecommendationEngine
from app.room.profiles import RoomProfileManager

log = logging.getLogger(__name__)


class AutomationWatcher:
    def __init__(self, db, client=None):
        self.db, self.client = db, client
        self.settings = {**copy.deepcopy(DEFAULTS), **db.get("config", "settings", {})}
        self.catalog = MatteCatalog(db)
        self.provider = ArtworkImageProvider(db)
        self.engine = MatteRecommendationEngine()
        self.profiles = RoomProfileManager()
        self.lock = asyncio.Lock()
        self.key = None
        self.last_write = 0
        self.last_written_content = None
        self.deferred_until = 0
        self.thumbnail_retry_at = 0
        saved_change = db.get("runtime", "last_change")
        if saved_change:
            elapsed = max(
                0,
                (
                    datetime.now(UTC) - datetime.fromisoformat(saved_change["timestamp"])
                ).total_seconds(),
            )
            self.last_write = time.monotonic() - elapsed
            self.last_written_content = saved_change["content_id"]
        self.state = {"connected": False, "current": {}, "recommendations": [], "error": None}
        self.task = None
        self.stopping = False

    def save_settings(self, update):
        self.settings.update(update)
        self.db.put("config", "settings", self.settings)
        self.key = None

    async def refresh_capabilities(self):
        await self.client.connect()
        info = await self.client.get_device_info()
        if not info["art_supported"]:
            raise ValueError("This TV does not advertise Art Mode support")
        self.db.put("config", "device", info)
        raw = await self.client.get_available_mattes()
        self.catalog.refresh(raw)
        caps = {
            **self.db.get("config", "capabilities", {}),
            "api_version": info.get("api_version"),
            "art_supported": True,
            "matte_count": len(self.catalog.all()),
            "requires_reselect_after_matte_change": self.db.get("config", "capabilities", {}).get(
                "requires_reselect_after_matte_change", "unverified"
            ),
            "matte_write": self.db.get("config", "capabilities", {}).get(
                "matte_write", "unverified"
            ),
            "websocket_events": sorted(self.client.observed_events),
        }
        self.db.put("config", "capabilities", caps)
        log.info("CAPABILITIES_REFRESHED")

    async def tick(self, force=False, apply=False):
        async with self.lock:
            if not self.client:
                return self.state
            if self.db.get("calibration", "active"):
                self.state["message"] = "Automation suspended during calibration"
                return self.state
            try:
                mode = await self.client.get_art_mode()
                self.state.update(
                    connected=True, artmode=mode, last_communication=now(), error=None
                )
                if mode != "on":
                    self.state["message"] = "Art Mode is off; no matte changes will be made"
                    self.key = None  # Refresh when the TV returns to Art Mode.
                    return self.state
                current = await self.client.get_current_artwork()
                cid = current["content_id"]
                old_cid = self.state.get("current", {}).get("content_id")
                profile = (
                    self.profiles.active(self.settings) if self.settings["use_room"] else "artwork"
                )
                room = self.db.get("rooms", profile) if self.settings["use_room"] else None
                self.state.update(current=current, profile=profile, room=room)
                if cid != old_cid:
                    self.thumbnail_retry_at = 0
                    self.state["last_artwork_change"] = now()
                    log.info("ARTWORK_CHANGED")
                override = self.db.get("overrides", cid, {"mode": "automatic"})
                key = json.dumps(
                    [cid, profile, room, self.settings, self.catalog.all(), override],
                    sort_keys=True,
                )
                retry_thumbnail = bool(
                    self.thumbnail_retry_at and time.monotonic() >= self.thumbnail_retry_at
                )
                if (
                    not force
                    and not apply
                    and not retry_thumbnail
                    and key == self.key
                    and (not self.deferred_until or time.monotonic() < self.deferred_until)
                ):
                    return self.state
                self.deferred_until = 0
                if profile != self.state.get("evaluated_profile"):
                    log.info("ROOM_PROFILE_CHANGED")
                self.state["evaluated_profile"] = profile
                self.key = key
                art = self.db.get("artwork", cid, {})
                if force or cid != old_cid or not art.get("analysis"):
                    obtained = await self.provider.acquire(self.client, cid)
                    if obtained:
                        art.update(obtained)
                    self.thumbnail_retry_at = (
                        time.monotonic() + 60 if not art.get("analysis") else 0
                    )
                    caps = self.db.get("config", "capabilities", {})
                    caps["thumbnail"] = bool(obtained and obtained.get("image_source") == "tv")
                    if cid.startswith("SAM-"):
                        caps["sam_thumbnail"] = caps["thumbnail"]
                    self.db.put("config", "capabilities", caps)
                art.update(content_id=cid, last_seen=now(), current_matte=current.get("matte_id"))
                self.db.put("artwork", cid, art)
                self.state.update(artwork=art, recommendations=[], message="")
                if art.get("analysis") and (room or not self.settings["use_room"]):
                    self.state["recommendations"] = self.engine.score(
                        art["analysis"], room, self.catalog.all(), self.settings
                    )
                    log.info("MATTE_RECOMMENDED")
                elif not art.get("analysis"):
                    self.state["message"] = (
                        "Artwork image unavailable — automatic visual analysis cannot run for this artwork."
                    )
                else:
                    self.state["message"] = (
                        f"Add a {profile} room profile before visual recommendations can run."
                    )
                art["recommendation"] = (
                    self.state["recommendations"][0] if self.state["recommendations"] else None
                )
                self.db.put("artwork", cid, art)
                if override["mode"] == "never":
                    self.state["message"] = "Never modify override is active"
                    return self.state
                if self.settings["automation"] or apply:
                    await self._maybe_apply(current, override, apply)
                return self.state
            except Exception as error:
                self.key = None
                self.state.update(
                    connected=False,
                    error=f"{type(error).__name__}: TV operation failed. Check Diagnostics and pairing.",
                )
                log.warning("TV_DISCONNECTED")
                if apply:
                    raise ValueError(
                        "TV operation failed; no verified change. Check Diagnostics."
                    ) from None
                return self.state

    async def apply_choice(self, content_id, matte_id, remember=False):
        """Apply an explicit choice without silently targeting a newly selected artwork."""
        async with self.lock:
            if not self.client or self.db.get("calibration", "active"):
                raise ValueError("Connect the TV and finish calibration before applying")
            if matte_id not in {m["id"] for m in self.catalog.all() if m["enabled"]}:
                raise ValueError("Choose an enabled matte advertised by this TV")
            if self.db.get("overrides", content_id, {}).get("mode") == "never":
                raise ValueError("Never modify is active; change the artwork override first")
            if await self.client.get_art_mode() != "on":
                raise ValueError("Art Mode must be on")
            current = await self.client.get_current_artwork()
            if current["content_id"] != content_id:
                raise ValueError("Artwork changed; refresh before applying")
            self.state["profile"] = (
                self.profiles.active(self.settings) if self.settings["use_room"] else "artwork"
            )
            await self._maybe_apply(current, {"mode": "force", "matte": matte_id}, True)
            actual = await self.client.get_current_artwork()
            if actual["content_id"] != content_id or actual.get("matte_id") != matte_id:
                raise ValueError("TV did not confirm this choice; no override saved")
            if remember:
                self.db.put("overrides", content_id, {"mode": "force", "matte": matte_id})
                self.key = None
            self.state["current"] = actual
            self.state["message"] = (
                "Saved for this artwork. Choose Automatic on Artwork to remove the override."
                if remember
                else "Matte applied. Automation remains active for future evaluations."
            )

    async def _maybe_apply(self, current, override, manual):
        candidates = self.state["recommendations"]
        cid = current["content_id"]
        selected = None
        if override["mode"] == "force":
            selected = override.get("matte")
        elif candidates:
            selected = candidates[0]["matte"]["id"]
        elif self.settings["fallback"] == "safe":
            selected = self.settings["safe_matte"]
        if not selected or selected == current.get("matte_id"):
            return
        available = {m["id"] for m in self.catalog.all() if m["enabled"]}
        if selected not in available:
            raise ValueError("Selected matte is disabled or unavailable on this TV")
        if not manual:
            if (
                cid == self.last_written_content
                and time.monotonic() - self.last_write < self.settings["cooldown"]
            ):
                self.deferred_until = self.last_write + self.settings["cooldown"]
                self.state["message"] = (
                    "Recommendation queued until the automatic change cooldown ends"
                )
                return
            if override["mode"] != "force" and candidates:
                baseline = next(
                    (r["score"] for r in candidates if r["matte"]["id"] == current.get("matte_id")),
                    0,
                )
                if candidates[0]["score"] - baseline < self.settings["threshold"]:
                    return
        # Recheck both state and content immediately before writing.
        if await self.client.get_art_mode() != "on":
            return
        if (await self.client.get_current_artwork())["content_id"] != cid:
            self.key = None
            return
        try:
            await self.client.set_matte(cid, selected)
            if self.settings["requires_reselect"]:
                if (
                    await self.client.get_art_mode() == "on"
                    and (await self.client.get_current_artwork())["content_id"] == cid
                ):
                    await self.client.select_artwork(cid)
            actual = await self.client.get_current_artwork()
            if actual.get("matte_id") != selected:
                raise ValueError(
                    "TV did not confirm the requested matte; check artwork compatibility/redraw setting"
                )
        except Exception:
            self.db.history(
                {
                    "artwork": cid,
                    "profile": self.state["profile"],
                    "previous": current.get("matte_id"),
                    "new": selected,
                    "score": None,
                    "reason": "TV did not confirm change",
                    "mode": "manual" if manual else "automatic",
                    "status": "failed",
                }
            )
            # Suppress automatic retries until something meaningful changes.
            self.state["message"] = "Matte change was not verified. Re-evaluate to retry."
            log.warning("MATTE_APPLY_FAILED")
            return
        self.last_write, self.last_written_content = time.monotonic(), cid
        self.db.put("runtime", "last_change", {"timestamp": now(), "content_id": cid})
        self.state.update(current=actual, last_matte_change=now())
        art = self.db.get("artwork", cid, {})
        art["current_matte"] = selected
        self.db.put("artwork", cid, art)
        entry = next((r for r in candidates if r["matte"]["id"] == selected), {})
        self.db.history(
            {
                "artwork": cid,
                "profile": self.state["profile"],
                "previous": current.get("matte_id"),
                "new": selected,
                "score": entry.get("score"),
                "reason": "; ".join(entry.get("reasons", ["User override or safe fallback"])),
                "mode": "manual" if manual else "automatic",
                "status": "verified",
            }
        )
        caps = self.db.get("config", "capabilities", {})
        caps["matte_write"] = "verified by API readback"
        self.db.put("config", "capabilities", caps)
        log.info("MATTE_APPLIED")

    async def run(self):
        failures = 0
        while not self.stopping:
            if self.client:
                self.client.changed.clear()
            await self.tick()
            failures = failures + 1 if self.state.get("error") else 0
            delay = min(120, self.settings["poll_seconds"] * 2 ** min(failures, 4))
            if self.client:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.client.changed.wait(), delay)
            else:
                await asyncio.sleep(delay)

    async def stop(self):
        self.stopping = True
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.client:
            await self.client.close()
