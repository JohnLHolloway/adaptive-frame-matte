"""Scan tracked/staged files for secrets and private runtime artifacts before publishing."""

import pathlib
import re
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
bad = []
patterns = [
    r"gh[pousr]_" + r"[A-Za-z0-9]{25,}",
    r"github_pat_" + r"[A-Za-z0-9_]{30,}",
    r"-----BEGIN " + r"(?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    r"\b10\.0\.0\.\d+\b",
    r"(?i)\b(?:token|password)\s*[:=]\s*['\"][A-Za-z0-9+/]{16,}['\"]",
]
for name in files:
    if not name:
        continue
    path = root / name
    if (
        any(p in path.parts for p in ("data", "private-frame", "tokens"))
        or path.suffix in (".db", ".sqlite3", ".token")
        or path.name == ".env"
    ):
        bad.append(name + ": private artifact")
    if path.is_file() and path.suffix not in (".png", ".jpg", ".webp"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            if re.search(pattern, text):
                bad.append(name + ": potential secret/private deployment address")
if bad:
    print("\n".join(bad))
    sys.exit(1)
print(
    f"Privacy audit passed: {len(files) - 1} tracked files; no matching secrets or private artifacts."
)
