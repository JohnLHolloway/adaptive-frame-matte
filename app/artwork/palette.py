import numpy as np
from skimage.color import deltaE_ciede2000, lab2rgb, rgb2lab


def to_lab(rgb):
    return rgb2lab(np.asarray(rgb, dtype=float) / 255)


def to_rgb(lab):
    return np.rint(np.clip(lab2rgb(np.asarray(lab, dtype=float)), 0, 1) * 255).astype(int)


def delta_e(first, second):
    first, second = np.broadcast_arrays(
        np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    )
    return deltaE_ciede2000(first, second)


def hex_color(rgb):
    return "#" + "".join(f"{int(v):02x}" for v in np.clip(rgb, 0, 255))


def palette(pixels, count=5):
    """Deterministic, weighted LAB clustering of quantized sRGB bins."""
    pixels = np.asarray(pixels).reshape(-1, 3)
    bins, inverse, weights = np.unique(
        (pixels // 16).astype(int), axis=0, return_inverse=True, return_counts=True
    )
    means = np.array(
        [
            np.bincount(inverse, weights=pixels[:, c], minlength=len(bins)) / weights
            for c in range(3)
        ]
    ).T
    labs = to_lab(means)
    centers = [labs[np.argmax(weights)]]
    for _ in range(min(count, len(labs)) - 1):
        dist = np.min(np.sum((labs[:, None] - np.array(centers)) ** 2, axis=2), axis=1)
        centers.append(labs[np.argmax(dist * weights)])
    centers = np.array(centers)
    for _ in range(15):
        labels = np.argmin(np.sum((labs[:, None] - centers) ** 2, axis=2), axis=1)
        updated = centers.copy()
        for i in range(len(centers)):
            mask = labels == i
            if mask.any():
                updated[i] = np.average(labs[mask], weights=weights[mask], axis=0)
        if np.allclose(updated, centers, atol=0.1):
            break
        centers = updated
    result = []
    for i, center in enumerate(centers):
        share = float(weights[labels == i].sum() / weights.sum())
        if share:
            result.append(
                {
                    "lab": center.tolist(),
                    "hex": hex_color(to_rgb(center)),
                    "percentage": round(100 * share, 2),
                }
            )
    return sorted(result, key=lambda x: -x["percentage"])
