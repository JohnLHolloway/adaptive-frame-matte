import math

import numpy as np

from app.artwork.palette import delta_e

REASONS = {
    "edge": "Harmony with the artwork perimeter",
    "wall": "Separation from the wall",
    "palette": "Harmony with the artwork palette",
    "room": "Fit with the room profile",
    "lightness": "Balanced lightness transition",
    "neutral": "Restrained chroma keeps the artwork dominant",
}


def closeness(value, target, spread):
    return 100 * math.exp(-(((value - target) / spread) ** 2))


class MatteRecommendationEngine:
    def score(self, artwork, room, mattes, settings):
        result = []
        strategy = settings["strategy"]
        weights = settings["weights"].copy()
        if strategy == "Subtle":
            weights.update(edge=25, wall=15, neutral=30, lightness=15, palette=10, room=5)
        elif strategy == "Contrast":
            weights.update(edge=25, wall=35, neutral=15, lightness=10, palette=5, room=10)
        elif strategy == "Gallery":
            weights.update(edge=15, wall=15, neutral=45, lightness=10, palette=5, room=10)
        for matte in mattes:
            if not matte["enabled"] or not matte.get("supported", True):
                continue
            lab = np.array(matte["lab"])
            chroma = np.linalg.norm(lab[1:])
            edge_distance = sum(
                float(delta_e(lab, p["lab"])) * p["percentage"] / 100
                for p in artwork["edge_palette"]
            )
            art_distance = sum(
                float(delta_e(lab, p["lab"])) * p["percentage"] / 100 for p in artwork["palette"]
            )
            wall_distance = float(delta_e(lab, room["wall_lab"]))
            target_edge = 30 if strategy == "Contrast" else 10 if strategy == "Subtle" else 20
            target_wall = 32 if strategy == "Contrast" else 12 if strategy == "Subtle" else 23
            neutral = float(np.clip(100 - chroma * 2.8 * settings["neutral_preference"], 0, 100))
            if strategy == "Gallery":
                neutral = 0.8 * neutral + 0.2 * closeness(lab[0], 86, 35)
            target_l = (
                0.45 * artwork["edge_lightness"]
                + 0.35 * room["lightness"]
                + 0.20 * (82 if room["brightness"] > 50 else 48)
            )
            components = {
                "edge": closeness(edge_distance, target_edge, 35),
                "wall": closeness(wall_distance, target_wall, 27),
                "palette": closeness(art_distance, 20, 38),
                "room": 0.6 * closeness(lab[2], room["warmth"], 25)
                + 0.4 * closeness(lab[0], room["brightness"], 50),
                "lightness": closeness(lab[0], target_l, 45),
                "neutral": neutral,
            }
            score = sum(components[k] * weights[k] for k in weights) / max(1, sum(weights.values()))
            # Small, conservative style effect. Never overwhelms a good color match.
            style = 0
            if matte["family"] == settings.get("preferred_family"):
                style += 2
            if matte["family"] == "shadowbox" and room["brightness"] < 50:
                style += 1.5
            if matte["family"].startswith("modern") and artwork["edge_structure"] > 15:
                style += 1
            score += style + {"preferred": 3, "avoid": -12, "normal": 0}[matte["preference"]]
            # Saturated candidates need a substantial advantage, not just complementarity.
            score -= max(0, chroma - 20) * 0.25 * settings["neutral_preference"]
            score = float(np.clip(score, 0, 100))
            result.append(
                {
                    "matte": matte,
                    "score": round(score, 2),
                    "components": {k: round(v, 1) for k, v in components.items()},
                    "style_adjustment": style,
                    "reasons": [
                        REASONS[k] for k in sorted(components, key=components.get, reverse=True)[:4]
                    ],
                }
            )
        return sorted(result, key=lambda x: (-x["score"], x["matte"]["id"]))
