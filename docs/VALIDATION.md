# Validation

The current suite covers RGB/LAB round trips, a published CIEDE2000 reference,
artwork and edge palette extraction, ICC handling, strategy differences, bounded
frame-finish influence, fixed-color behavior, pause/Never Modify/Art Mode guards,
hysteresis, write cooldowns, artwork overrides, protocol compatibility, thumbnail
security, large-library paging, TV isolation, restart persistence, and removal of
legacy room HTTP endpoints without deleting private files.

A physical QN65LS03DAFXZA with Art API 5.0.1.0 has been used. Pairing from the server,
Art Store SAM-* thumbnails, matte read/write, same-art reselect redraw, observed
image_selected websocket events, and exact original matte restoration were verified.
The user confirmed that a matte write alone did not redraw; reselecting did.
TrueNAS bridge-network operation and Docker restarts were verified. No firmware,
volume, account, Wi-Fi or unrelated picture settings were changed.

Only one physical TV was available; multi-TV isolation is tested using mock clients.
Other Frame generations and a long unattended soak remain unverified. Command
readback is distinguished from a person confirming the visual display. Live tests
are opt-in and never run in GitHub Actions.
