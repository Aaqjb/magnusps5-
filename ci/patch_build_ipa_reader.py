#!/usr/bin/env python3
"""Patch only the reconstructed IPA verifier's linker-map text decoding.

Apple's linker map is overwhelmingly textual but can contain bytes that are not
valid UTF-8 (for example inside symbol/path data).  Python 3.14's default
Path.read_text() therefore aborts after the app has already linked successfully.
This patch keeps all verification logic intact and merely makes decoding robust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


OLD = "mapping = link_map.read_text()"
NEW = "mapping = link_map.read_text(encoding='utf-8', errors='replace')"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    target = source / "tools/build_ipa.py"
    if not target.is_file():
        raise FileNotFoundError(target)

    before = target.read_bytes()
    text = before.decode("utf-8")
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one guarded linker-map read in {target}, found {count}"
        )
    if NEW in text:
        raise RuntimeError("Robust linker-map decoder is already present unexpectedly")

    text = text.replace(OLD, NEW, 1)
    after = text.encode("utf-8")
    target.write_bytes(after)

    # Guard against an accidental broad edit. The replacement changes only this
    # one verifier expression and never touches emulator/runtime source files.
    result = {
        "status": "patched reconstructed packaging verifier only",
        "target": str(target),
        "before_sha256": sha256(before),
        "after_sha256": sha256(after),
        "replacement": {
            "from": OLD,
            "to": NEW,
        },
        "reason": (
            "Apple linker maps may contain isolated non-UTF-8 bytes. Replacement "
            "decoding preserves ASCII symbol/path checks while preventing the "
            "post-link verifier from crashing before IPA packaging."
        ),
    }
    args.evidence.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.evidence.resolve().write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
