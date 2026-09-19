"""Original open sRGB reference pattern. Coordinates are in a 3840x2160 plane."""

from io import BytesIO

import cv2
from PIL import Image, ImageDraw, ImageFont

SIZE = (3840, 2160)
MARKERS = [(120, 120), (3420, 120), (3420, 1740), (120, 1740)]
PATCHES = [
    (32, 32, 32),
    (80, 80, 80),
    (128, 128, 128),
    (180, 180, 180),
    (230, 230, 230),
    (255, 255, 255),
    (0, 0, 0),
    (196, 180, 158),
    (160, 180, 196),
    (180, 65, 65),
    (70, 150, 85),
    (65, 95, 180),
    (200, 160, 55),
    (150, 85, 160),
    (60, 170, 175),
    (178, 151, 142),
]


def patch_box(i):
    return (650 + (i % 8) * 320, 430 + (i // 8) * 320, 890 + (i % 8) * 320, 670 + (i // 8) * 320)


def generate():
    image = Image.new("RGB", SIZE, (128, 128, 128))
    draw = ImageDraw.Draw(image)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for i, (x, y) in enumerate(MARKERS):
        draw.rectangle((x - 35, y - 35, x + 335, y + 335), fill="white")
        marker = cv2.aruco.generateImageMarker(dictionary, i, 300)
        image.paste(Image.fromarray(marker).convert("RGB"), (x, y))
    for i, color in enumerate(PATCHES):
        draw.rectangle(patch_box(i), fill=color)
    font = ImageFont.load_default(size=62)
    draw.text((620, 1250), "ADAPTIVE FRAME MATTE", fill="white", font=font)
    draw.text((620, 1380), "Room calibration / sRGB reference 01", fill="white", font=font)
    draw.text((620, 1550), "Photograph the whole TV and surrounding wall.", fill="white", font=font)
    draw.text(
        (620, 1670), "Use your usual viewing position and room lighting.", fill="white", font=font
    )
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()
