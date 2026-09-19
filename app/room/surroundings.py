"""Measure contextual palettes separately from wall pixels and screen content."""

import cv2
import numpy as np

from app.artwork.palette import delta_e, palette, to_lab


def surrounding_palette(rgb, corners, wall_lab, matrix):
    transform = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), np.float32(corners)
    )
    region = np.zeros(rgb.shape[:2], np.uint8)
    outside = cv2.perspectiveTransform(
        np.float32([[[-0.55, -0.35], [1.55, -0.35], [1.55, 2.4], [-0.55, 2.4]]]), transform
    )[0]
    cv2.fillConvexPoly(region, np.rint(outside).astype(np.int32), 255)
    # Exclude the screen plus a small bezel margin, so movie/art colors never become decor.
    screen = cv2.perspectiveTransform(
        np.float32([[[-0.025, -0.035], [1.025, -0.035], [1.025, 1.035], [-0.025, 1.035]]]),
        transform,
    )[0]
    cv2.fillConvexPoly(region, np.rint(screen).astype(np.int32), 0)
    pixels = rgb[region > 0]
    if len(pixels) < 100:
        return {"surrounding_palette": [], "accent_palette": [], "surrounding_neutrals": []}
    pixels = pixels[:: max(1, len(pixels) // 40000)].astype(float)
    corrected = np.clip(np.c_[pixels / 255, np.ones(len(pixels))] @ matrix * 255, 0, 255)
    lab = to_lab(corrected)
    usable = (lab[:, 0] > 10) & (lab[:, 0] < 95)
    accents = usable & (np.linalg.norm(lab[:, 1:], axis=1) > 9) & (delta_e(lab, wall_lab) > 9)
    overall = palette(corrected[usable]) if usable.sum() > 100 else []
    accent_colors = palette(corrected[accents]) if accents.sum() > 100 else []
    # Suppress tiny noisy clusters; percentages are within the accent population.
    accent_colors = [c for c in accent_colors if c["percentage"] >= 3]
    total = sum(c["percentage"] for c in accent_colors)
    for color in accent_colors:
        color["percentage"] = round(color["percentage"] / total * 100, 2)
    return {
        "surrounding_palette": overall,
        "accent_palette": accent_colors,
        "surrounding_neutrals": [c for c in overall if np.linalg.norm(c["lab"][1:]) < 18],
        "accent_fraction": float(accents.sum() / max(1, usable.sum())),
    }
