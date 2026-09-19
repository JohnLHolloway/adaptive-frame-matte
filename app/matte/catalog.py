from app.artwork.palette import hex_color, to_lab

# Original nominal estimates, only used if firmware omits RGB. Never a supported-ID list.
NOMINAL = {
    "black": (34, 34, 34),
    "white": (238, 238, 238),
    "polar": (232, 232, 232),
    "warm": (232, 227, 216),
    "antique": (222, 215, 200),
    "neutral": (136, 136, 136),
    "cream": (235, 226, 206),
}


class MatteCatalog:
    def __init__(self, db):
        self.db = db

    def refresh(self, raw):
        old = self.db.all("mattes")
        present = []
        for item in raw.get("matte_types", []):
            family = item.get("matte_type", item.get("matte_id", ""))
            if not family:
                continue
            colors = raw.get("matte_colors", [])
            if family == "none" or "_" in family:
                colors = [{"color": "none" if family == "none" else family.split("_", 1)[1]}]
            for c in colors:
                color = c.get("color", c.get("color_name", "unknown"))
                mid = family if family == "none" or "_" in family else f"{family}_{color}"
                rgb = (
                    [c[k] for k in ("R", "G", "B")]
                    if all(k in c for k in ("R", "G", "B"))
                    else NOMINAL.get(color, (150, 150, 150))
                )
                source = "TV-reported" if "R" in c else "Nominal estimate"
                row = {
                    "id": mid,
                    "family": family.split("_", 1)[0],
                    "color": color,
                    "name": mid.replace("_", " / ").title(),
                    "hex": hex_color(rgb),
                    "lab": to_lab(rgb).tolist(),
                    "source": source,
                    "enabled": mid != "none",
                    "preference": "normal",
                    "supported": True,
                    "compatibility": "Device-advertised; artwork compatibility checked on apply",
                }
                if mid in old:
                    row.update({k: old[mid][k] for k in ("enabled", "preference")})
                    if old[mid].get("source") == "User calibrated":
                        row.update({k: old[mid][k] for k in ("hex", "lab", "source")})
                self.db.put("mattes", mid, row)
                present.append(mid)
        for mid in set(old) - set(present):
            self.db.put("mattes", mid, {**old[mid], "supported": False})
        return self.all()

    def all(self):
        return [v for v in self.db.all("mattes").values() if v.get("supported")]
