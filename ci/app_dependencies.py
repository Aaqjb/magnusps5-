#!/usr/bin/env python3
"""Build pinned FFmpeg 5 and verify official MoltenVK device archives."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tarfile
import urllib.request

MOLTENVK_URL = 'https://github.com/KhronosGroup/MoltenVK/releases/download/v1.4.2/MoltenVK-ios.tar'
MOLTENVK_SHA256 = 'b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1'
FFMPEG_REVISION = '9bc0bcce7a03701025d7002271ddc2ce4f351908'  # n5.1.8


def run(*args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def output(*args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('build-dependencies'))
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    archive = root / 'MoltenVK-ios.tar'
    urllib.request.urlretrieve(MOLTENVK_URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != MOLTENVK_SHA256:
        raise ValueError('MoltenVK release archive checksum mismatch')
    with tarfile.open(archive) as tar:
        # Extract only regular files/directories; the release's dylib symlink
        # and other platforms are not inputs to this static iPhoneOS app.
        members = [m for m in tar.getmembers() if m.isfile() or m.isdir()]
        tar.extractall(root, members=members, filter='data')
    library = root / 'MoltenVK/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a'
    if output('xcrun', 'lipo', '-archs', library) != 'arm64':
        raise ValueError('MoltenVK archive is not arm64')
    # Validate the contained Mach-O object platform, not just the archive name.
    metadata = output('xcrun', 'otool', '-l', library)
    platforms = set(re.findall(r'^\s*platform\s+(\S+)', metadata, re.M))
    if platforms not in ({'2'}, {'IOS'}):
        raise ValueError('MoltenVK archive is not for iPhoneOS')

    source = root / 'ffmpeg-source'
    run('git', 'init', '--quiet', source)
    run('git', 'fetch', '--depth=1', '--no-tags', 'https://github.com/FFmpeg/FFmpeg.git', FFMPEG_REVISION, cwd=source)
    run('git', 'checkout', '--detach', FFMPEG_REVISION, cwd=source)
    prefix = root / 'ffmpeg'
    sdk = output('xcrun', '--sdk', 'iphoneos', '--show-sdk-path')
    compiler = output('xcrun', '--sdk', 'iphoneos', '--find', 'clang')
    target = '-target arm64-apple-ios17.4'
    run(source / 'configure', f'--prefix={prefix}', '--target-os=darwin', '--arch=aarch64',
        '--enable-cross-compile', f'--cc={compiler}', f'--sysroot={sdk}',
        f'--extra-cflags={target}', f'--extra-ldflags={target}',
        '--enable-static', '--disable-shared', '--enable-pic', '--disable-programs',
        '--disable-doc', '--disable-debug', '--disable-avdevice', '--disable-avfilter',
        '--disable-postproc', '--disable-network', '--disable-autodetect',
        '--disable-securetransport', '--disable-videotoolbox', '--disable-audiotoolbox',
        '--disable-iconv', '--disable-bzlib', '--disable-lzma', '--disable-zlib', cwd=source)
    run('make', '-j3', cwd=source)
    run('make', 'install', cwd=source)
    hashes = {}
    for component in ('avcodec', 'avformat', 'avutil', 'swscale', 'swresample'):
        path = prefix / f'lib/lib{component}.a'
        if output('xcrun', 'lipo', '-archs', path) != 'arm64':
            raise ValueError(f'Wrong FFmpeg architecture: {path}')
        hashes[component] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / 'dependencies.json').write_text(json.dumps({
        'moltenvk_url': MOLTENVK_URL, 'moltenvk_archive_sha256': MOLTENVK_SHA256,
        'moltenvk_library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'ffmpeg_revision': FFMPEG_REVISION, 'ffmpeg_libraries': hashes,
        'status': 'Device dependency build only; game compatibility not established'
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
