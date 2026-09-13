#!/usr/bin/env python3
"""Deduplicate fmt for the final Magnus iPhoneOS link.

FEX is first built and strictly linked with its own real fmt archive.  The final
Magnus executable also links Kyty/Magnus's bundled fmt, so carrying both static
archives into one executable produces duplicate fmt::v12 definitions.

This script runs only after the standalone FEX link gate has passed.  It:
  * verifies FEX and Magnus use the exact same FMT_VERSION;
  * preserves FEX's real archive as libfmt.fex-standalone.a;
  * replaces the path expected by the final app link with an arm64 iPhoneOS
    placeholder archive containing no exported fmt symbols;
  * records hashes and versions as build evidence.

The final executable therefore resolves FEX's fmt references from the single
Magnus/Kyty fmt implementation instead of suppressing duplicate-symbol errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


FMT_VERSION_RE = re.compile(r"^\s*#\s*define\s+FMT_VERSION\s+(\d+)\b", re.MULTILINE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fmt_version(fmt_root: Path) -> tuple[int, Path]:
    candidates = (
        fmt_root / "include/fmt/base.h",
        fmt_root / "include/fmt/core.h",
        fmt_root / "include/fmt/format.h",
    )
    for header in candidates:
        if not header.is_file():
            continue
        match = FMT_VERSION_RE.search(header.read_text(errors="replace"))
        if match:
            return int(match.group(1)), header
    raise RuntimeError(f"Could not find FMT_VERSION under {fmt_root}")


def run(*args: str) -> None:
    subprocess.run(list(args), check=True)


def output(*args: str) -> str:
    return subprocess.check_output(list(args), text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Materialized Magnus source tree")
    parser.add_argument("--fex-root", type=Path, required=True,
                        help="Pinned FEX source tree")
    parser.add_argument("--fex-build", type=Path, required=True,
                        help="Configured iPhoneOS FEX build tree")
    parser.add_argument("--evidence", type=Path, required=True,
                        help="JSON evidence output")
    args = parser.parse_args()

    source = args.source.resolve()
    fex_root = args.fex_root.resolve()
    fex_build = args.fex_build.resolve()
    evidence = args.evidence.resolve()
    evidence.parent.mkdir(parents=True, exist_ok=True)

    magnus_fmt = source / "3rdparty/fmt"
    fex_fmt = fex_root / "External/fmt"
    magnus_version, magnus_header = fmt_version(magnus_fmt)
    fex_version, fex_header = fmt_version(fex_fmt)

    if magnus_version != fex_version:
        raise RuntimeError(
            "Refusing to share fmt across the final link because versions differ: "
            f"Magnus={magnus_version}, FEX={fex_version}"
        )

    archive = fex_build / "External/fmt/libfmt.a"
    if not archive.is_file():
        raise FileNotFoundError(f"Expected FEX fmt archive not found: {archive}")

    backup = archive.with_name("libfmt.fex-standalone.a")
    if backup.exists():
        raise RuntimeError(f"Refusing to overwrite existing preserved archive: {backup}")

    original_hash = sha256(archive)
    shutil.copy2(archive, backup)

    sdk = output("xcrun", "--sdk", "iphoneos", "--show-sdk-path")
    clang = output("xcrun", "--sdk", "iphoneos", "--find", "clang")

    with tempfile.TemporaryDirectory(prefix="magnus-shared-fmt-") as tmp:
        tmp = Path(tmp)
        placeholder_c = tmp / "shared_fmt_placeholder.c"
        placeholder_o = tmp / "shared_fmt_placeholder.o"
        placeholder_c.write_text(
            "/* Intentionally no exported symbols.  The final Magnus link uses "
            "its single bundled fmt implementation. */\n"
            "static const int magnus_fex_fmt_placeholder = 0;\n"
        )
        run(
            clang,
            "-arch", "arm64",
            "-isysroot", sdk,
            "-miphoneos-version-min=17.4",
            "-c", str(placeholder_c),
            "-o", str(placeholder_o),
        )
        archive.unlink()
        run("/usr/bin/ar", "-rcs", str(archive), str(placeholder_o))

    nm = subprocess.run(
        ["/usr/bin/nm", "-g", str(archive)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout
    if "_ZN3fmt" in nm or "fmt::" in nm:
        raise RuntimeError("Placeholder archive unexpectedly exports fmt symbols")

    result = {
        "strategy": "single-final-app-fmt",
        "fmt_version": magnus_version,
        "magnus_fmt_header": str(magnus_header),
        "fex_fmt_header": str(fex_header),
        "fex_real_archive_preserved": str(backup),
        "fex_real_archive_sha256": original_hash,
        "final_app_placeholder_archive": str(archive),
        "final_app_placeholder_sha256": sha256(archive),
        "reason": (
            "Standalone FEX validation uses its real fmt archive. The final Magnus "
            "app links only Magnus/Kyty fmt so FEX and Kyty do not provide duplicate "
            "fmt::v12 definitions."
        ),
    }
    evidence.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
