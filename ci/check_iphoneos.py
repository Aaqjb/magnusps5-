#!/usr/bin/env python3
"""Compile actual app/JIT/interface objects with Apple's device SDK, without stubs.

This is deliberately not an app link, emulator run, JIT execution or IPA export.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess


def output(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True).strip()


def verify_object(path):
    if output('xcrun', 'lipo', '-archs', path) != 'arm64':
        raise RuntimeError(f'Not an arm64 object: {path}')
    metadata = output('xcrun', 'vtool', '-show-build', path)
    if not re.search(r'platform\s+IOS\b', metadata) or 'IOSSIMULATOR' in metadata:
        raise RuntimeError(f'Not an iPhoneOS object: {path}')
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'platform': metadata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('Full Xcode and the iPhoneOS SDK are required')
    root = args.source.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    sdk = output('xcrun', '--sdk', 'iphoneos', '--show-sdk-path')
    evidence = {'xcode': output('xcodebuild', '-version'), 'sdk': sdk, 'objects': [],
                'status': 'iPhoneOS object compilation only; no app link or runtime validation'}
    units = [('ios/App/Main.mm', 'clang++', ['-std=c++20', '-fobjc-arc']),
             ('src/ios/jitProtocol.c', 'clang', ['-O2']),
             ('src/common/guestCpu.cpp', 'clang++', ['-std=c++20'])]
    for source, compiler, flags in units:
        obj = args.output / (Path(source).name + '.o')
        command = ['xcrun', '--sdk', 'iphoneos', compiler, '-target', 'arm64-apple-ios17.4',
                   '-isysroot', sdk, '-I', str(root / 'src'), *flags,
                   '-c', str(root / source), '-o', str(obj)]
        print(' '.join(command), flush=True)
        subprocess.run(command, check=True)
        evidence['objects'].append(verify_object(obj))
    subprocess.run(['python3', str(root / 'tools/check_jit_object.py'),
                    str(args.output / 'jitProtocol.c.o')], check=True)
    (args.output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(evidence['status'])


if __name__ == '__main__':
    main()
