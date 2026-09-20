# Deployment

[Back to README](../README.md)

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

## Upgrade from 0.2.x

Version 0.3 removes room photography, calibration, geographic location, and day/night
scheduling, including their HTTP routes. Existing pairing, matte preferences, artwork
history and overrides remain. Obsolete settings are removed from active configuration.
Old room files and database records are left untouched for backup/recovery, but the
app does not read, serve or use them. They are not required for a new installation.
Finish any active legacy calibration session on 0.2.x before upgrading; an unfinished
session remains a safety stop rather than silently changing the displayed artwork.

## Privacy and access

No telemetry, analytics, cloud AI or Samsung account password. Pairing tokens and
images stay in `/data`; never commit or publish that directory or `.env`. Image types,
size, filenames and network inputs are validated. **Do not expose this UI directly
to the public internet**: it is intended for a trusted LAN, with no user login system.
