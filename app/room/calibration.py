import hashlib
import logging

import cv2
import numpy as np
from PIL import Image

from app.artwork.analyzer import load_image
from app.artwork.palette import delta_e, hex_color, palette, to_lab, to_rgb
from app.room.masking import automatic_mask, refine_mask
from app.room.pattern import MARKERS, PATCHES, SIZE, generate, patch_box
from app.room.snapshot import detect_tv, wall_near_tv
from app.room.surroundings import surrounding_palette

log = logging.getLogger(__name__)


def detect_screen(rgb):
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    if ids is None or not {0, 1, 2, 3}.issubset(set(ids.flatten())):
        raise ValueError(
            "Cannot find all four reference markers. Include the whole TV, avoid glare, "
            "and ensure the calibration image is displayed."
        )
    source, target = [], []
    for marker, ident in zip(corners, ids.flatten(), strict=True):
        if ident > 3:
            continue
        x, y = MARKERS[ident]
        source.extend([[x, y], [x + 299, y], [x + 299, y + 299], [x, y + 299]])
        target.extend(marker[0])
    homography, inliers = cv2.findHomography(np.float32(source), np.float32(target), cv2.RANSAC, 3)
    if homography is None or inliers.sum() < 12:
        raise ValueError("Screen geometry is uncertain; retake the photograph")
    plane = np.float32([[[0, 0], [3839, 0], [3839, 2159], [0, 2159]]])
    screen = cv2.perspectiveTransform(plane, homography)[0]
    corrected = cv2.warpPerspective(rgb, np.linalg.inv(homography), SIZE)
    return screen, corrected


def fit_correction(observed, expected):
    """Regularized affine camera/scene correction, with held-out error estimate."""
    x = np.c_[np.asarray(observed) / 255, np.ones(len(observed))]
    y = np.asarray(expected) / 255
    if np.linalg.matrix_rank(x) < 4:
        raise ValueError("Color references are not distinguishable")
    prior = np.vstack([np.eye(3), np.zeros(3)])
    ridge = 0.002
    matrix = np.linalg.solve(x.T @ x + ridge * np.eye(4), x.T @ y + ridge * prior)
    errors = []
    for i in range(len(x)):
        train = np.arange(len(x)) != i
        m = np.linalg.solve(
            x[train].T @ x[train] + ridge * np.eye(4), x[train].T @ y[train] + ridge * prior
        )
        pred = np.clip(x[i] @ m, 0, 1) * 255
        errors.append(float(delta_e(to_lab(pred), to_lab(expected[i]))))
    return matrix, float(np.median(errors))


def apply_correction(rgb, matrix):
    shape = rgb.shape
    flat = rgb.reshape(-1, 3).astype(float) / 255
    return np.clip(np.c_[flat, np.ones(len(flat))] @ matrix * 255, 0, 255).reshape(shape)


def describe(lab, variation):
    return [
        "Warm" if lab[2] > 4 else "Cool" if lab[2] < -4 else "Neutral",
        "Light" if lab[0] > 75 else "Medium-light" if lab[0] > 50 else "Dark",
        "Low saturation" if np.linalg.norm(lab[1:]) < 18 else "Colorful",
        "Low contrast"
        if variation < 6
        else "Moderate contrast"
        if variation < 15
        else "High contrast",
    ]


def measure(rgb, mask, matrix, error):
    pixels = rgb[mask]
    if len(pixels) < 500:
        raise ValueError("Select at least 500 wall pixels")
    # Limit compute on high resolution photographs, without changing masks.
    pixels = pixels[:: max(1, len(pixels) // 30000)]
    corrected = apply_correction(pixels, matrix)
    labs = to_lab(corrected)
    lab = np.median(labs, axis=0)
    variability = float(np.median(delta_e(labs, lab)))
    cast = np.median(to_lab(pixels) - labs, axis=0)
    surrounding = palette(corrected)
    confidence = float(np.clip(0.90 - error / 55 - variability / 100, 0.05, 0.90))
    return {
        "wall_lab": lab.tolist(),
        "wall_hex": hex_color(to_rgb(lab)),
        "lightness": float(lab[0]),
        "chroma": float(np.linalg.norm(lab[1:])),
        "warmth": float(lab[2]),
        "brightness": float(to_lab(pixels)[:, 0].mean()),
        "ambient_cast": cast.tolist(),
        "palette": surrounding,
        "neutral_palette": [p for p in surrounding if np.linalg.norm(p["lab"][1:]) < 18],
        "contrast": float(np.std(labs[:, 0])),
        "variability": variability,
        "confidence": round(confidence, 2),
        "reference_error_delta_e": error,
        "descriptors": describe(lab, variability),
        "source": "guided",
    }


class RoomCalibrationService:
    def __init__(self, db):
        self.db = db
        self.directory = db.directory / "room"
        self.directory.mkdir(exist_ok=True)

    @staticmethod
    def snapshot_metadata(result, confidence):
        result.update(
            source="snapshot",
            reference_error_delta_e=None,
            ambient_cast=None,
            color_corrected=False,
            detection_confidence=confidence,
            confidence=round(
                min(0.60, confidence * 0.75) * max(0.4, 1 - result["variability"] / 60), 2
            ),
        )
        return result

    def preview(self, rgb, mask, corners, profile):
        overlay = rgb.copy()
        overlay[mask] = (overlay[mask] * 0.75 + np.array([55, 170, 100]) * 0.25).astype(np.uint8)
        cv2.polylines(overlay, [np.rint(corners).astype(np.int32)], True, (245, 215, 115), 3)
        filename = f"{profile}-detection.png"
        Image.fromarray(overlay).save(self.directory / filename)
        return filename

    def snapshot(self, data, profile, normalized_corners=None):
        """An ordinary room photo needs no television operation or reference artwork."""
        image = load_image(data)
        image.thumbnail((2400, 1800))
        rgb = np.array(image)
        if normalized_corners is None:
            corners, confidence = detect_tv(rgb)
            if confidence < 0.5:
                raise ValueError("TV detection is ambiguous. Tap its four corners to continue.")
        else:
            points = np.asarray(normalized_corners, dtype=float)
            if (
                points.shape != (4, 2)
                or not np.isfinite(points).all()
                or np.any(points < 0)
                or np.any(points > 1)
            ):
                raise ValueError("Provide four TV corners inside the photo")
            corners = (points * [image.width, image.height]).astype(np.float32)
            if (
                not cv2.isContourConvex(corners)
                or cv2.contourArea(corners) < image.width * image.height * 0.015
            ):
                raise ValueError("Tap the four TV corners in clockwise order, starting at top left")
            confidence = 0.75
        mask = refine_mask(rgb, wall_near_tv(rgb.shape, corners))
        matrix = np.vstack([np.eye(3), np.zeros(3)])
        result = self.snapshot_metadata(measure(rgb, mask, matrix, 0), confidence)
        result.update(surrounding_palette(rgb, corners, result["wall_lab"], matrix))
        image.save(self.directory / f"{profile}.png")
        Image.fromarray(mask.astype(np.uint8) * 255).save(self.directory / f"{profile}-mask.png")
        result.update(
            corners=corners.tolist(),
            matrix=matrix.tolist(),
            photo=f"{profile}.png",
            mask=f"{profile}-mask.png",
            detection=self.preview(rgb, mask, corners, profile),
        )
        self.db.put("rooms", profile, result)
        log.info("CALIBRATION_COMPLETED source=snapshot")
        return result

    def process(self, data, profile):
        image = load_image(data)
        image.thumbnail((2400, 1800))
        rgb = np.array(image)
        corners, plane = detect_screen(rgb)
        observed = []
        for i in range(len(PATCHES)):
            x1, y1, x2, y2 = patch_box(i)
            observed.append(np.median(plane[y1 + 35 : y2 - 35, x1 + 35 : x2 - 35], axis=(0, 1)))
        matrix, error = fit_correction(observed, PATCHES)
        region = automatic_mask(rgb.shape, corners)
        mask = refine_mask(rgb, region)
        result = measure(rgb, mask, matrix, error)
        result.update(surrounding_palette(rgb, corners, result["wall_lab"], matrix))
        image.save(self.directory / f"{profile}.png")  # Strip EXIF/location metadata.
        Image.fromarray(mask.astype(np.uint8) * 255).save(self.directory / f"{profile}-mask.png")
        result.update(
            {
                "corners": corners.tolist(),
                "matrix": matrix.tolist(),
                "photo": f"{profile}.png",
                "mask": f"{profile}-mask.png",
            }
        )
        self.db.put("rooms", profile, result)
        log.info("CALIBRATION_COMPLETED")
        return result

    def remask(self, profile, data=None):
        old = self.db.get("rooms", profile)
        if not old or old.get("source") not in ("guided", "snapshot"):
            raise ValueError("Upload a room photo first")
        rgb = np.array(Image.open(self.directory / f"{profile}.png").convert("RGB"))
        if data:
            mask_image = load_image(data)
            if mask_image.size != (rgb.shape[1], rgb.shape[0]):
                raise ValueError("Mask dimensions do not match the photograph")
            mask = np.array(mask_image)[:, :, 0] > 127
            # Never sample the screen, even if painted over accidentally.
            tv = np.zeros(mask.shape, np.uint8)
            cv2.fillConvexPoly(tv, np.int32(old["corners"]), 255)
            mask &= tv == 0
        else:
            region = (
                wall_near_tv(rgb.shape, old["corners"])
                if old["source"] == "snapshot"
                else automatic_mask(rgb.shape, old["corners"])
            )
            mask = refine_mask(rgb, region)
        result = {
            **old,
            **measure(rgb, mask, np.array(old["matrix"]), old["reference_error_delta_e"] or 0),
        }
        if old["source"] == "snapshot":
            result = self.snapshot_metadata(result, old["detection_confidence"])
        result.update(
            surrounding_palette(rgb, old["corners"], result["wall_lab"], np.array(old["matrix"]))
        )
        result["detection"] = self.preview(rgb, mask, old["corners"], profile)
        Image.fromarray(mask.astype(np.uint8) * 255).save(self.directory / f"{profile}-mask.png")
        self.db.put("rooms", profile, result)
        return result

    async def start(self, client):
        if self.db.get("calibration", "active"):
            raise ValueError("Finish the existing calibration session first")
        if await client.get_art_mode() != "on":
            raise ValueError("Display Art Mode before starting calibration")
        original = await client.get_current_artwork()
        state = {"original": original, "artmode": "on", "phase": "uploading"}
        self.db.put("calibration", "active", state)  # Journal before any mutation.
        data = generate()
        raw = await client.get_available_mattes()
        families = [t.get("matte_type") for t in raw["matte_types"]]
        matte = "none" if "none" in families else original.get("matte_id")
        try:
            cid = await client.upload_artwork(data, matte)
            self.db.put(
                "owned",
                cid,
                {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "kind": "calibration-v1",
                    "matte": matte,
                    "device": self.db.get("config", "tv_ip", "mock"),
                },
            )
            state.update({"content_id": cid, "matte": matte, "phase": "displaying"})
            self.db.put("calibration", "active", state)
            await client.select_artwork(cid)
        except Exception:
            state["phase"] = "interrupted"
            self.db.put("calibration", "active", state)
            raise
        log.info("CALIBRATION_STARTED")
        return state

    async def finish(self, client):
        state = self.db.get("calibration", "active")
        if state and state.get("content_id"):
            current = await client.get_current_artwork()
            if current["content_id"] == state["content_id"]:
                await client.select_artwork(state["original"]["content_id"])
        self.db.put("calibration", "active", None)

    async def remove_owned(self, client, cid):
        owned = self.db.get("owned", cid)
        if not owned or owned.get("kind") != "calibration-v1" or owned.get("deleted"):
            raise ValueError(
                "This artwork is not a positively identified application calibration asset"
            )
        if owned.get("device") != self.db.get("config", "tv_ip", "mock"):
            raise ValueError("This calibration image belongs to a different television")
        if owned["sha256"] != hashlib.sha256(generate()).hexdigest():
            raise ValueError("Calibration pattern fingerprint differs; deletion refused")
        if (await client.get_current_artwork())["content_id"] == cid:
            raise ValueError("Finish calibration before removing the displayed image")
        # IDs can be reused after external deletion. Confirm the asset still on the TV.
        thumbnail = await client.get_artwork_thumbnail(cid)
        _, plane = detect_screen(np.array(load_image(thumbnail)))
        expected = np.array(load_image(generate()))
        actual_small = cv2.resize(plane, (320, 180)).astype(float)
        expected_small = cv2.resize(expected, (320, 180)).astype(float)
        if np.mean(np.abs(actual_small - expected_small)) > 18:
            raise ValueError(
                "TV image no longer matches the application reference; deletion refused"
            )
        await client.delete_owned_artwork(cid)
        self.db.put("owned", cid, {**owned, "deleted": True})
