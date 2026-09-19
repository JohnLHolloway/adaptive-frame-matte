# Contributing

Use Python 3.12+, install `.[dev]`, and run `ruff check .` and `pytest`.
Keep Samsung-specific behavior inside `app/samsung/client.py`. Never add power,
volume, account, Wi-Fi or arbitrary deletion operations as a workaround.

Regression tests should validate observable behavior. Physical tests are opt-in and
must preserve state. Include tested model/API and distinguish API acknowledgement,
API readback and visually confirmed redraw. Do not publish runtime data.

Before committing: inspect `git diff --cached`, run
`python scripts/privacy_audit.py`, and ensure `/data`, `.env`, calibration photos
and tokens remain ignored. Contributions to original application code use MIT;
do not copy incompatible third-party code or assets into the project.
