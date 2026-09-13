#!/usr/bin/env python3
"""Strictly link the real native FEX archives and bridge into a diagnostic dylib.

This is a link test, not the Magnus app, an IPA, or a device execution test.
Whole-core archive loading keeps missing symbols visible. Support libraries
resolve the core's references normally. No undefined-symbol fallback, substitute
functions or dead stripping are used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from check_iphoneos import output, verify_object

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fex-build', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()
    build, evidence = args.fex_build.resolve(), args.evidence.resolve()
    libraries = [
        'FEXCore/Source/libFEXCore.a', 'FEXCore/Source/libFEXCore_Base.a',
        'FEXCore/Source/libJemallocLibs.a', 'External/tiny-json/libtiny-json.a',
        'External/fmt/libfmt.a', 'External/xxhash/cmake_unofficial/libxxhash.a',
        'External/cephes/libcephes_128bit.a', 'External/SoftFloat-3e/libsoftfloat_3e.a',
    ]
    archives = [build / name for name in libraries]
    objects = [evidence / 'bridge/FexRuntime.cpp.o', evidence / 'bridge/KytyAdapter.cpp.o',
               evidence / 'iphoneos/guestCpu.cpp.o', evidence / 'iphoneos/cache.cpp.o']
    for path in [*archives, *objects]:
        if not path.is_file():
            raise FileNotFoundError(path)
        if output('xcrun', 'lipo', '-archs', path) != 'arm64':
            raise RuntimeError(f'Expected device arm64 input: {path}')
    destination = evidence / 'link'
    destination.mkdir(parents=True, exist_ok=False)
    library = destination / 'MagnusFexLinkProbe.dylib'
    mapping = destination / 'MagnusFexLinkProbe.map'
    sdk = output('xcrun', '--sdk', 'iphoneos', '--show-sdk-path')
    command = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-target', 'arm64-apple-ios17.4',
               '-isysroot', sdk, '-dynamiclib', '-Wl,-undefined,error',
               '-Wl,-map,' + str(mapping), '-install_name', '@rpath/MagnusFexLinkProbe.dylib',
               *(str(path) for path in objects),
               *('-Wl,-force_load,' + str(path) for path in archives[:2]),
               *(str(path) for path in archives[2:]), '-o', str(library)]
    print(' '.join(command), flush=True)
    subprocess.run(command, check=True)
    product = verify_object(library)
    lock = json.loads((ROOT / 'source.lock.json').read_text())
    (destination / 'results.json').write_text(json.dumps({
        'status': 'Strict whole-archive FEX/bridge link only; no Magnus app or device execution',
        'source_revision': lock['source_revision'], 'fex_revision': lock['fex_revision'],
        'fex_compat_patch_sha256': lock['fex_compat_patch_sha256'], 'product': product,
        'input_archives': [{'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                           for name, path in zip(libraries, archives)],
    }, indent=2) + '\n')

    # The strict link above deliberately validates FEX with its own real fmt.
    # The complete Magnus executable also links Kyty/Magnus's fmt archive. If
    # both fmt archives are carried into that final static link, their identical
    # fmt::v12 definitions collide. Only after this strict gate succeeds, prepare
    # the FEX build tree so the final app resolves FEX's fmt references from the
    # single Magnus/Kyty fmt implementation. This does not suppress linker errors.
    subprocess.run([
        sys.executable, str(ROOT / 'ci/prepare_shared_fmt.py'),
        '--source', str(ROOT / 'checkout'),
        '--fex-root', str(ROOT / 'fex'),
        '--fex-build', str(build),
        '--evidence', str(evidence / 'shared-fmt.json'),
    ], check=True)

    # The final executable has already been proven capable of linking with the
    # shared fmt arrangement. Patch only the reconstructed packaging verifier so
    # an Apple linker-map byte outside UTF-8 cannot crash Python after a successful
    # link. The patch helper exact-matches one expression and records hashes.
    subprocess.run([
        sys.executable, str(ROOT / 'ci/patch_build_ipa_reader.py'),
        '--source', str(ROOT / 'checkout'),
        '--evidence', str(evidence / 'build-ipa-reader-patch.json'),
    ], check=True)


if __name__ == '__main__':
    main()
