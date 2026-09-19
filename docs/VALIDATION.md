# Validation record

Development validation, 2026-09-19. Treat these as observations of this revision,
not a compatibility promise for every Samsung TV or firmware.

## Automated and browser checks

- 68 pytest tests pass on Python 3.13 (Windows development environment).
- Ruff checks pass; Python compilation succeeds.
- Desktop Chromium: Dashboard, Setup, Room, Artwork, Mattes, Strategy, History,
  Diagnostics and Settings render with no JavaScript errors.
- Mobile Chromium touch contexts: all pages at widths 320, 360, 390 and 430 have
  no document horizontal overflow. Touch wall-mask editing/saving tested at 390.
- Guided calibration exercised through HTTP with an original synthetic photograph:
  reference display, photograph upload, pattern detection, profile generation,
  browser mask editing/save and original-artwork restoration in mock mode.
- Ordinary snapshot detection checked against a private user-provided phone photo:
  TV located, nearby wall sampled automatically, screen/curtains/mantel excluded.
  That photograph and its measurements are not in the repository. Synthetic tests
  cover automatic detection, sampling, confidence limits and four-corner fallback.
- Linux Python 3.12 Docker build, non-root runtime, read-only filesystem and
  `/healthz` healthcheck tested. Container artwork change and day/night evaluation
  exercised in mock mode. A container restart preserves profiles, settings/history.
- Gitleaks and the repository-specific privacy audit are run before publication.

## Physical television checks

LAN connectivity and an actual Frame were established. Local pairing/token
persistence, device information, Art API version, Art Mode state, current artwork,
current matte, matte families, color names and TV-supplied RGB were read.

Testing resumed with explicit permission while Art Mode was on. Verified on a
2024 Frame / Art API 5.0.1.0:

- Art Store thumbnail retrieval, including local palette analysis (earlier transient
  transfers had failed). Personal calibration artwork thumbnails also worked.
- Same-family matte change and recommendation application confirmed by readback.
- Automatic recommendation application after selecting different Art Store content.
- `image_selected` received from an independent websocket client selection.
- Repeated unchanged evaluations caused no further writes.
- Day-to-night selection re-evaluated the same content. With no measured night profile,
  the application requested one rather than fabricating a room measurement.
- Generated calibration pattern upload, no-matte selection readback, thumbnail
  identity check, and removal of only positively identified generated test assets.
- Original artwork, original landscape and portrait matte values, and Art Mode state
  restored; both tested artworks' matte values verified after restoration.

Live testing uncovered and fixed MY_ personal content IDs, uppercase matte defaults,
delayed selection readback, and probe restoration of separate portrait matte values.
The TV may couple the reported orientations during a normal matte change. A combined
landscape/portrait request did not reliably change the landscape matte on this firmware.
No firmware, unrelated settings or power commands were used. No user artwork was deleted.

Remaining unverified checks:

- Human confirmation of visibly changed pixels and whether re-selection is needed.
- Artwork-change events initiated specifically by the physical remote (an independent
  local API client was verified).
- Real room photographs containing the displayed reference pattern; ordinary snapshot
  calibration was tested using the privately supplied room photo.
- Overnight/long-duration unattended operation on the physical television.
- Installation on a user's TrueNAS host (local Docker testing is not a NAS deployment).

Run `scripts/frame_probe.py` as documented in the README before enabling automation
on a new physical installation. No live TV tests run in GitHub Actions.
