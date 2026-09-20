# Contributing

Use Python 3.12+, install `.[dev]`, and run `ruff check .` and `pytest`.
Keep Samsung-specific behavior inside `app/samsung/client.py`. Never add power,
volume, account, Wi-Fi or arbitrary deletion operations as a workaround.

Regression tests should validate observable behavior. Physical tests are opt-in and
must preserve state. Include tested model/API and distinguish API acknowledgement,
API readback and visually confirmed redraw. Do not publish runtime data.

Before committing: inspect `git diff --cached`, run
`python scripts/privacy_audit.py`, and ensure `/data`, `.env`, private images
and tokens remain ignored. Contributions to original application code use MIT;
do not copy incompatible third-party code or assets into the project.

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

See [validation notes](docs/VALIDATION.md) and [safe physical-TV tests](docs/TROUBLESHOOTING.md#compatibility-and-safe-live-tests).
