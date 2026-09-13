#!/usr/bin/env python3
"""Verify that the final Magnus iPhoneOS executable reaches the real FEX path.

This is a static final-binary proof, not a substitute for physical-device
execution. It verifies call edges in the linked arm64 Mach-O rather than merely
checking that bridge/FEX symbols exist somewhere in the file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


BOOT_THREAD = "__ZN12_GLOBAL__N_110BootThreadENSt3__14__fs10filesystem4pathE"
INSTALL_STINGER = "__ZN6Magnus14InstallStingerEPKc"
SUCCESS_LOG = b"Magnus:Runtime:Info: actual FEX x86 execution check passed; guest CPU installed"

INSTALL_CALLEES = [
    "__ZN6Magnus6Bridge10FexRuntimeC1ERKN7FEXCore12HostFeaturesERNS2_15SignalDelegatorENS0_6MemoryERN6Common8HostCall8RegistryE",
    "__ZN6Magnus6Bridge11KytyAdapter7InstallEv",
    "__ZN6Magnus6Bridge10FexRuntime7MapCodeEyy",
    "__ZN6Magnus6Bridge10FexRuntime4CallEyNSt3__14spanIKyLm18446744073709551615EEEyy",
    "__ZN6Magnus6Bridge10FexRuntime9UnmapCodeEyy",
]

MAP_MARKERS = [
    "libmagnus_fex_bridge.a(FexRuntime.cpp.o)",
    "libmagnus_fex_bridge.a(KytyAdapter.cpp.o)",
    "libFEXCore.a(Context.cpp.o)",
    "libFEXCore.a(JIT.cpp.o)",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_objdump() -> list[str]:
    direct = shutil.which("llvm-objdump")
    if direct:
        return [direct]
    try:
        found = subprocess.check_output(
            ["xcrun", "--find", "llvm-objdump"], text=True
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        found = ""
    if found:
        return [found]
    raise RuntimeError("llvm-objdump is required to verify final runtime call edges")


def disassemble(tool: list[str], binary: Path, symbol: str) -> str:
    command = [
        *tool,
        "--disassemble",
        f"--disassemble-symbols={symbol}",
        "--symbolize-operands",
        str(binary),
    ]
    result = subprocess.run(
        command,
        check=True,
        text=True,
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout


def require_call(disassembly: str, callee: str, owner: str) -> int:
    needle = f"<{callee}>"
    position = disassembly.find(needle)
    if position < 0:
        raise RuntimeError(f"{owner} does not call required runtime target: {callee}")
    line = next((line for line in disassembly.splitlines() if needle in line), "")
    if "\tbl\t" not in line and " bl " not in line:
        raise RuntimeError(f"Required target is present but not as a branch-with-link call: {line}")
    return position


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--map", dest="map_file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    binary = args.binary.resolve()
    map_file = args.map_file.resolve()
    output = args.output.resolve()
    if not binary.is_file():
        raise FileNotFoundError(binary)
    if not map_file.is_file():
        raise FileNotFoundError(map_file)

    map_text = map_file.read_text(encoding="utf-8", errors="replace")
    missing_map = [marker for marker in MAP_MARKERS if marker not in map_text]
    if missing_map:
        raise RuntimeError(f"Final linker map is missing required runtime objects: {missing_map}")

    binary_bytes = binary.read_bytes()
    if SUCCESS_LOG not in binary_bytes:
        raise RuntimeError("Final executable is missing the FEX x86-execution success diagnostic")

    tool = find_objdump()
    boot = disassemble(tool, binary, BOOT_THREAD)
    install = disassemble(tool, binary, INSTALL_STINGER)

    boot_call = require_call(boot, INSTALL_STINGER, "BootThread")
    call_positions = [require_call(install, target, "InstallStinger") for target in INSTALL_CALLEES]
    if call_positions != sorted(call_positions):
        raise RuntimeError(
            "FEX startup/test call order changed: expected construct -> adapter install -> "
            "map test code -> execute through FEX -> unmap"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "status": "final-binary runtime path statically verified; physical-device execution still required",
        "binary": str(binary),
        "binary_sha256": sha256(binary),
        "linker_map": str(map_file),
        "linker_map_sha256": sha256(map_file),
        "boot_thread_calls_install_stinger": True,
        "install_stinger_call_order": INSTALL_CALLEES,
        "success_diagnostic_present": SUCCESS_LOG.decode(),
        "required_linked_objects": MAP_MARKERS,
        "physical_device_execution_verified": False,
    }
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
