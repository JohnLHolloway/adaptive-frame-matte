# Color measurement and recommendation limits

Three signals are kept separate:

1. **Artwork:** up to five dominant LAB clusters and an independent outside-12.5%
   perimeter palette. The perimeter carries the strongest recommendation weight.
2. **Wall:** robust statistics from relatively smooth patches immediately above
   and beside the TV. Screen, frame gap, texture and color outliers are excluded.
3. **Room context:** a wider region near the TV, excluding the whole screen and
   bezel. It has its own dominant/neutral palette and accent palette. Accents must
   have measurable chroma and differ from the wall; tiny clusters and near-clipped
   light/dark pixels are suppressed. This is color analysis, not object recognition.

Embedded ICC profiles are converted to sRGB before measurement (including phone
wide-gamut images when their ICC profile is present). Untagged RGB is assumed sRGB.
EXIF/GPS and other image metadata are removed from normalized stored images.

We use scikit-image's D65 sRGB-to-CIELAB conversion and CIEDE2000 color differences.
See the [scikit-image color API](https://scikit-image.org/docs/stable/api/skimage.color.html#skimage.color.deltaE_ciede2000).
CIEDE2000 measures perceptual color difference; it does **not** scientifically
determine which matte is attractive. The bounded harmony/lightness functions,
neutral bias and strategy weights are explicit product heuristics.

An ordinary snapshot measures apparent color under that phone's processing.
There is no defensible absolute white balance, ambient illuminance or true wall
reflectance recovery from an arbitrary photo alone. Snapshot confidence is a
heuristic capped at 60%, and ambient cast is unknown. Day/night photographs should
use normal lighting and similar viewpoints. Avoid filters and clipped highlights.

Optional reference calibration fits a regularized affine transform from known
patches and evaluates held-out patch error. It reduces some camera/scene errors,
but an emissive TV is not a reflective reference card, and phone HDR/tone mapping
can be spatially nonlinear. We do not claim laboratory accuracy. Its confidence
is capped at 90%. A physical reference card or measured matte calibration could
improve a future version, but is not required.

Room accents act as a **small tie-breaker**: default influence 5 changes a matte's
score by at most ±2.5 points. Gallery/Subtle reduce this further. Users can set
influence to zero to ignore temporary/seasonal decorations, or increase it to 10
(at most ±5 points). The neutral/saturation penalties still apply. Accents never
change the measured wall color and never include the TV's current movie or artwork.

The automatic detector and masks are fallible. Four-corner confirmation and an
optional advanced mask editor provide local correction without making painting
part of the normal setup workflow.

Low-confidence wall/room color component scores are pulled toward a neutral score,
and accent influence is reduced proportionally. This makes uncertain camera
measurements less influential than artwork analysis and neutral preference.
