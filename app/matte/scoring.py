import math

import numpy as np

from app.artwork.palette import delta_e, to_lab

REASONS = {
    "edge": "Harmony with the artwork perimeter",
    "palette": "Harmony with the artwork palette",
    "lightness": "Balanced lightness transition",
    "neutral": "Restrained chroma keeps the artwork dominant",
}


def closeness(value, target, spread):
    return 100 * math.exp(-(((value - target) / spread) ** 2))


class MatteRecommendationEngine:
    def score(self, artwork, mattes, settings):
        result = []
        strategy = settings["strategy"]
        weights = settings["weights"].copy()
        if strategy == "Subtle":
            weights.update(edge=35, neutral=30, lightness=15, palette=20)
        elif strategy == "Contrast":
            weights.update(edge=45, neutral=15, lightness=20, palette=20)
        elif strategy == "Gallery":
            weights.update(edge=20, neutral=50, lightness=15, palette=15)
        # Original broad finish estimates, used only as a small tie-breaker.
        finishes = {
            "white": (235, 235, 230),
            "black": (30, 30, 30),
            "light_wood": (193, 155, 111),
            "dark_wood": (79, 53, 36),
            "warm_metal": (166, 131, 74),
            "cool_metal": (157, 160, 164),
        }
        finish = finishes.get(settings.get("frame_finish"))
        finish_lab = to_lab(finish) if finish else None
        for matte in mattes:
            if (
                settings.get("preferred_family_only")
                and settings.get("preferred_family")
                and matte["family"] != settings["preferred_family"]
            ):
                continue
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
            target_edge = 30 if strategy == "Contrast" else 10 if strategy == "Subtle" else 20
            neutral = float(np.clip(100 - chroma * 2.8 * settings["neutral_preference"], 0, 100))
            if strategy == "Gallery":
                neutral = 0.45 * neutral + 0.55 * closeness(lab[0], 90, 20)
            target_l = 0.65 * artwork["edge_lightness"] + 0.35 * 88
            components = {
                "edge": closeness(edge_distance, target_edge, 35),
                "palette": closeness(art_distance, 20, 38),
                "lightness": closeness(lab[0], target_l, 45),
                "neutral": neutral,
            }
            score = sum(components[k] * weights[k] for k in weights) / max(1, sum(weights.values()))
            finish_adjustment = 0.0
            if finish_lab is not None:
                # Bounded to +/- 2 points: artwork and neutrality stay primary.
                separation = closeness(float(delta_e(lab, finish_lab)), 25, 40)
                finish_adjustment = (separation - 50) / 25
                score += finish_adjustment
            # Small, conservative style effect. Never overwhelms a good color match.
            style = 0
            if matte["family"] == settings.get("preferred_family"):
                style += 2
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
                    "finish_adjustment": round(finish_adjustment, 2),
                    "style_adjustment": style,
                    "reasons": [
                        REASONS[k]
                        for k in sorted(
                            (k for k in components if weights[k] > 0),
                            key=components.get,
                            reverse=True,
                        )[:4]
                    ]
                    + (
                        ["Small separation benefit from your frame finish"]
                        if finish_adjustment > 0.5
                        else []
                    ),
                }
            )
        return sorted(result, key=lambda x: (-x["score"], x["matte"]["id"]))
