# Verified cloud results — 12 September 2026

[Passing GitHub Actions run](https://github.com/Aaqjb/magnusps5-/actions/runs/34674071987)
at build-setup commit `347e247494b20839b75e22d6f181d5cbd9abbd55`.

| Check | Result | What was established |
| --- | --- | --- |
| Source reconstruction | Pass | Exact source commit and complete Git tree matched the lock. |
| Production source audit | Pass | 183 required core compilation units selected; reviewed source hashes matched. |
| CPU-side regression executables | 7/7 pass | Host-call ABI, release assertions, shader metadata and resource-analysis tests ran on Linux. |
| Python checks | 9/9 pass | Source omission/content substitution, dependency preflight and integration preparation checks. |
| JIT-script tests | 6/6 pass | Mock debugger protocol tests; no phone debugger was exercised. |
| Apple SDK object builds | Pass | App frontend, JIT protocol, real cache support, CPU interface, FEX runtime and Kyty adapter compiled for device arm64. |
| Native FEX libraries | Pass | FEXCore, FEXCore_Base, allocator support and required support libraries built for iPhoneOS. |
| Strict FEX/bridge link | Pass | Both complete FEX core archives and our bridge linked into an iPhoneOS diagnostic dylib with missing symbols treated as errors. |
| Complete Magnus app / IPA | Not built | The link probe does not include the full Kyty renderer or app startup. |
| iPhone execution / game rendering | Not tested | No physical-device execution took place. |

Toolchain: Xcode 16.4 (16F6), iPhoneOS SDK 18.5, arm64, minimum OS 17.4.

## Input identity

- Reconstructed source: `b817b57a559d7cff6c62c212c9013c9ebd17e03c`.
- Kyty target: `2e315a3c62bf036c8225d5057ada1d70cd8063f1`.
- Reviewed core-source digest: `df5e61d1f2dea88330269f12bfab3f3e69407742c8980999b1106adfc8ed3752`.
- FEX base: `053c385ecc9090702e4959a1d96752ea918a6110`.
- Magnus FEX compatibility patch SHA-256:
  `45bd467feb86872a72b2edf9a828beb652d042e4f3cc957da1dcafc867471cc1`.

The exact native linker report and input archive hashes are retained in
[validation/native-link.json](validation/native-link.json).
The diagnostic dylib SHA-256 is
`7c007cd58d7aa8d6c81328fd5eeae69f6b75bd4ae4e600af9f8e2efc7edf4a7b`.
The downloadable Actions evidence ZIP was verified against SHA-256
`c736d9e765f85d4e8c19d3a4051b6150d791261ae5219ae5cde16e634a0ff7ec`.
Actions artifacts expire after three days; this report remains in the repository.

## Changes required to reach this result

The build now uses an explicit arm64 cross-compilation target rather than
Linux `/proc/cpuinfo` detection. A 13-line reviewed patch corrects platform
guards around fork-specific diagnostic reporting. The native link includes
Magnus's existing `src/ios/cache.cpp` implementation. Both FEX core archives
are force-loaded; support libraries resolve only functions the core requires.
No missing emulation functions are replaced with success-returning stubs.

## Remaining app work

The native FEX/bridge component can now be built and linked reproducibly.
The next integration work is the iOS startup/JIT and signal layer behind
`InstallStinger`, executable-memory mapping callbacks, complete typed HLE
registration, and compatible MoltenVK/FFmpeg builds. The complete app must
then pass its own link-map/core-identity checks and physical-device tests.

The current diagnostic dylib is not an IPA and must not be presented as a
working emulator release. See [CLOUD-BUILD.md](CLOUD-BUILD.md) for the build
commands and the scope of each check.
