# Release lockfile reconciliation: prepared, not executed

The [pinned release commit](https://github.com/openai/codex/commit/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a)
changes only codex-rs/Cargo.toml workspace version from 0.0.0 to 0.153.4.
Cargo.lock is absent from that commit's changes. The pinned official
[Windows release workflow](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/.github/workflows/rust-release-windows.yml)
invokes cargo build without --locked. These facts support a hypothesis; they do
not prove that Cargo will change only internal versions.

Local Rust/Cargo 1.95.0 was unavailable during preparation. No installation or
workflow dispatch was performed. Therefore the actual changed-entry count,
internal names, external dependency comparison and patch SHA-256 are UNKNOWN.
No Cargo-generated exact patch is claimed or applied by this commit.

The manual workflow now skips NASM/native compilation and selects a lockfile-only
diagnostic. Existing pinned Rust action installs the previously authorized runner
toolchain; exact rustc/cargo versions are checked. An existing Python with tomllib
and safe tar extraction is required; missing support stops without installation.

The helper exports the exact clean Git commit into a disposable source directory,
excluding .git and rejecting devices/escaping archive paths. The sole upstream
symlink, vendor/bubblewrap/LICENSE, is verified by its exact Git blob and materialized
as link-target text, matching a Windows core.symlinks=false checkout; no OS symlink
is created. Any other link is rejected. It invokes Cargo
metadata once with the existing lockfile and without --locked only in this isolated
diagnostic. It does not run cargo update, compile code, tests, auth or model actions.
Only the temporary lockfile may change. Output and metadata remain in RAM.

Workspace identities are derived from Cargo workspace members and checked against
their pinned manifests. Only packages inheriting release version 0.153.4 may have
their previous 0.0.0 version changed. Fixed-version local packages and non-workspace
dependencies must remain exact. Expected qualified internal dependency references
may change correspondingly; all other internal fields and lock format must match.
All external package entries must be structurally identical, including dependencies,
versions, sources and checksums. Any addition, removal or mutation stops the helper.

Safe report: changed entry count, changed internal package names, external version,
source/checksum change flags, and external addition/removal flags. Changed entry
count treats an external identity replacement as removal plus addition. External
names, source URLs and checksums are not reported. A rejected comparison produces
no patch. An accepted comparison generates a deterministic unified diff in TEMP,
reports its SHA-256, and deletes it with the disposable directory. No artifact is
uploaded or published; the next review must reconstruct the candidate and verify
the same hash before canonical inclusion.

Proposed later canonical sequence, only after successful measured reconciliation:
verify source pin and original lockfile digest; verify exact patch SHA-256;
git apply --check and apply that one-file patch; verify postimage digest and exact
scope; then run all existing --locked compilation/tests. This proposal is not yet
activated. Logging patch, NASM backport and build/test --locked arguments are unchanged.
