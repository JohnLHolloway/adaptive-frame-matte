# Adaptive Frame Matte

A local companion for Samsung Frame TVs. It chooses a restrained matte for each
painting—or keeps one color on every artwork—in your favorite border style.
One Python app, one container, no cloud AI or room photography.

**Unofficial. Not affiliated with Samsung.** Uses Samsung's existing local Art Mode
interface, never custom firmware. Firmware/API behavior can change. Samsung artwork
is not redistributed, Art Store source files are not downloaded, and authentication
or DRM is never bypassed. All visual analysis stays local.

## Quick start

```sh
git clone https://github.com/JohnLHolloway/adaptive-frame-matte.git
cd adaptive-frame-matte
mkdir -p data
sudo chown 10001:10001 data
docker compose up -d --build
```

Open **http://YOUR_SERVER_IP:8787**. Find your TV in Setup, or enter its local IP.
Press **Allow** on the TV if prompted. Pairing is saved under `/data` and never
shown in the browser. Keep the TV in Art Mode to test matte changes.

Under **Preferences**, choose:

- **Automatically for each painting**: analyze the artwork, particularly its edges.
  Gallery defaults to light, quiet neutrals. Adaptive, Subtle, and Contrast offer
  other balances. Advanced numerical controls are off by default.
- **Always use one color**: choose any enabled color advertised by your TV. It is
  applied to each artwork in your selected style, even without a usable thumbnail.
- **Frame style**: keep a favorite style such as Shadowbox while adapting its color.
- **Physical frame finish**: optionally select white, black, light/dark wood or
  warm/cool metal. This broad estimate contributes at most two score points in
  either direction, only in automatic mode. It is not a measured color calibration.

Resume automation on Home. Pause stops all automatic writes, including fixed color.
No room photos, location, sunrise/sunset schedule, or day/night setup is needed.

## Everyday use

Home shows what's on the TV and why a matte is suggested. Use **Try another color**,
then **Use this**; optionally **Keep for this artwork** to save an individual choice.
Manage saved choices under Settings → Artwork library. Fixed-color mode overrides
saved per-artwork colors while active; returning to Automatic restores their effect.
**Never modify** always takes precedence, even in fixed-color mode.

Each configured TV has independent pairing, preferences, caches, history and watcher.
Add TVs under Settings → Your TVs & discovery. The TV selector appears when more
than one TV is configured. Changing the viewed TV does not pause the others.

## How it works

A persistent local websocket listens for artwork changes, with a 10-second polling
fallback. The image provider tries the TV thumbnail, a local image you supplied,
then the cache. Analysis extracts dominant and perimeter colors in CIELAB; candidate
matte scoring uses CIEDE2000, lightness balance and a neutral bias. The catalog comes
from the TV; no Samsung matte IDs are assumed globally. See [color method](docs/COLOR_METHOD.md).

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

## Docker and TrueNAS SCALE

Requires a Docker/Compose-capable TrueNAS SCALE release. Create a persistent dataset,
for example `POOL/apps/adaptive-frame-matte`, using the TrueNAS UI. In its directory:

```sh
cd /mnt/POOL/apps/adaptive-frame-matte
git clone https://github.com/JohnLHolloway/adaptive-frame-matte.git project
mkdir -p data
sudo chown 10001:10001 data
cd project
printf 'FRAME_DATA_PATH=/mnt/POOL/apps/adaptive-frame-matte/data\nFRAME_MOCK_TV=false\n' > .env
sudo docker compose up -d --build
```

Open **http://YOUR_SERVER_IP:8787**. The container runs as UID/GID 10001, exposes
port 8787, logs to stdout, has a healthcheck, and restarts unless stopped. `/data`
contains SQLite, tokens, thumbnails, history, and preferences. Back up that directory
or its ZFS dataset. Keep it outside the repository checkout.

Update without losing pairing or preferences:

```sh
git pull --ff-only
sudo docker compose up -d --build --force-recreate
sudo docker compose logs --tail=100
```

This is ordinary Compose deployment; it does not automatically register a TrueNAS
Apps UI entry. The provided container has no need for host privileges.

## Network requirements and discovery

Bridge networking works with a manual TV IP. Your server must reach the TV's local
Samsung endpoints (usually HTTP 8001 and TLS websocket 8002). Thumbnail transfer uses
a TV-advertised local port. Reserve the TV's address in DHCP if possible.

SSDP multicast may not cross Docker or VLAN boundaries. Setup supports an optional
explicit private `/24` Samsung-only discovery pass; it does not aggressively scan
unrelated services. For multicast discovery, Linux host networking can be used by
removing the Compose `ports` section and adding `network_mode: host`. It is optional.

Discovery/debug command:

```sh
python scripts/frame_probe.py --discover
python scripts/frame_probe.py --help
```

## Compatibility and safe live tests

The adapter uses NickWaterton's maintained Frame-focused `samsungtvws` fork at a
pinned commit. Different Frame generations expose different options. A production
QN65LS03DAFXZA with Art API 5.0.1.0 has been tested: Art Store thumbnails, native
matte writes, websocket image events and restoration worked. This model required
reselecting the current artwork for a visible matte redraw; the app supports that
quirk and never performs the reselect outside Art Mode. Other models remain unverified.

The opt-in `scripts/frame_probe.py` supports discovery, pairing, capabilities, and
state-preserving matte tests. Run `--help` before using its write-test options. It
records original state and restores it; visual redraw confirmation still needs a
person looking at the TV. Physical tests never run in GitHub Actions.

## Troubleshooting

- **Not found**: enter the TV address manually; check VLAN/firewall and discovery notes.
- **Pairing timed out**: approve the popup on the TV and retry Setup. A token authorized
  from a different host may require pairing again from the deployment server.
- **Matte stored but not visible**: enable re-selection in Advanced settings only after
  verifying that the model needs it. Never use power cycling as a redraw workaround.
- **No changes**: check Pause, Art Mode, Never modify overrides and the improvement
  threshold. Fixed color is selected in Preferences, not through an artwork override.
- **Unavailable color/style**: enable the desired color in the catalog or choose a
  combination supported by that artwork. The app does not invent missing TV options.
- **Colors look different**: TV brightness, panel rendering and browser displays differ.
  TV-provided RGB is an estimate of appearance, not a physical measurement.

## Upgrade from 0.2.x

Version 0.3 removes room photography, calibration, geographic location, and day/night
scheduling, including their HTTP routes. Existing pairing, matte preferences, artwork
history and overrides remain. Obsolete settings are removed from active configuration.
Old room files and database records are left untouched for backup/recovery, but the
app does not read, serve or use them. They are not required for a new installation.
Finish any active legacy calibration session on 0.2.x before upgrading; an unfinished
session remains a safety stop rather than silently changing the displayed artwork.

## Development and mock mode

Python 3.12+:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
FRAME_MOCK_TV=true FRAME_DATA_DIR=./data uvicorn app.main:app --port 8787
ruff check .
pytest
```

On Windows, activate `.venv\Scripts\Activate.ps1` and set variables with `$env:`.
Mock mode provides generated artwork, simulated events and a device catalog, without
connecting to a physical TV. CI runs lint, unit/integration tests, privacy checks and
a Docker build. Tests cover perceptual color math, image analysis, fixed-color rules,
overrides, write guards, multi-TV isolation and migration.

## Privacy, security, licensing and contributing

No telemetry, analytics, cloud AI or Samsung account password. Pairing tokens and
images stay in `/data`; never commit or publish that directory or `.env`. Image types,
size, filenames and network inputs are validated. **Do not expose this UI directly
to the public internet**: it is intended for a trusted LAN, with no user login system.

Original application code and generated demo art are MIT licensed. See [LICENSE](LICENSE),
[third-party notices](THIRD_PARTY_NOTICES.md), and [contributing](CONTRIBUTING.md).
`samsungtvws` remains LGPL-3.0 as a separately installed, replaceable dependency.
The Docker image includes its exact corresponding source at
`/usr/share/adaptive-frame-matte/samsungtvws-source.tar.gz`; retain it and notices
when redistributing the image. No Samsung artwork or incompatible matte data is included.
