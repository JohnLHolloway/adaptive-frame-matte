"""The only module coupled to samsungtvws. Never sends power or remote keys."""

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import ssl
import uuid
from pathlib import Path

from samsungtvws.async_art import SamsungTVAsyncArt

from app.samsung.discovery import device_info, validate_ip

# Upstream logs pairing tokens and websocket URLs, even at INFO. Disable its logger tree.
for logger_name in list(logging.Logger.manager.loggerDict):
    if logger_name.startswith("samsungtvws"):
        logging.getLogger(logger_name).disabled = True
logging.getLogger("samsungtvws").disabled = True


class LocalArt(SamsungTVAsyncArt):
    def get_token(self):
        """Pair only on explicit async connect, never through constructor-side remote I/O."""

    async def get_artmode(self):
        data = await self._send_art_request({"request": "get_artmode_status"})
        if not data:
            raise ValueError("Art Mode status is unavailable")
        return data.get("value", data.get("status"))


class SamsungClient:
    def __init__(self, ip: str, directory: Path):
        self.ip = validate_ip(ip)
        directory.mkdir(parents=True, exist_ok=True)
        self.token_file = directory / (hashlib.sha256(ip.encode()).hexdigest()[:16] + ".token")
        self.art = LocalArt(
            ip,
            port=8002,
            token_file=str(self.token_file),
            timeout=15,
            name="Adaptive Frame Matte",
            key_press_delay=0.1,
        )
        self.changed = asyncio.Event()
        self.observed_events = set()
        self.lock = asyncio.Lock()
        for name in (
            "image_selected",
            "slideshow_image_changed",
            "auto_rotation_image_changed",
            "art_mode_changed",
            "artmode_status",
        ):
            self.art.set_callback(name, self._event)

    def _event(self, event, response):
        name = json.loads(response.get("data", "{}")).get("event", event)
        self.observed_events.add(name)
        self.changed.set()

    async def connect(self):
        if not self.art.is_alive():
            await asyncio.wait_for(self.art.start_listening(), 45)
        if self.token_file.exists():
            self.token_file.chmod(0o600)

    async def pair(self):
        await self.connect()

    async def close(self):
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.art.close(), 5)

    async def _call(self, fn, *args, **kwargs):
        async with self.lock:
            await self.connect()
            try:
                return await asyncio.wait_for(fn(*args, **kwargs), 20)
            except (TimeoutError, AssertionError, OSError):
                await self.close()
                raise RuntimeError(
                    "TV request failed or timed out; reconnect will be attempted"
                ) from None

    async def get_device_info(self):
        info = await device_info(self.ip)
        try:
            info["api_version"] = await self._call(self.art.get_api_version)
        except Exception:
            info["api_version"] = "unknown"
        return info

    async def get_art_mode(self):
        value = await self._call(self.art.get_artmode)
        if value not in ("on", "off"):
            raise RuntimeError("TV returned an unknown Art Mode state")
        return value

    async def get_current_artwork(self):
        data = await self._call(self.art.get_current)
        result = {
            k: data[k]
            for k in ("content_id", "matte_id", "portrait_matte_id", "content_type", "category_id")
            if k in data
        }
        # Store content can report uppercase defaults; writes return lowercase equivalents.
        for field in ("matte_id", "portrait_matte_id"):
            if isinstance(result.get(field), str):
                result[field] = result[field].lower()
        return result

    async def get_current_matte(self):
        return (await self.get_current_artwork()).get("matte_id", "")

    async def get_available_mattes(self):
        async def request():
            data = await self.art._send_art_request({"request": "get_matte_list"})
            if not data:
                raise ValueError("TV did not return a matte catalog")
            types = data.get("matte_type_list", data.get("matte_list", []))
            colors = data.get("matte_color_list", [])
            return {
                "matte_types": json.loads(types) if isinstance(types, str) else types,
                "matte_colors": json.loads(colors) if isinstance(colors, str) else colors,
            }

        return await self._call(request)

    async def get_artwork_thumbnail(self, content_id):
        # Bounded D2D receive: do not trust a TV-supplied hostname, length or filename.
        async def receive():
            result = await self.art._send_art_request(
                {
                    "request": "get_thumbnail_list",
                    "content_id_list": [{"content_id": content_id}],
                    "conn_info": {
                        "d2d_mode": "socket",
                        "connection_id": uuid.uuid4().int % 2**32,
                        "id": str(uuid.uuid4()),
                    },
                }
            )
            if not result:
                raise RuntimeError("Thumbnail unavailable")
            conn = result["conn_info"]
            conn = json.loads(conn) if isinstance(conn, str) else conn
            if conn.get("ip") != self.ip:
                raise ValueError("TV returned an unexpected transfer host")
            port = int(conn["port"])
            if not 1024 <= port <= 65535:
                raise ValueError("Invalid transfer port")
            ctx = None
            if conn.get("secured"):
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE  # Samsung's local self-signed certificate
            reader, writer = await asyncio.open_connection(self.ip, port, ssl=ctx)
            try:
                size = int.from_bytes(await reader.readexactly(4), "big")
                if not 1 <= size <= 65536:
                    raise ValueError("Invalid thumbnail header")
                header = json.loads(await reader.readexactly(size))
                length = int(header["fileLength"])
                if not 1 <= length <= 20 * 1024 * 1024:
                    raise ValueError("Invalid thumbnail size")
                return await reader.readexactly(length)
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

        return await self._call(receive)

    async def set_matte(self, content_id, matte):
        if await self.get_art_mode() != "on":
            raise ValueError("Matte changes require active Art Mode")
        current = await self.get_current_artwork()
        if current["content_id"] != content_id:
            raise ValueError("Artwork changed; re-evaluate before applying")
        # Some firmware couples the reported landscape and portrait matte values.
        # Supplying the old portrait value here can cancel the requested visible change.
        await self._call(self.art.change_matte, content_id, matte)

    async def restore_mattes(self, original):
        """Restore both recorded orientations for the opt-in acceptance probe."""
        cid = original["content_id"]
        await self.set_matte(cid, original["matte_id"])
        actual = await self.get_current_artwork()
        portrait = original.get("portrait_matte_id")
        if portrait and actual.get("portrait_matte_id") != portrait:
            if actual["content_id"] != cid or await self.get_art_mode() != "on":
                raise ValueError("TV state changed during restoration")
            await self._call(
                self.art.change_matte, cid, original["matte_id"], portrait_matte=portrait
            )
        actual = await self.get_current_artwork()
        if any(
            actual.get(k) != original.get(k)
            for k in ("content_id", "matte_id", "portrait_matte_id")
        ):
            raise ValueError("TV did not confirm restoration of both matte orientations")

    async def select_artwork(self, content_id):
        if await self.get_art_mode() != "on":
            raise ValueError("Will not wake the TV or enter Art Mode")
        await self._call(self.art.select_image, content_id, show=True)
        # The acknowledgement can arrive before get_current_artwork reflects selection.
        # Wait briefly for readback rather than racing calibration cleanup/restoration.
        for _ in range(12):
            if (await self.get_current_artwork()).get("content_id") == content_id:
                return
            await asyncio.sleep(0.25)
        raise ValueError("TV did not confirm the requested artwork selection")

    async def upload_artwork(self, data, matte="none"):
        result = await self._call(
            self.art.upload, data, matte=matte, portrait_matte=matte, file_type="PNG"
        )
        if not isinstance(result, str) or not re.fullmatch(
            r"MY[-_][A-Za-z0-9_-]+(?:\.(?:png|jpg|jpeg))?", result
        ):
            raise ValueError("TV did not return a personal artwork identifier")
        return result.rsplit(".", 1)[0]

    async def delete_owned_artwork(self, content_id):
        # Ownership and fingerprint must be checked by calibration service first.
        await self._call(self.art.delete, content_id)
