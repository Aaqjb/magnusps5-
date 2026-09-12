# MagnusPS5 reconstruction — cloud validation

This repository builds the reconstructed source based on Kyty revision
`2e315a3c62bf036c8225d5057ada1d70cd8063f1`. It does not use an existing IPA or an
old precompiled emulator library. The reconstruction is experimental, not a
working PS5 emulator release.

## Where the source is

`source/reconstruction.bundle` is a Git delta bundle, not an app binary. It
contains our reconstruction commits, including the actual FEX execution bridge,
on top of the pinned public MagnusPS5 base. To reconstruct the complete source:

```sh
python3 ci/materialize_source.py
```

The script checks the bundle's SHA-256 and verifies the final Git commit and
complete tree against `source.lock.json`. It stops if anything is missing or
mismatched: it never falls back to compiling the older base. Source files are
then in `checkout/`, including `BRIDGE-PROGRESS.md`, `IPA-BUILD.md`, the upstream
license, and third-party notices. Existing upstream authorship is preserved in
the bundle's commits. The base is fetched from
[BaconMakin/MagnusPS5](https://github.com/BaconMakin/MagnusPS5) at a fixed commit;
moving upstream branches are not build inputs.

## What Actions checks

Under **Actions → Reconstructed core and iPhoneOS compile → Run workflow**:

- Linux: actual production source-selection audit, Python/JavaScript checks,
  and seven compiled CPU-side regression executables.
- macOS: real iPhoneOS/arm64 compilation of the UIKit app source, JIT protocol
  and CPU interface; then a native iPhoneOS FEXCore build and compilation of our
  bridge against its real generated headers and ABI options.
- All steps are required. Compiler errors fail the run and are preserved in
  diagnostic artifacts. A failure does not silently select an older core.

Actions are SHA-pinned, use read-only repository access, retain small diagnostic
artifacts for three days, and use standard hosted runners. No signing secrets,
device credentials, game files, or original IPA are uploaded or required.

The selected Apple environment is `macos-15` with Xcode 16.4 and an iOS 17.4
deployment target. If GitHub removes that Xcode installation, the run should
fail visibly until the environment is deliberately updated.

The FEX cross-build uses `TUNE_CPU=none` and `TUNE_ARCH=generic`. This retains
Clang's explicit arm64 iPhoneOS target instead of trying to tune for a Linux
runner CPU through `/proc/cpuinfo`. It requires no edits to FEX source.

## What passing does not prove

These jobs do **not** link the complete app, produce an IPA, execute JIT on an
iPhone, render a game, or confirm entitlement availability. The FEX runtime
adapter previously executed real translated x86 test programs in Linux VIXL
simulation, but that does not establish Apple runtime readiness.

Remaining work includes the Darwin JIT/signal/allocation bootstrap, executable
mapping callbacks and complete typed HLE registration, plus compatible iOS
MoltenVK/FFmpeg dependencies and the final app link/device tests. The iPhoneOS
FEX build itself is an unvalidated experiment; no source edits or Linux-only
diagnostic shims are applied to the FEX dependency.

Once the missing platform integration and dependencies exist, the reconstructed
source has `tools/build_ipa.py`. That build requires a fresh device app, verifies
the updated core identity and new renderer objects in the final link map, and
only then packages an unsigned IPA. A passing object-compile job must not be
presented as that milestone.
