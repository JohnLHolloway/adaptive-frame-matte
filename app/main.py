import asyncio
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import time
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from astral.geocoder import all_locations, database
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from app import __version__, config
from app.artwork.palette import to_lab
from app.room.pattern import generate
from app.room.profiles import quick_profile
from app.samsung.discovery import discover, validate_ip
from app.samsung.mock import MockFrameClient
from app.services.televisions import TelevisionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
ROOT = Path(__file__).parent / "web"


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    automation: bool | None = None
    strategy: str | None = None
    threshold: float | None = Field(None, ge=0, le=100)
    cooldown: int | None = Field(None, ge=0, le=86400)
    neutral_preference: float | None = Field(None, ge=0, le=3)
    accent_influence: float | None = Field(None, ge=0, le=10)
    weights: dict[str, float] | None = None
    profile_mode: str | None = None
    schedule: str | None = None
    sun_offset_minutes: int | None = Field(None, ge=-360, le=360)
    day_start: str | None = None
    night_start: str | None = None
    timezone: str | None = None
    location_label: str | None = Field(None, max_length=120)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    fallback: str | None = None
    safe_matte: str | None = None
    requires_reselect: bool | None = None
    preferred_family: str | None = None
    preferred_family_only: bool | None = None
    setup_complete: bool | None = None


def create_app(directory=None, mock=None):
    directory = Path(directory) if directory else config.DATA
    mock = config.MOCK if mock is None else mock

    selected_tv = ContextVar("selected_tv", default="primary")

    @asynccontextmanager
    async def lifespan(app):
        manager = TelevisionManager(directory, mock)
        app.state.televisions = manager
        await manager.start()
        primary = manager.runtimes["primary"]
        app.state.db, app.state.watcher = primary.db, primary.watcher
        app.state.csrf = secrets.token_urlsafe(32)
        try:
            yield
        finally:
            await manager.close()

    app = FastAPI(
        title="Adaptive Frame Matte",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")

    @app.middleware("http")
    async def security(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "Cross-origin writes are not allowed"}, status_code=403
                )
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), app.state.csrf):
                return JSONResponse(
                    {"detail": "Reload the page before making changes"}, status_code=403
                )
            if int(request.headers.get("content-length", "0")) > config.MAX_UPLOAD + 65536:
                return JSONResponse({"detail": "Upload exceeds 20 MB"}, status_code=413)
        identifier = request.headers.get("x-frame-id", request.query_params.get("tv", "primary"))
        if identifier not in app.state.televisions.runtimes:
            return JSONResponse({"detail": "Unknown television"}, status_code=404)
        context = selected_tv.set(identifier)
        try:
            response = await call_next(request)
        finally:
            selected_tv.reset(context)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        # Never serialize raw Samsung exceptions: they may contain tokens/URLs/device identifiers.
        logging.getLogger(__name__).warning("REQUEST_FAILED %s", type(exc).__name__)
        return JSONResponse(
            {"detail": "Operation failed. Check TV connectivity and Diagnostics."}, status_code=503
        )

    def runtime():
        return app.state.televisions.runtimes[selected_tv.get()]

    def watcher():
        return runtime().watcher

    def db():
        return runtime().db

    def client():
        if not watcher().client:
            raise ValueError("Connect to a Frame in Setup first")
        return watcher().client

    def profile_name(value):
        if value not in ("day", "night"):
            raise ValueError("Choose day or night")
        return value

    async def image_bytes(file):
        data = await file.read(config.MAX_UPLOAD + 1)
        if len(data) > config.MAX_UPLOAD:
            raise ValueError("Upload exceeds 20 MB")
        return data

    @app.get("/healthz")
    async def health():
        db().connection.execute("SELECT 1")
        return {"status": "ok", "version": __version__}

    @app.get("/api/state")
    async def state():
        w = watcher()
        caps = db().get("config", "capabilities", {})
        if w.client:
            caps["websocket_events"] = sorted(w.client.observed_events)
        return {
            **w.state,
            "settings": w.settings,
            "current_override": db().get(
                "overrides", w.state.get("current", {}).get("content_id", ""), {"mode": "automatic"}
            ),
            "device": db().get("config", "device", {}),
            "capabilities": caps,
            "rooms": db().all("rooms"),
            "mattes": w.catalog.all(),
            "tv_id": selected_tv.get(),
            "televisions": app.state.televisions.list(),
            "history": db().history(),
            "mock": mock,
            "version": __version__,
            "calibration": db().get("calibration", "active"),
            "owned": db().all("owned"),
        }

    @app.post("/api/discover")
    async def discovery(request: Request):
        payload = await request.json()
        results = (
            [await client().get_device_info()]
            if mock
            else await discover(payload.get("subnet") or None)
        )
        logging.getLogger(__name__).info("TV_DISCOVERED count=%d", len(results))
        return results

    @app.post("/api/televisions")
    async def add_television(request: Request):
        identifier = await app.state.televisions.add((await request.json()).get("name"))
        return {"id": identifier}

    @app.post("/api/television/name")
    async def rename_television(request: Request):
        name = TelevisionManager.name((await request.json()).get("name"))
        app.state.televisions.registry.put("televisions", selected_tv.get(), {"name": name})
        return {"ok": True}

    @app.get("/api/artworks")
    async def artworks(q: str = "", behavior: str = "all", page: int = 1, size: int = 24):
        if len(q) > 100 or behavior not in ("all", "automatic", "force", "never"):
            raise ValueError("Invalid artwork filter")
        if page < 1 or not 1 <= size <= 48:
            raise ValueError("Invalid artwork page")
        return db().artwork_page(q, behavior, page, size)

    @app.post("/api/connect")
    async def connect(request: Request):
        ip = validate_ip((await request.json()).get("ip", "")) if not mock else None
        w = watcher()
        async with app.state.televisions.lock, w.lock:
            if ip and any(
                r.db.get("config", "tv_ip") == ip and key != selected_tv.get()
                for key, r in app.state.televisions.runtimes.items()
            ):
                raise ValueError("This TV is already configured; select it from the TV menu")
            if db().get("calibration", "active"):
                raise ValueError("Finish calibration before changing televisions")
            if w.client:
                await w.client.close()
            if mock:
                w.client = MockFrameClient()
            else:
                from app.samsung.client import SamsungClient

                w.client = SamsungClient(ip, db().directory / "tokens")
            await w.client.pair()
            old_ip = db().get("config", "tv_ip")
            if ip != old_ip:
                db().put("config", "capabilities", {})
                w.save_settings({"automation": False, "requires_reselect": False})
            db().put("config", "tv_ip", ip)
            await w.refresh_capabilities()
            current = await w.client.get_current_artwork()
            mode = await w.client.get_art_mode()
            w.state.update(current=current, artmode=mode, connected=True, error=None)
            w.key = None
        logging.getLogger(__name__).info("TV_PAIRED")
        return {"paired": True}

    @app.post("/api/capabilities")
    async def capabilities():
        async with watcher().lock:
            await watcher().refresh_capabilities()
        return {"ok": True}

    @app.post("/api/action/{action}")
    async def action(action):
        w = watcher()
        if action in ("pause", "resume"):
            w.save_settings({"automation": action == "resume"})
        elif action in ("evaluate", "apply"):
            await w.tick(force=True, apply=action == "apply")
        elif action == "reset":
            w.save_settings(
                {
                    k: config.DEFAULTS[k]
                    for k in (
                        "strategy",
                        "weights",
                        "neutral_preference",
                        "threshold",
                        "accent_influence",
                    )
                }
            )
        else:
            raise ValueError("Unknown action")
        return {"ok": True, "message": w.state.get("message")}

    @app.get("/api/locations")
    async def locations(q: str = ""):
        query = q.strip().casefold()[:100]
        if len(query) < 2:
            return []
        matches = [
            loc
            for loc in all_locations(database())
            if query in f"{loc.name} {loc.region}".casefold()
        ]
        matches.sort(key=lambda loc: (not loc.name.casefold().startswith(query), loc.name))
        return [
            {
                "name": loc.name,
                "region": loc.region,
                "timezone": loc.timezone,
                "latitude": round(loc.latitude, 2),
                "longitude": round(loc.longitude, 2),
            }
            for loc in matches[:30]
        ]

    @app.post("/api/recommendations/apply")
    async def apply_choice(request: Request):
        data = await request.json()
        await watcher().apply_choice(
            data.get("content_id"), data.get("matte_id"), data.get("remember") is True
        )
        return {"ok": True}

    @app.post("/api/settings")
    async def settings(update: SettingsUpdate):
        values = update.model_dump(exclude_none=True)
        choices = {
            "strategy": ("Adaptive", "Subtle", "Contrast", "Gallery"),
            "profile_mode": ("auto", "day", "night"),
            "schedule": ("fixed", "sun"),
            "fallback": ("retain", "safe"),
        }
        for key, options in choices.items():
            if key in values and values[key] not in options:
                raise ValueError(f"Invalid {key}")
        for key in ("day_start", "night_start"):
            if key in values:
                time.fromisoformat(values[key])
        if "timezone" in values:
            try:
                ZoneInfo(values["timezone"])
            except Exception:
                raise ValueError("Use a valid IANA timezone, such as America/New_York") from None
        if "weights" in values:
            weights = values["weights"]
            if (
                set(weights) != set(config.DEFAULTS["weights"])
                or any(not 0 <= v <= 100 for v in weights.values())
                or sum(weights.values()) <= 0
            ):
                raise ValueError("Set all six weights between 0 and 100, with a positive total")
        merged = {**watcher().settings, **values}
        if merged["schedule"] == "sun" and (
            merged["latitude"] is None or merged["longitude"] is None
        ):
            raise ValueError("Sunrise/sunset needs approximate latitude and longitude")
        family = merged.get("preferred_family")
        if family and family not in {m["family"] for m in watcher().catalog.all()}:
            raise ValueError("Choose a style advertised by this TV")
        if merged.get("preferred_family_only") and not family:
            raise ValueError("Choose a style before restricting automatic recommendations")
        watcher().save_settings(values)
        return {"ok": True}

    @app.post("/api/room/{profile}/quick")
    async def quick(profile, request: Request):
        db().put("rooms", profile_name(profile), quick_profile((await request.json())["color"]))
        watcher().key = None
        return {"ok": True}

    @app.post("/api/room/{profile}/photo")
    async def photo(profile, file: UploadFile):
        result = await asyncio.to_thread(
            runtime().calibration.process, await image_bytes(file), profile_name(profile)
        )
        watcher().key = None
        return result

    @app.post("/api/room/{profile}/snapshot")
    async def snapshot(profile: str, file: UploadFile, corners: str | None = Form(None)):
        points = json.loads(corners) if corners else None
        result = await asyncio.to_thread(
            runtime().calibration.snapshot, await image_bytes(file), profile_name(profile), points
        )
        watcher().key = None
        return result

    @app.post("/api/room/{profile}/mask")
    async def mask(profile, file: UploadFile):
        result = await asyncio.to_thread(
            runtime().calibration.remask, profile_name(profile), await image_bytes(file)
        )
        watcher().key = None
        return result

    @app.post("/api/room/{profile}/reset-mask")
    async def reset_mask(profile):
        return await asyncio.to_thread(runtime().calibration.remask, profile_name(profile))

    @app.get("/calibration-pattern.png")
    async def pattern():
        return Response(generate(), media_type="image/png")

    @app.post("/api/calibration/{action}")
    async def calibration(action, request: Request):
        async with watcher().lock:
            service = runtime().calibration
            if action == "start":
                result = await service.start(client())
            elif action == "finish":
                result = await service.finish(client())
            elif action == "remove":
                result = await service.remove_owned(client(), (await request.json())["content_id"])
            else:
                raise ValueError("Unknown calibration action")
            watcher().key = None
        return result or {"ok": True}

    @app.post("/api/override")
    async def override(request: Request):
        data = await request.json()
        cid, mode = str(data["content_id"]), data["mode"]
        if cid not in db().all("artwork") or mode not in ("automatic", "force", "never"):
            raise ValueError("Invalid artwork override")
        if mode == "force" and data.get("matte") not in {m["id"] for m in watcher().catalog.all()}:
            raise ValueError("Choose a discovered matte")
        db().put("overrides", cid, {"mode": mode, "matte": data.get("matte")})
        watcher().key = None
        return {"ok": True}

    @app.post("/api/matte")
    async def matte(request: Request):
        data = await request.json()
        row = db().get("mattes", data["id"])
        if not row or data.get("preference", "normal") not in ("normal", "preferred", "avoid"):
            raise ValueError("Invalid matte")
        row.update(
            enabled=bool(data.get("enabled", row["enabled"])),
            preference=data.get("preference", row["preference"]),
        )
        if data.get("hex"):
            color = data["hex"]
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Use #RRGGBB")
            row.update(
                hex=color,
                lab=to_lab([int(color[i : i + 2], 16) for i in (1, 3, 5)]).tolist(),
                source="User calibrated",
            )
        db().put("mattes", row["id"], row)
        watcher().key = None
        return {"ok": True}

    @app.post("/api/mattes/bulk")
    async def matte_group(request: Request):
        data = await request.json()
        field = data.get("field")
        if field not in ("family", "color"):
            raise ValueError("Choose a discovered style or color")
        rows = [r for r in watcher().catalog.all() if r[field] == data.get("value")]
        if not rows:
            raise ValueError("Unknown matte group")
        preference = data.get("preference", "normal")
        if preference not in ("normal", "preferred", "avoid"):
            raise ValueError("Invalid preference")
        color = data.get("hex")
        if color and (field != "color" or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
            raise ValueError("A measured color must use #RRGGBB")
        for row in rows:
            row.update(enabled=bool(data.get("enabled", True)), preference=preference)
            if color:
                row.update(
                    hex=color,
                    source="User calibrated",
                    lab=to_lab([int(color[i : i + 2], 16) for i in (1, 3, 5)]).tolist(),
                )
            db().put("mattes", row["id"], row)
        watcher().key = None
        return {"ok": True, "updated": len(rows)}

    @app.post("/api/artwork/{content_id}/image")
    async def local_art(content_id, file: UploadFile):
        if content_id not in db().all("artwork"):
            raise ValueError("Unknown artwork")
        watcher().provider.store_local(content_id, await image_bytes(file))
        watcher().key = None
        return {"ok": True}

    @app.post("/api/mock/next")
    async def mock_next():
        if not mock:
            raise HTTPException(404)
        c = client()
        ids = list(c.images)
        await c.select_artwork(ids[(ids.index(c.current) + 1) % len(ids)])
        return {"ok": True}

    @app.get("/media/{category}/{filename}")
    async def media(category, filename):
        if (
            category not in ("room", "artwork")
            or not re.fullmatch(r"[a-zA-Z0-9.-]+\.png", filename)
            or ".." in filename
        ):
            raise HTTPException(404)
        path = db().directory / category / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png")

    @app.get("/{page:path}", response_class=HTMLResponse)
    async def page(request: Request, page=""):
        if page not in (
            "",
            "setup",
            "room",
            "artwork",
            "mattes",
            "strategy",
            "history",
            "diagnostics",
            "settings",
            "televisions",
        ):
            raise HTTPException(404)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"csrf": app.state.csrf, "page": page or "dashboard"},
        )

    return app


app = create_app()
