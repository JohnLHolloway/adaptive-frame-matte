# Troubleshooting and compatibility

[Back to README](../README.md)

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

For network setup, see [deployment and discovery](DEPLOYMENT.md#network-requirements-and-discovery).
