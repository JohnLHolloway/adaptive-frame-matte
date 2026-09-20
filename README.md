# Adaptive Frame Matte

A self-hosted companion for Samsung Frame TVs that picks a matte to suit each
artwork. Set it up once, choose your favorite border style, and let it follow along
as the art changes.

- **Automatic colors** with a preference for quiet, gallery-style neutrals.
- **One color for everything**, or a saved choice for an individual artwork.
- **Your TV's own matte styles**, including its native shadow and depth effects.
- **A phone-friendly interface** with support for multiple TVs.

Everything runs locally. No cloud account, AI service, or room photos needed.

## Get started

You'll need a Samsung Frame TV and a server with Docker Compose on the same LAN.

```sh
git clone https://github.com/JohnLHolloway/adaptive-frame-matte.git
cd adaptive-frame-matte
mkdir -p data
sudo chown 10001:10001 data
docker compose up -d --build
```

1. Open **http://YOUR_SERVER_IP:8787**.
2. Find your Frame in Setup, or enter its IP address. Press **Allow** on the TV if prompted.
3. Choose a style and automatic or fixed color under **Preferences**.
4. Put the TV in Art Mode and resume automation on Home.

The app only changes mattes while Art Mode is active; it won't wake the TV or
interrupt normal viewing. Pairing and preferences survive container restarts.

## Need a little more detail?

- [Using the app](docs/USAGE.md) — styles, saved choices, and multiple TVs.
- [Docker and TrueNAS setup](docs/DEPLOYMENT.md) — storage, updates, and discovery.
- [Troubleshooting](docs/TROUBLESHOOTING.md) — pairing, compatibility, and matte redraws.
- [How colors are chosen](docs/COLOR_METHOD.md) — artwork analysis and scoring.
- [Contributing](CONTRIBUTING.md) — local development, mock mode, and tests.

## A few things to know

Available colors and styles depend on your TV. Custom colors and arbitrary border
widths aren't supported by Samsung's local interface. Automatic color matching
needs a thumbnail from the TV; fixed-color mode works without one.

**Use on a trusted home network. Do not expose the UI directly to the internet.**
There is no login system. Keep the `data` folder private: it contains pairing tokens
and cached images. There is no telemetry, and all image analysis stays local.

Unofficial and not affiliated with Samsung. No firmware modifications, DRM bypass,
or redistribution of Samsung artwork. Samsung firmware changes may affect compatibility.

[MIT license](LICENSE) for the app. Dependencies retain their own licenses;
see [third-party notices](THIRD_PARTY_NOTICES.md).
