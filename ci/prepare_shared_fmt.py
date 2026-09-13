#!/usr/bin/env python3
"""Prepare a single fmt implementation for the final Magnus iPhoneOS link.

The strict FEX link gate runs first with FEX's own real fmt archive. Magnus/Kyty
also builds a bundled fmt archive, and the two copies export the same fmt::v12
symbols. The complete app therefore cannot carry both static archives.

Before deduplicating anything, this script builds Magnus's fmt for iPhoneOS and
performs a second strict FEX/bridge link using Magnus fmt instead of FEX fmt.
Only if that binary compatibility probe succeeds do we preserve FEX's real fmt
archive and replace its final-app path with a symbol-free arm64 placeholder.
The final app then has exactly one fmt implementation: Magnus/Kyty's.
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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(*args: str) -> None:
    print(" ".join(str(arg) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], check=True)


def output(*args: str) -> str:
    return subprocess.check_output([str(arg) for arg in args], text=True).strip()


def build_magnus_fmt(source: Path, output_root: Path) -> Path:
    fmt_source = source / "3rdparty/fmt"
    fmt_build = output_root / "magnus-fmt-build"
    if fmt_build.exists():
        shutil.rmtree(fmt_build)
    run(
        "cmake", "-S", str(fmt_source), "-B", str(fmt_build), "-G", "Ninja",
        "-DCMAKE_SYSTEM_NAME=iOS",
        "-DCMAKE_SYSTEM_PROCESSOR=arm64",
        "-DCMAKE_OSX_ARCHITECTURES=arm64",
        "-DCMAKE_OSX_SYSROOT=iphoneos",
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=17.4",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
        "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
        "-DFMT_DOC=OFF", "-DFMT_TEST=OFF", "-DFMT_INSTALL=OFF",
        "-DFMT_OS=ON", "-DFMT_MODULE=OFF",
    )
    run("cmake", "--build", str(fmt_build), "--target", "fmt", "--parallel", "2")
    library = fmt_build / "libfmt.a"
    if not library.is_file():
        candidates = list(fmt_build.rglob("libfmt.a"))
        if len(candidates) != 1:
            raise RuntimeError(f"Could not uniquely locate Magnus fmt archive in {fmt_build}")
        library = candidates[0]
    if output("xcrun", "lipo", "-archs", str(library)) != "arm64":
        raise RuntimeError(f"Magnus fmt probe archive is not device arm64: {library}")
    return library


def shared_fmt_link_probe(fex_build: Path, evidence_root: Path, magnus_fmt: Path) -> tuple[Path, Path]:
    libraries = [
        fex_build / "FEXCore/Source/libFEXCore.a",
        fex_build / "FEXCore/Source/libFEXCore_Base.a",
        fex_build / "FEXCore/Source/libJemallocLibs.a",
        fex_build / "External/tiny-json/libtiny-json.a",
        magnus_fmt,
        fex_build / "External/xxhash/cmake_unofficial/libxxhash.a",
        fex_build / "External/cephes/libcephes_128bit.a",
        fex_build / "External/SoftFloat-3e/libsoftfloat_3e.a",
    ]
    objects = [
        evidence_root / "bridge/FexRuntime.cpp.o",
        evidence_root / "bridge/KytyAdapter.cpp.o",
        evidence_root / "iphoneos/guestCpu.cpp.o",
        evidence_root / "iphoneos/cache.cpp.o",
    ]
    for path in [*libraries, *objects]:
        if not path.is_file():
            raise FileNotFoundError(path)
        if output("xcrun", "lipo", "-archs", str(path)) != "arm64":
            raise RuntimeError(f"Expected device arm64 compatibility-probe input: {path}")

    destination = evidence_root / "shared-fmt-link"
    destination.mkdir(parents=True, exist_ok=False)
    product = destination / "MagnusSharedFmtLinkProbe.dylib"
    mapping = destination / "MagnusSharedFmtLinkProbe.map"
    sdk = output("xcrun", "--sdk", "iphoneos", "--show-sdk-path")
    command = [
        "xcrun", "--sdk", "iphoneos", "clang++",
        "-target", "arm64-apple-ios17.4", "-isysroot", sdk,
        "-dynamiclib", "-Wl,-undefined,error", "-Wl,-map," + str(mapping),
        "-install_name", "@rpath/MagnusSharedFmtLinkProbe.dylib",
        *(str(path) for path in objects),
        "-Wl,-force_load," + str(libraries[0]),
        "-Wl,-force_load," + str(libraries[1]),
        *(str(path) for path in libraries[2:]),
        "-o", str(product),
    ]
    run(*command)
    if not product.is_file():
        raise RuntimeError("Shared-fmt compatibility probe did not produce a dylib")
    if output("xcrun", "lipo", "-archs", str(product)) != "arm64":
        raise RuntimeError("Shared-fmt compatibility probe is not arm64")
    return product, mapping


def make_placeholder(archive: Path) -> None:
    sdk = output("xcrun", "--sdk", "iphoneos", "--show-sdk-path")
    clang = output("xcrun", "--sdk", "iphoneos", "--find", "clang")
    with tempfile.TemporaryDirectory(prefix="magnus-shared-fmt-") as tmp_name:
        tmp = Path(tmp_name)
        source = tmp / "shared_fmt_placeholder.c"
        obj = tmp / "shared_fmt_placeholder.o"
        source.write_text(
            "/* Intentionally no exported symbols. The final Magnus app provides "
            "the sole fmt implementation. */\n"
            "static const int magnus_fex_fmt_placeholder = 0;\n"
        )
        run(
            clang, "-arch", "arm64", "-isysroot", sdk,
            "-miphoneos-version-min=17.4", "-c", str(source), "-o", str(obj),
        )
        archive.unlink()
        run("/usr/bin/ar", "-rcs", str(archive), str(obj))
    if output("xcrun", "lipo", "-archs", str(archive)) != "arm64":
        raise RuntimeError("Final-app fmt placeholder is not arm64")
    nm = subprocess.run(
        ["/usr/bin/nm", "-g", str(archive)], check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout
    if "_ZN3fmt" in nm or "fmt::" in nm:
        raise RuntimeError("Placeholder archive unexpectedly exports fmt symbols")


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
    evidence_root = evidence.parent
    evidence_root.mkdir(parents=True, exist_ok=True)

    magnus_fmt_root = source / "3rdparty/fmt"
    fex_fmt_root = fex_root / "External/fmt"
    magnus_version, magnus_header = fmt_version(magnus_fmt_root)
    fex_version, fex_header = fmt_version(fex_fmt_root)
    magnus_major = magnus_version // 10000
    fex_major = fex_version // 10000
    if magnus_major != fex_major:
        raise RuntimeError(
            "Refusing cross-major fmt sharing: "
            f"Magnus={magnus_version}, FEX={fex_version}"
        )

    fex_archive = fex_build / "External/fmt/libfmt.a"
    if not fex_archive.is_file():
        raise FileNotFoundError(f"Expected FEX fmt archive not found: {fex_archive}")

    # Do not infer compatibility merely from the shared major namespace. Build
    # Magnus's exact fmt and prove the already-built FEXCore/bridge can strictly
    # link against it with no unresolved-symbol fallback.
    magnus_probe_fmt = build_magnus_fmt(source, evidence_root)
    probe_product, probe_map = shared_fmt_link_probe(
        fex_build, evidence_root, magnus_probe_fmt
    )

    backup = fex_archive.with_name("libfmt.fex-standalone.a")
    if backup.exists():
        raise RuntimeError(f"Refusing to overwrite preserved FEX fmt archive: {backup}")
    original_hash = sha256(fex_archive)
    shutil.copy2(fex_archive, backup)
    make_placeholder(fex_archive)

    result = {
        "strategy": "single-final-app-fmt-after-strict-compatibility-probe",
        "magnus_fmt_version": magnus_version,
        "fex_fmt_version": fex_version,
        "fmt_major_namespace": magnus_major,
        "magnus_fmt_header": str(magnus_header),
        "fex_fmt_header": str(fex_header),
        "magnus_probe_fmt_archive": str(magnus_probe_fmt),
        "magnus_probe_fmt_sha256": sha256(magnus_probe_fmt),
        "shared_fmt_link_probe": str(probe_product),
        "shared_fmt_link_probe_sha256": sha256(probe_product),
        "shared_fmt_link_map": str(probe_map),
        "fex_real_archive_preserved": str(backup),
        "fex_real_archive_sha256": original_hash,
        "final_app_placeholder_archive": str(fex_archive),
        "final_app_placeholder_sha256": sha256(fex_archive),
        "reason": (
            "FEX standalone validation retained its real fmt. A second strict "
            "iPhoneOS link proved FEXCore and the Magnus bridge resolve against "
            "Magnus fmt before the duplicate FEX fmt archive was removed from "
            "the final app link."
        ),
    }
    evidence.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
