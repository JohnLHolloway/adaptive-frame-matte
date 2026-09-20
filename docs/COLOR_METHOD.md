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

## Automation and TV limits

A persistent local websocket listens for artwork changes, with a 10-second polling
fallback. The image provider tries the TV thumbnail, a local image you supplied,
then the cache. Analysis extracts dominant and perimeter colors in CIELAB; candidate
matte scoring uses CIEDE2000, lightness balance and a neutral bias. The catalog comes
from the TV; no Samsung matte IDs are assumed globally.

Automatic mode uses an eight-point improvement threshold and a five-minute cooldown
for the same artwork. New artwork can be evaluated immediately. Fixed color bypasses
score thresholds and the cooldown so explicit color changes take effect promptly;
already-correct mattes are not rewritten. Both modes require Art Mode and recheck
current artwork before writes. The app never wakes the TV to change a matte.

If a thumbnail is unavailable, automatic visual recommendations cannot run; retain
current matte is the default fallback. A safe matte or per-artwork override can be
configured. Fixed color needs no thumbnail. Firmware can reject particular
style/artwork combinations; failures are reported without silently substituting colors.

Matte commands select TV-supported style/color IDs. Arbitrary RGB colors and numeric
border widths are not exposed by this interface. Samsung renders its own shadowbox
and border effects. Browser previews are approximate; multi-panel layouts are not
reproduced. Advanced swatch edits change our estimated appearance, not Samsung's color.
