"""Opt-in local probe. Never invoked by CI. No power, settings, or deletion commands."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.samsung.client import SamsungClient  # noqa: E402
from app.samsung.discovery import discover  # noqa: E402


async def probe(args):
    if args.discover:
        print(json.dumps(await discover(args.subnet), indent=2))
        return
    if not args.ip:
        raise ValueError("Use --ip for a manual TV address or --discover")
    directory = Path(args.data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    client = SamsungClient(args.ip, directory / "tokens")
    print(
        "If Samsung displays an Adaptive Frame Matte authorization popup, press Allow.", flush=True
    )
    original = None
    attempted = False
    report = {
        "matte_write": "not tested",
        "immediate_redraw": "unverified",
        "requires_reselect": "unverified",
        "sam_thumbnail": "not tested",
    }
    try:
        await client.connect()
        report["pairing"] = "OK"
        info = await client.get_device_info()
        report["model"] = info["model"]
        report["art_supported"] = info["art_supported"]
        report["api_version"] = info.get("api_version")
        mode = await client.get_art_mode()
        original = await client.get_current_artwork()
        report.update(artmode=mode, original=original)
        report["mattes"] = await client.get_available_mattes()
        # A recovery journal is private, and is written before any possible mutation.
        (directory / "probe-original.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
        if mode == "on":
            try:
                image = await client.get_artwork_thumbnail(original["content_id"])
                report["thumbnail_bytes"] = len(image)
                if original["content_id"].startswith("SAM-"):
                    report["sam_thumbnail"] = bool(image)
            except Exception as error:
                report["thumbnail"] = type(error).__name__
                if original["content_id"].startswith("SAM-"):
                    report["sam_thumbnail"] = "unavailable in this probe"
        else:
            report["thumbnail"] = "deferred: Art Mode is off"
        if args.write_test:
            if mode != "on":
                print("Write test skipped: Art Mode is off. The TV will not be awakened.")
            else:
                # Match the current family, use only an advertised color, change landscape only.
                family = original["matte_id"].split("_", 1)[0]
                colors = [c["color"] for c in report["mattes"]["matte_colors"]]
                target = next(
                    (
                        f"{family}_{color}"
                        for color in colors
                        if f"{family}_{color}" != original["matte_id"]
                    ),
                    None,
                )
                if not target or family == "none":
                    raise ValueError("No safe same-family alternative for this artwork")
                attempted = True
                await client.set_matte(original["content_id"], target)
                readback = await client.get_current_artwork()
                report["matte_write"] = (
                    "verified" if readback.get("matte_id") == target else "not verified"
                )
                print(
                    "Temporary matte:", target, "API readback:", report["matte_write"], flush=True
                )
                answer = await asyncio.to_thread(
                    input, "Did the physical matte visibly change? [y/n/unknown] "
                )
                report["immediate_redraw"] = answer.strip().lower()
                if answer.strip().lower() == "y":
                    report["requires_reselect"] = False
                elif answer.strip().lower() == "n":
                    await client.select_artwork(original["content_id"])
                    answer = await asyncio.to_thread(
                        input, "Did re-selecting make the physical matte change? [y/n/unknown] "
                    )
                    report["requires_reselect"] = (
                        True if answer.strip().lower() == "y" else "unverified"
                    )
        if args.observe_seconds:
            print(
                "Observing artwork events; change artwork with your TV remote if desired.",
                flush=True,
            )
            await asyncio.sleep(min(60, args.observe_seconds))
        report["observed_websocket_events"] = sorted(client.observed_events)
    finally:
        if attempted and original:
            # Retry restoration on a fresh connection after a transport failure.
            restored = False
            for _ in range(2):
                try:
                    if await client.get_art_mode() != "on":
                        raise ValueError("Art Mode is now off: will not wake TV to restore")
                    if (await client.get_current_artwork())["content_id"] != original["content_id"]:
                        raise ValueError(
                            "Artwork changed externally: will not replace user's selection"
                        )
                    await client.set_matte(original["content_id"], original["matte_id"])
                    await client.select_artwork(original["content_id"])
                    actual = await client.get_current_artwork()
                    restored = all(
                        actual.get(k) == original.get(k)
                        for k in ("content_id", "matte_id", "portrait_matte_id")
                    )
                    if restored:
                        print("MATTE_RESTORED: exact original state verified")
                        break
                except Exception:
                    await client.close()
            report["restored"] = restored
            if not restored:
                print(
                    "RESTORATION NOT VERIFIED. Original state is in the private probe-original.json.",
                    file=sys.stderr,
                )
        await client.close()
        (directory / "probe-report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--subnet", help="Optional private /24, Samsung port 8002 only")
    parser.add_argument("--ip")
    parser.add_argument("--data-dir", default=os.getenv("FRAME_DATA_DIR", "data"))
    parser.add_argument(
        "--write-test", action="store_true", help="Interactive, state-preserving matte test"
    )
    parser.add_argument("--observe-seconds", type=int, default=0)
    args = parser.parse_args()
    try:
        asyncio.run(probe(args))
    except (Exception, KeyboardInterrupt) as error:
        print(
            f"Probe stopped: {type(error).__name__}. Check local connectivity and pairing.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
