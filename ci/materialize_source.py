#!/usr/bin/env python3
"""Reconstruct the exact reviewed source; never fall back to the upstream base."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def output(*args, cwd=None):
    return subprocess.check_output([str(arg) for arg in args], cwd=cwd, text=True).strip()


def materialize(destination):
    lock = json.loads((ROOT / 'source.lock.json').read_text())
    if lock['format'] != 1:
        raise ValueError('Unsupported source lock format')
    for key in ('base_revision', 'source_revision', 'source_tree', 'kyty_revision', 'fex_revision'):
        if not re.fullmatch(r'[0-9a-f]{40}', lock[key]):
            raise ValueError(f'Invalid pinned revision: {key}')
    bundle = (ROOT / lock['bundle']).resolve()
    if not bundle.is_relative_to(ROOT.resolve()):
        raise ValueError('Bundle must be inside this repository')
    data = bundle.read_bytes()
    if len(data) != lock['bundle_size'] or hashlib.sha256(data).hexdigest() != lock['bundle_sha256']:
        raise ValueError('Source bundle integrity check failed; refusing the old core')
    if destination.exists():
        raise ValueError('Destination already exists; use a fresh directory')
    # The base is only the prerequisite for a Git delta bundle. It is never the
    # source passed to a build. The final commit and complete tree must both match.
    run('git', 'init', '--quiet', destination)
    run('git', 'fetch', '--no-tags', '--depth=1', lock['base_repository'], lock['base_revision'], cwd=destination)
    run('git', 'checkout', '--quiet', '--detach', lock['base_revision'], cwd=destination)
    run('git', 'bundle', 'verify', bundle, cwd=destination)
    run('git', 'fetch', '--no-tags', bundle, 'HEAD', cwd=destination)
    run('git', 'checkout', '--quiet', '--detach', lock['source_revision'], cwd=destination)
    if output('git', 'rev-parse', 'HEAD', cwd=destination) != lock['source_revision']:
        raise ValueError('Reconstructed commit mismatch')
    if output('git', 'rev-parse', 'HEAD^{tree}', cwd=destination) != lock['source_tree']:
        raise ValueError('Reconstructed tree mismatch')
    if output('git', 'status', '--porcelain', cwd=destination):
        raise ValueError('Reconstructed source is dirty')
    core_lock = json.loads((destination / 'reconstruction.lock.json').read_text())
    if core_lock['kyty']['target_revision'] != lock['kyty_revision']:
        raise ValueError('Kyty revision mismatch')
    print(json.dumps({key: lock[key] for key in ('source_revision', 'source_tree', 'kyty_revision')}, indent=2))
    print('Verified reconstructed source. This does not establish an app build or device execution.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT / 'checkout')
    args = parser.parse_args()
    materialize(args.destination.resolve())
