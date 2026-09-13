#!/usr/bin/env python3
"""Prepare the built Magnus app for SideStore transport without provisioning it.

The known-working Magnus 0.0.1 SideStore package carries an ad-hoc signature
whose requested entitlements are visible to the resigning tool.  The final
SideStore installation still supplies the user's real certificate/profile.

This step deliberately does NOT embed a provisioning profile and does NOT claim
physical-device execution.  It only makes the transport IPA match the capability
request of the working community package and verifies the result byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


REQUIRED_ENTITLEMENTS = {
    "get-task-allow": True,
    "com.apple.developer.kernel.extended-virtual-addressing": True,
    "com.apple.developer.kernel.increased-memory-limit": True,
    "com.apple.developer.kernel.increased-debugging-memory-limit": True,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def plist_from_codesign(app: Path) -> dict:
    proc = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(app)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    data = proc.stdout + b"\n" + proc.stderr
    start = data.find(b"<?xml")
    end_marker = b"</plist>"
    end = data.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError(
            "codesign did not return XML entitlements; output was: "
            + data.decode("utf-8", errors="replace")
        )
    return plistlib.loads(data[start : end + len(end_marker)])


def zip_payload(payload: Path, output: Path) -> None:
    if output.exists():
        output.unlink()
    # zip(1) preserves Unix executable mode bits and the bundle layout SideStore
    # expects.  -y preserves any symlinks should the app gain them in future.
    subprocess.run(
        ["/usr/bin/zip", "-qry", "-y", str(output.resolve()), "Payload"],
        cwd=payload.parent,
        check=True,
    )


def verify_ipa(ipa: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="magnus-sidestore-verify-") as td:
        root = Path(td)
        with zipfile.ZipFile(ipa) as archive:
            names = archive.namelist()
            if any(name.endswith("embedded.mobileprovision") for name in names):
                raise RuntimeError("Transport IPA unexpectedly contains a provisioning profile")
            if "Payload/MagnusPS5.app/jit.js" not in names:
                raise RuntimeError("Transport IPA lost the bundled Magnus JIT script")
            if "Payload/MagnusPS5.app/MagnusPS5" not in names:
                raise RuntimeError("Transport IPA lost the Magnus executable")
            archive.extractall(root)

        app = root / "Payload/MagnusPS5.app"
        binary = app / "MagnusPS5"
        subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
        embedded = plist_from_codesign(app)
        missing = {
            key: value
            for key, value in REQUIRED_ENTITLEMENTS.items()
            if embedded.get(key) != value
        }
        if missing:
            raise RuntimeError(f"Final IPA signature is missing required entitlements: {missing}")
        return {
            "ipa_sha256": sha256(ipa),
            "signed_binary_sha256": sha256(binary),
            "jit_sha256": sha256(app / "jit.js"),
            "embedded_entitlements": embedded,
            "embedded_mobileprovision": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--source-ipa", type=Path, required=True)
    parser.add_argument("--output-ipa", type=Path, required=True)
    parser.add_argument("--entitlements", type=Path, required=True)
    parser.add_argument("--build-json", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    source_ipa = args.source_ipa.resolve()
    output_ipa = args.output_ipa.resolve()
    entitlements = args.entitlements.resolve()
    build_json = args.build_json.resolve()
    evidence = args.evidence.resolve()

    if not source_ipa.is_file():
        raise FileNotFoundError(source_ipa)

    apps = sorted(build_dir.glob("**/MagnusPS5.app"))
    apps = [p for p in apps if (p / "MagnusPS5").is_file()]
    if len(apps) != 1:
        raise RuntimeError(f"Expected exactly one built MagnusPS5.app, found {len(apps)}: {apps}")
    app = apps[0]
    binary = app / "MagnusPS5"
    jit = app / "jit.js"
    if not jit.is_file():
        raise FileNotFoundError(jit)
    if (app / "embedded.mobileprovision").exists():
        raise RuntimeError("Built app unexpectedly contains an embedded provisioning profile")

    pre_sign_binary_sha = sha256(binary)
    source_ipa_sha = sha256(source_ipa)

    entitlements.parent.mkdir(parents=True, exist_ok=True)
    entitlements.write_bytes(plistlib.dumps(REQUIRED_ENTITLEMENTS, fmt=plistlib.FMT_XML, sort_keys=True))

    # Ad-hoc transport signature only. SideStore must replace this with the
    # account-specific certificate and provisioning profile at installation.
    subprocess.run(
        [
            "codesign", "--force", "--sign", "-", "--timestamp=none",
            "--generate-entitlement-der", "--entitlements", str(entitlements), str(app),
        ],
        check=True,
    )
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)

    embedded = plist_from_codesign(app)
    missing = {
        key: value
        for key, value in REQUIRED_ENTITLEMENTS.items()
        if embedded.get(key) != value
    }
    if missing:
        raise RuntimeError(f"Ad-hoc signature is missing requested entitlements: {missing}")

    with tempfile.TemporaryDirectory(prefix="magnus-sidestore-package-") as td:
        staging = Path(td)
        payload = staging / "Payload"
        payload.mkdir()
        shutil.copytree(app, payload / app.name, symlinks=True)
        zip_payload(payload, output_ipa)

    verified = verify_ipa(output_ipa)

    metadata = json.loads(build_json.read_text()) if build_json.is_file() else {}
    metadata.update(
        {
            "status": "ad-hoc transport signed for SideStore; final provisioning and physical-device execution unverified",
            "sidestore_transport_signature": "ad-hoc",
            "requested_entitlements": REQUIRED_ENTITLEMENTS,
            "source_unsigned_ipa_sha256": source_ipa_sha,
            "sidestore_ipa_sha256": verified["ipa_sha256"],
            "sidestore_signed_executable_sha256": verified["signed_binary_sha256"],
            "jit_sha256": verified["jit_sha256"],
            "embedded_mobileprovision": False,
        }
    )
    build_json.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    result = {
        "status": "SideStore transport IPA prepared and independently re-opened/verified",
        "app": str(app),
        "pre_sign_binary_sha256": pre_sign_binary_sha,
        "post_sign_binary_sha256": sha256(binary),
        "source_unsigned_ipa_sha256": source_ipa_sha,
        "output": str(output_ipa),
        **verified,
        "required_entitlements": REQUIRED_ENTITLEMENTS,
        "final_signing_required": True,
        "physical_device_execution_verified": False,
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
