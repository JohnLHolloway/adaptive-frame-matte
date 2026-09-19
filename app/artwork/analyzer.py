from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.artwork.palette import palette, to_lab

Image.MAX_IMAGE_PIXELS = 40_000_000


def load_image(data: bytes):
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("Image exceeds 20 MB")
    try:
        opened = Image.open(BytesIO(data))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Invalid or oversized image; use JPEG, PNG or WebP") from None
    with opened as image:
        if image.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("Use JPEG, PNG or WebP")
        if image.width * image.height > 40_000_000:
            raise ValueError("Image exceeds 40 megapixels")
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")


class ArtworkAnalyzer:
    def analyze(self, data):
        image = load_image(data)
        aspect = image.width / image.height
        image.thumbnail((256, 256))
        rgb = np.array(image)
        lab = to_lab(rgb)
        h, w = rgb.shape[:2]
        edge = np.ones((h, w), dtype=bool)
        y, x = max(1, int(h * 0.125)), max(1, int(w * 0.125))
        edge[y:-y, x:-x] = False
        mean = lab.mean(axis=(0, 1))
        edge_mean = lab[edge].mean(axis=0)
        return {
            "palette": palette(rgb),
            "edge_palette": palette(rgb[edge]),
            "average_lab": mean.tolist(),
            "lightness": float(mean[0]),
            "chroma": float(np.linalg.norm(mean[1:])),
            "warmth": float(mean[2]),
            "edge_lab": edge_mean.tolist(),
            "edge_lightness": float(edge_mean[0]),
            "edge_chroma": float(np.linalg.norm(edge_mean[1:])),
            "edge_structure": float(np.std(lab[edge, 0])),
            "aspect": aspect,
        }
