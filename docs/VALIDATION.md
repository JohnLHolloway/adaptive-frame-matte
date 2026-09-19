# Validation record

Development validation, 2026-09-19. Treat these as observations of this revision,
not a compatibility promise for every Samsung TV or firmware.

## Automated and browser checks

- 57 pytest tests pass on Python 3.13 (Windows development environment).
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

The current artwork was Art Store content. Thumbnail transfer failed during the
session. A matte write was acknowledged but the requested matte was not confirmed
by readback. The original matte was confirmed intact afterward. No arbitrary artwork
was uploaded/deleted, no firmware/settings changed, and no power command was sent.

Physical testing stopped when the user resumed normal television viewing.
Remaining unverified checks:

- Successful matte write and visibly changed matte on the physical display.
- Whether re-selection is required for physical redraw.
- Successful thumbnail retrieval for Art Store and personal artwork.
- Artwork-change websocket events during a real remote-initiated artwork change.
- Physical calibration-pattern upload, display, real room photos and cleanup.
- End-to-end unattended automation on the physical television.
- Installation on a user's TrueNAS host (local Docker testing is not a NAS deployment).

Run `scripts/frame_probe.py` as documented in the README before enabling automation
on a new physical installation. No live TV tests run in GitHub Actions.
