# Color method

Artwork is decoded with Pillow, oriented from EXIF, converted from an embedded ICC
profile to sRGB when present, and stripped of metadata. A bounded 256-pixel image
provides deterministic, weighted color clustering in CIELAB. The outside 12.5% is
analyzed separately because it meets the matte directly. Color distances use
CIEDE2000 from scikit-image; this is local numerical analysis, not an LLM.

Candidates come exclusively from the connected TV's catalog. RGB values reported
by the TV are preferred; a small original nominal mapping is used otherwise.
Users can refine swatches in Advanced controls. These estimates do not change the
TV's native matte colors and are not laboratory measurements.

Four components contribute to automatic scoring: artwork-edge harmony, overall
palette harmony, lightness balance and conservative neutrality. Gallery emphasizes
low-chroma, light paper-like mattes. Adaptive, Subtle and Contrast change the balance.
A large color distance is not treated as automatically attractive. Saturated mattes
need a substantial advantage. Style preference is conservative or can be locked.

An optional physical-frame finish uses broad original nominal color estimates. It
provides at most +/-2 score points based on moderate separation from the trim. This
is a tie-breaker, not a claim to know the exact wood stain or metal color. Choose
No preference to remove it. No room photographs, walls, ambient brightness,
location, clock, or daylight information enters the model.

Fixed color bypasses scoring completely. It chooses the requested TV-supported
color in the preferred style (or preserves the current style where available).
Never modify overrides and Art Mode safety checks remain in effect. It does not
require a thumbnail. Per-artwork forced colors resume their effect when global
fixed-color mode is switched back to automatic.
