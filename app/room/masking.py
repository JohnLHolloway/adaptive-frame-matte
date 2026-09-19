import cv2
import numpy as np


def automatic_mask(shape, corners):
    h, w = shape[:2]
    tv = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(tv, np.rint(corners).astype(np.int32), 255)
    radius = max(15, int(min(h, w) * 0.12))
    outer = cv2.dilate(tv, np.ones((radius * 2 + 1, radius * 2 + 1), np.uint8))
    gap = cv2.dilate(tv, np.ones((11, 11), np.uint8))
    return (outer > 0) & (gap == 0)


def refine_mask(rgb, mask):
    """Reject strong texture and robust color outliers; user editing remains essential."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    texture = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    smooth = cv2.GaussianBlur(texture, (9, 9), 0) < 18
    pixels = rgb[mask]
    if len(pixels) < 100:
        raise ValueError("Include more surrounding wall in the photograph")
    median = np.median(pixels, axis=0)
    distances = np.linalg.norm(rgb.astype(float) - median, axis=2)
    limit = max(25, float(np.percentile(distances[mask], 75)))
    return mask & smooth & (distances <= limit)
