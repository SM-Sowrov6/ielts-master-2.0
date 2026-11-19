"""Rebuild the common-password blocklist (docs/SECURITY_GUIDELINES.md §2).

Source (verified 2026-11-18):
- File: `Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt` from
  SecLists (https://github.com/danielmiessler/SecLists), MIT License, pinned to a commit.
- Data origin: Mark Burnett's "ten million passwords" dataset (2015), published openly by the
  author for research and defence; SecLists redistributes the frequency-sorted top 1,000,000.

Processing is deterministic: keep entries whose length is within the password policy
(10..128 characters), lowercase them (the check is case-insensitive), de-duplicate, sort, and
write gzip with a fixed mtime. The download is verified against a pinned SHA-256.

Maintenance: the dataset is static. To update, change COMMIT and SHA256 after reviewing the new
file and its licence, then run:

    uv run python -I scripts/update_password_blocklist.py
"""

import gzip
import hashlib
import sys
import urllib.request
from pathlib import Path

COMMIT = "6b19c2f5088c45b5dadb4d8918d2ab4f7efb03a9"
PATH = "Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt"
SHA256 = "424a3e03a17df0a2bc2b3ca749d81b04e79d59cb7aeec8876a5a3f308d0caf51"
URL = f"https://raw.githubusercontent.com/danielmiessler/SecLists/{COMMIT}/{PATH}"
MIN_LENGTH, MAX_LENGTH = 10, 128
OUT = (
    Path(__file__).resolve().parents[1]
    / "backend/app/modules/identity/data/common-passwords.txt.gz"
)


def main() -> int:
    with urllib.request.urlopen(URL, timeout=120) as response:
        raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SHA256:
        print(f"SHA-256 mismatch: expected {SHA256}, got {digest}", file=sys.stderr)
        return 1
    words = {
        line.strip().lower()
        for line in raw.decode("utf-8", errors="ignore").splitlines()
        if MIN_LENGTH <= len(line.strip()) <= MAX_LENGTH
    }
    header = (
        f"# Common-password blocklist. Source: SecLists@{COMMIT} {PATH} (MIT License).\n"
        f"# Origin: Mark Burnett ten-million-passwords dataset. Filter: {MIN_LENGTH}-{MAX_LENGTH}"
        " chars, lowercased.\n"
    )
    body = header + "\n".join(sorted(words)) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(body.encode("utf-8"))
    print(f"wrote {len(words)} entries to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
