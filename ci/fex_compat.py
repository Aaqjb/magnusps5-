#!/usr/bin/env python3
"""Apply or verify the exact Magnus-owned native FEX diagnostic patch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('apply', 'verify'))
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'source.lock.json').read_text())
    patch = (ROOT / lock['fex_compat_patch']).resolve()
    if not patch.is_relative_to(ROOT):
        raise ValueError('Patch path escapes the project')
    data = patch.read_bytes()
    if hashlib.sha256(data).hexdigest() != lock['fex_compat_patch_sha256']:
        raise ValueError('FEX compatibility patch integrity mismatch')
    prefix = ['git', '-C', str(args.source.resolve())]
    revision = subprocess.check_output([*prefix, 'rev-parse', 'HEAD'], text=True).strip()
    if revision != lock['fex_revision']:
        raise ValueError('Unexpected FEX revision; patch requires review against a new version')
    subprocess.run([*prefix, 'diff', '--exit-code'], check=True)
    if args.mode == 'apply':
        subprocess.run([*prefix, 'diff', '--cached', '--exit-code'], check=True)
        subprocess.run([*prefix, 'apply', '--check', '--index', str(patch)], check=True)
        subprocess.run([*prefix, 'apply', '--index', str(patch)], check=True)
    actual = subprocess.check_output([
        *prefix, 'diff', '--cached', '--binary', '--no-ext-diff', '--no-textconv',
        '--no-renames', '--full-index', '--unified=3', '--no-color',
        '--src-prefix=a/', '--dst-prefix=b/'])
    if actual != data:
        raise ValueError('FEX changes differ from the reviewed compatibility patch')
    print(json.dumps({'fex_revision': revision, 'compat_patch_sha256': lock['fex_compat_patch_sha256'],
                      'scope': 'platform guards for diagnostics; no substitute CPU or OS functions'}, indent=2))


if __name__ == '__main__':
    main()
