# MagnusPS5 reconstruction — cloud validation

This repository builds the reconstructed source based on Kyty revision
`d3d7bd33f8eb4996cf198c430bb2e4fa4bf518eb`. It does not use an existing IPA or an
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

Under **Actions → Reconstructed core and full iPhoneOS build → Run workflow**:

- Linux: actual production source-selection audit, Python/JavaScript checks,
  and nine compiled CPU-side regression executables, including page protection
  and thread cancellation, joining and ownership transfer.
- macOS: real iPhoneOS/arm64 compilation of the UIKit app source, JIT protocol
  and CPU interface; compilation of our bridge against FEX's real generated
  headers and ABI options; and an independent native iPhoneOS FEXCore build.
- A strict diagnostic dylib link force-loads both complete FEX core archives
  with our bridge, CPU interface and real Magnus cache-flush implementation.
  Support libraries resolve the core's references normally. Undefined symbols
  fail the link; no fallback symbol lookup or dead stripping is used. This
  dylib is not the Magnus app.
- The full app build uses verified MoltenVK 1.4.2 device libraries and a pinned
  FFmpeg 7.1.3 source build matching the core's libavcodec 61 API. Dependencies
  are cached after every installed file
  is hashed; restored caches must match those hashes and source pins.
- The complete app links the new core, FEX bridge and native startup. Packaging
  requires device arm64/iOS metadata, the reviewed core identity, and renderer
  and bridge implementation objects in the final link map. Only a passing
  package step uploads the unsigned IPA, retained for seven days.
- All steps are required. Compiler errors fail the run and are preserved in
  diagnostic artifacts. A failure does not silently select an older core.

Actions are SHA-pinned, use read-only repository access, retain small diagnostic
artifacts for three days, and use standard hosted runners. No signing secrets,
device credentials, game files, or original IPA are uploaded or required.

The selected Apple environment is `macos-15` with Xcode 26.3 and an iOS 17.4
deployment target. If GitHub removes that Xcode installation, the run should
fail visibly until the environment is deliberately updated.

Xcode 26 supplies the MetalFX frame-interpolation declarations used by the
existing iOS presentation code. The runtime iOS 26 availability checks remain.
The renderer uses real host threads with explicit cooperative cancellation and
joining because the older supported iOS C++ library lacks `std::jthread`.

The FEX cross-build uses `TUNE_CPU=none` and `TUNE_ARCH=generic`. This retains
Clang's explicit arm64 iPhoneOS target instead of trying to tune for a Linux
runner CPU through `/proc/cpuinfo`. It requires no edits to FEX source.

The full FEX compile keeps going through independent files after an error and
still fails the job. This gathers the real native-port errors in one run.
Bridge object compilation does not depend on a completed FEX archive, so a
dependency failure cannot conceal whether our own adapter compiles for iOS.

## Native FEX compatibility patch

The initial real SDK runs exposed two Windows-specific diagnostic blocks in the
pinned fork that could not compile for a native Apple target. This repository
carries a 13-line compatibility patch in `ci/patches/`:

- Gate frontend-specific counter reporting with the same `FEX_IOS_HOST`
  condition as the counters' producers.
- Keep the misaligned-atomic address report on Apple; restrict Windows virtual
  memory metadata queries to Windows builds.
- Exclude the rpmalloc snapshot reader on Apple, where this pinned fork's CMake
  configuration disables that allocator.

The patch adds no dummy CPU, allocation, signal or memory-query functions. The
atomic instruction handler and failure return remain in place. The workflow
verifies the base revision, patch SHA-256, and the complete staged diff before
and after building. This is a compatibility patch for this Magnus build; no
change is submitted to the upstream FEX repository.

## Device validation still required

The workflow attempts the complete app and IPA. Consult the recorded run result
to establish whether those stages passed. A passing build cannot execute JIT on
an iPhone, render a game or confirm entitlement availability. The FEX runtime
adapter executed real translated x86 test programs in Linux VIXL simulation;
that does not establish device runtime readiness.

Darwin JIT allocation, guest fault-register recovery and executable mapping
callbacks are implemented. Startup requires a real ARM execution check after
debugger detach and an x86 execution check through FEX. They have not been run
on a physical phone here. Asynchronous guest signal delivery and full HLE ABI
coverage remain incomplete. Only the explicit diagnostic compatibility patch
is applied to FEX; Linux test shims are not used in the device app.

The reconstructed source's `tools/build_ipa.py` requires a fresh device app, verifies
the updated core identity and new renderer objects in the final link map, and
only then packages an unsigned IPA. A passing object-compile job must not be
presented as that milestone.
