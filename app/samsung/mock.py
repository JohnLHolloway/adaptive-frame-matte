import asyncio
from io import BytesIO

from PIL import Image, ImageDraw


def sample(index=0):
    colors = [
        ("#d5b99b", "#574d43", "#87967e"),
        ("#58718c", "#202f42", "#d8cfc3"),
        ("#b77b55", "#4a4640", "#c4baa0"),
    ][index % 3]
    im = Image.new("RGB", (1280, 720), colors[0])
    d = ImageDraw.Draw(im)
    d.ellipse((750, 90, 930, 270), fill="#eee5d3")
    d.polygon(
        [(0, 600), (350, 260), (700, 580), (1030, 320), (1280, 520), (1280, 720), (0, 720)],
        fill=colors[2],
    )
    d.polygon([(0, 640), (700, 520), (1280, 640), (1280, 720), (0, 720)], fill=colors[1])
    out = BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


class MockFrameClient:
    def __init__(self):
        self.current = "MY-DEMO-0"
        self.matte = "modern_polar"
        self.mode = "on"
        self.changed = asyncio.Event()
        self.observed_events = set()
        self.images = {f"MY-DEMO-{i}": sample(i) for i in range(3)}
        self.images["SAM-DEMO"] = sample(1)
        self.writes = []
        self.requires_reselect = False
        self.pending = None

    async def connect(self):
        pass

    async def pair(self):
        pass

    async def close(self):
        pass

    async def get_device_info(self):
        return {
            "name": "Demo Frame",
            "model": "Mock Frame",
            "art_supported": True,
            "api_version": "mock-1",
        }

    async def get_art_mode(self):
        return self.mode

    async def get_current_artwork(self):
        return {
            "content_id": self.current,
            "matte_id": self.matte,
            "content_type": "artstore" if self.current.startswith("SAM-") else "personal",
        }

    async def get_current_matte(self):
        return self.matte

    async def get_available_mattes(self):
        return {
            "matte_types": [{"matte_type": f} for f in ("none", "modern", "shadowbox", "flexible")],
            "matte_colors": [
                {"color": name, "R": r, "G": g, "B": b}
                for name, r, g, b in [
                    ("polar", 232, 231, 231),
                    ("warm", 231, 226, 215),
                    ("neutral", 137, 136, 134),
                    ("black", 34, 34, 33),
                    ("sage", 170, 176, 141),
                    ("navy", 39, 53, 74),
                ]
            ],
        }

    async def get_artwork_thumbnail(self, content_id):
        return self.images[content_id]

    async def set_matte(self, content_id, matte):
        if self.mode != "on" or content_id != self.current:
            raise ValueError("Art Mode is not displaying the requested artwork")
        self.writes.append((content_id, matte))
        self.pending = matte
        if not self.requires_reselect:
            self.matte = matte

    async def select_artwork(self, content_id):
        if self.mode != "on":
            raise ValueError("Art Mode is off")
        self.current = content_id
        if self.pending:
            self.matte, self.pending = self.pending, None
        self.observed_events.add("image_selected")
        self.changed.set()

    async def upload_artwork(self, data, matte="none"):
        cid = f"MY-CAL-{len(self.images)}"
        self.images[cid] = data
        return cid

    async def delete_owned_artwork(self, cid):
        del self.images[cid]
