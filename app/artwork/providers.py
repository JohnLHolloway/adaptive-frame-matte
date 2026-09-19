import hashlib
import logging
from io import BytesIO

from app.artwork.analyzer import ArtworkAnalyzer, load_image

log = logging.getLogger(__name__)


class ArtworkImageProvider:
    def __init__(self, db):
        self.db = db
        self.directory = db.directory / "artwork"
        self.directory.mkdir(exist_ok=True)

    async def acquire(self, client, content_id):
        key = hashlib.sha256(content_id.encode()).hexdigest()
        data = None
        source = "tv"
        try:
            data = await client.get_artwork_thumbnail(content_id)
            load_image(data)
            log.info("THUMBNAIL_RECEIVED")
        except Exception:
            data = None
            log.info("THUMBNAIL_UNAVAILABLE")
        if not data:
            for filename in (key + ".local.png", key + ".png"):
                path = self.directory / filename
                if path.exists():
                    data = path.read_bytes()
                    source = "local" if ".local." in filename else "cache"
                    break
        if not data:
            return None
        image = load_image(data)
        image.thumbnail((1024, 1024))
        out = BytesIO()
        image.save(out, format="PNG")
        data = out.getvalue()
        (self.directory / (key + ".png")).write_bytes(data)
        fingerprint = hashlib.sha256(data).hexdigest()
        cache_key = key + fingerprint
        analysis = self.db.get("analysis", cache_key)
        if not analysis:
            analysis = ArtworkAnalyzer().analyze(data)
            self.db.put("analysis", cache_key, analysis)
            log.info("ARTWORK_ANALYZED")
        return {
            "image": key + ".png",
            "fingerprint": fingerprint,
            "analysis": analysis,
            "image_source": source,
        }

    def store_local(self, content_id, data):
        image = load_image(data)
        image.thumbnail((2048, 2048))
        key = hashlib.sha256(content_id.encode()).hexdigest()
        image.save(self.directory / (key + ".local.png"))
