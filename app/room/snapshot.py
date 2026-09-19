"""Local geometric TV detection for ordinary room snapshots; no model or cloud call."""

import itertools

import cv2
import numpy as np


def intersection(a, b):
    a1 = np.cross([a[0], a[1], 1], [a[2], a[3], 1])
    b1 = np.cross([b[0], b[1], 1], [b[2], b[3], 1])
    point = np.cross(a1, b1)
    if abs(point[2]) < 1e-6:
        return None
    return point[:2] / point[2]


def detect_tv(rgb):
    """Score quadrilaterals supported by long near-horizontal/vertical frame edges.

    Conservative for roughly upright phone photographs. Ambiguous geometry should
    be confirmed with four taps; this is not semantic recognition of a television.
    """
    scale = min(1, 1200 / max(rgb.shape[:2]))
    small = cv2.resize(rgb, None, fx=scale, fy=scale) if scale < 1 else rgb
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    detected = cv2.createLineSegmentDetector().detect(gray)[0]
    if detected is None:
        raise ValueError("Could not locate the TV. Tap its four corners to continue.")
    lines = detected.reshape(-1, 4)
    horizontal, vertical = [], []
    for line in lines:
        dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
        length = np.hypot(dx, dy)
        if length < min(h, w) * 0.065:
            continue
        if dy < dx * 0.3:
            horizontal.append((length, line))
        elif dx < dy * 0.3:
            vertical.append((length, line))
    horizontal = [line for _, line in sorted(horizontal, key=lambda p: -p[0])[:35]]
    vertical = [line for _, line in sorted(vertical, key=lambda p: -p[0])[:25]]
    edges = cv2.Canny(gray, 35, 110)
    distances = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3)
    candidates = []
    for first, second in itertools.combinations(vertical, 2):
        left, right = sorted((first, second), key=lambda p: (p[0] + p[2]) / 2)
        width = (right[0] + right[2] - left[0] - left[2]) / 2
        if not 0.18 * w < width < 0.94 * w:
            continue
        for a, b in itertools.combinations(horizontal, 2):
            top, bottom = sorted((a, b), key=lambda p: (p[1] + p[3]) / 2)
            height = (bottom[1] + bottom[3] - top[1] - top[3]) / 2
            if height < h * 0.07 or not 1.35 < width / height < 2.25:
                continue
            # Segment centers should actually lie near the proposed sides.
            if any(
                not left[[0, 2]].mean() - 15 < p[[0, 2]].mean() < right[[0, 2]].mean() + 15
                for p in (top, bottom)
            ):
                continue
            if any(
                not top[[1, 3]].mean() - 20 < p[[1, 3]].mean() < bottom[[1, 3]].mean() + 20
                for p in (left, right)
            ):
                continue
            points = [
                intersection(top, left),
                intersection(top, right),
                intersection(bottom, right),
                intersection(bottom, left),
            ]
            if any(p is None for p in points):
                continue
            quad = np.float32(points)
            if np.any(quad < 2) or np.any(quad[:, 0] >= w - 2) or np.any(quad[:, 1] >= h - 2):
                continue
            area = cv2.contourArea(quad)
            if not 0.035 < area / (h * w) < 0.65:
                continue
            support = []
            for i in range(4):
                samples = np.linspace(quad[i], quad[(i + 1) % 4], 100).astype(int)
                support.append(float(np.mean(distances[samples[:, 1], samples[:, 0]] < 3)))
            if min(support) < 0.45:
                continue
            aspect = width / height
            score = 0.65 * np.mean(support) + 0.25 * np.exp(-(((aspect - 16 / 9) / 0.3) ** 2))
            # Weak preference for a central screen; never a fixed screen position.
            score += 0.10 * (1 - abs(quad[:, 0].mean() / w - 0.5))
            candidates.append((float(score), quad))
    if not candidates:
        raise ValueError("Could not locate the TV. Tap its four corners to continue.")
    candidates.sort(key=lambda item: -item[0])
    best_score, best = candidates[0]
    # Deduplicate line-fragment proposals before measuring ambiguity.
    rivals = [
        score
        for score, q in candidates[1:]
        if np.linalg.norm(q.mean(axis=0) - best.mean(axis=0)) > 0.15 * w
    ]
    confidence = min(0.78, best_score * 0.78)
    if rivals and best_score - max(rivals) < 0.04:
        confidence *= 0.65
    return best / scale, confidence


def wall_near_tv(shape, corners):
    """Sample above and beside the frame, avoiding furniture below the screen."""
    transform = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), np.float32(corners)
    )
    mask = np.zeros(shape[:2], np.uint8)
    for box in [(0.04, -0.3, 0.96, -0.055), (-0.16, 0.05, -0.035, 0.75), (1.035, 0.05, 1.16, 0.75)]:
        x1, y1, x2, y2 = box
        polygon = cv2.perspectiveTransform(
            np.float32([[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]]), transform
        )[0]
        cv2.fillConvexPoly(mask, np.rint(polygon).astype(np.int32), 255)
    return mask > 0
