# Third-party software

Adaptive Frame Matte's original code, generated reference pattern, and generated
mock artworks are MIT licensed. No third-party matte color table is copied.
Device-reported RGB values stay in the local database. The tiny nominal fallback
table is an original estimate, not measured Samsung color data.

Samsung communication uses **samsungtvws**, NickWaterton's Frame-focused fork,
at commit `fe95ef1d784cd32f49bf9a07ec479576574eea07`, under **LGPL-3.0**:
https://github.com/NickWaterton/samsung-tv-ws-api

It is an unmodified, separately installed Python library, not copied into the
MIT application. Its license remains in its installed distribution. Corresponding
source for the exact version is available at:
https://github.com/NickWaterton/samsung-tv-ws-api/tree/fe95ef1d784cd32f49bf9a07ec479576574eea07

Users may replace/relink this library. To use a modified copy, mount or install it
into Python's site-packages, or change the dependency and rebuild the supplied
Dockerfile. No restriction on reverse engineering for debugging library changes
is imposed. If distributing container images, retain these notices and provide
the exact corresponding library source with your distribution (see README).

Other direct dependencies: FastAPI, Starlette, Uvicorn, Jinja2, python-multipart,
Pillow, NumPy, scikit-image, OpenCV, Astral, HTTPX, tzdata. These use MIT, BSD,
Apache-2.0, HPND/Pillow, or public-domain/IANA terms. Development tools pytest,
pytest-asyncio and Ruff have permissive licenses. Transitive dependency licenses
remain with their installed distributions. certifi's unmodified certificate data
is MPL-2.0, available at https://github.com/certifi/python-certifi; PSF-licensed
components retain their notices. A development-environment inventory is included
in `dependency-licenses.json` (container/platform versions can differ).
scikit-image provides D65 sRGB/CIELAB
conversion and CIEDE2000; OpenCV provides ArUco detection and perspective transforms.

The MIT license on this application does not replace dependency licenses.
Samsung trademarks belong to Samsung. No Samsung artwork is included.
