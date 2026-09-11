#!/usr/bin/env python3
"""Compile our bridge using the real FEX iPhoneOS build's ABI/header settings.

FEX source is not modified. No Linux diagnostic shims or fake SDK are allowed.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from check_iphoneos import verify_object


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--fex-build', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root, build = args.source.resolve(), args.fex_build.resolve()
    entries = json.loads((build / 'compile_commands.json').read_text())
    entry = next(e for e in entries if e['file'].endswith('/Interface/Context/Context.cpp'))
    command = entry.get('arguments') or shlex.split(entry['command'])
    if any('VIXL_SIMULATOR=1' in arg or 'LinuxDiagnosticCompat' in arg for arg in command):
        raise ValueError('A native iPhoneOS FEX configuration is required')
    flags, skip = [], False
    for value in command[1:]:
        if skip:
            skip = False
            continue
        if value in ('-o', '-MF', '-MT', '-MQ'):
            skip = True
        elif value not in ('-c', '-MD', '-MMD', entry['file']):
            flags.append(value)
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for source in ('bridge/FexRuntime.cpp', 'bridge/KytyAdapter.cpp'):
        obj = args.output.resolve() / (Path(source).name + '.o')
        subprocess.run([command[0], *flags, '-I', str(root / 'src'), '-I', str(root / 'bridge'),
                        '-c', str(root / source), '-o', str(obj)], cwd=entry['directory'], check=True)
        results.append(verify_object(obj))
    (args.output / 'results.json').write_text(json.dumps({
        'status': 'Bridge iPhoneOS object compilation only; no app link or runtime validation',
        'objects': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
