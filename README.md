# Worker-only safe logging candidate — Stage 3A

Status: local design and workflow preparation only. No remote build has run. This recipe does not establish that the binary compiles or is safe for live credentials. Stage 3B requires separate authorization.

## Source and patch

Repository: https://github.com/openai/codex

Commit: `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`; release tag: `rust-v0.153.4`.

The commit is the checkout authority; the tag is descriptive. The supervisor requires a clean checkout and the exact HEAD. It verifies the entire original `codex-rs/http-client/src/client.rs` against Git blob `9cda749aa27581101a4f718644151f88c508100d`, including exactly two expected header expressions/events, before `git apply --check`. LF checkout is enforced through job-local Git environment configuration. A mismatch fails; no patch fuzz or fallback is attempted.

`logging.patch` removes response headers and URL from both successful `Request completed` events. Remaining fields: method, status, HTTP version. The unused `log_response` URL argument is renamed `_url`; signatures/call behavior are unchanged. Requests, authentication, OAuth, retry, TLS, cookie processing, keyring, protocol and model logic remain upstream. The test verifies that response headers are still returned to the caller.

This patch does not sanitize every Codex log. In particular, failure events, other crates and application-level errors may still log URLs or content. The result is a narrowly scoped candidate, not a general credential-leak guarantee.

## Workflow

Stage 3B.1 adds a pinned NASM source checkout and build before native preflight. Only manual `workflow_dispatch`, a single `windows-2022` job, maximum 180 minutes, no matrix or automatic rerun. Permissions are `contents: read`; all three checkouts use `persist-credentials: false`. No repository writes, deployment, signing, caching or OpenAI secrets. The ephemeral GitHub Actions token used by checkout/upload is GitHub infrastructure authorization; no personal access token is supplied to build/test children.

Actions pinned exactly as in the upstream release recipe:

| Action | Full commit |
|---|---|
| actions/checkout | de0fac2e4500dabe0009e67214ff5f5447ce83dd |
| dtolnay/rust-toolchain | e081816240890017053eacbb1bdf337761dc5582 |
| actions/upload-artifact | bbbca2ddaa5d8feaa63e36b76fdaad77386f024f |

Evidence: [upstream release workflow](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/.github/workflows/rust-release.yml), [Windows workflow](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/.github/workflows/rust-release-windows.yml), [toolchain](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/rust-toolchain.toml).

Preflight requires preinstalled VS 2022 x64 MSVC, SDK headers/libraries, NMAKE, MSVC LIB, Perl, Python, Git and rustup; NASM is compiled in the disposable workspace. It records runner image version, OS build, VS, cl/link file versions, selected and installed SDK versions, NASM and Git. Missing prerequisites stop the job without installation. The explicitly requested Rust action provisions Rust 1.95.0, target `x86_64-pc-windows-msvc`, upstream components clippy/rustfmt/rust-src. Exact rustc/cargo versions are checked afterward. No other tool installation, CMake or Ninja setup is present. Compiler environment changes are confined to the disposable job.

`windows-2022` is a moving hosted image label, not an immutable VM pin. VS/SDK patch versions are recorded rather than invented or silently installed. Upstream uses its own Windows runners; this hosted runner is not claimed identical. Existing Perl/tool availability, NASM source compilation and sufficient disk/RAM remain gates. A missing tool requires a new decision, not an automatic bootstrap.

Build command, from `codex-rs`:

```text
cargo build --locked --release --target x86_64-pc-windows-msvc -p codex-cli --bin codex
```

Job-only `LIBSQLITE3_FLAGS=SQLITE_DISABLE_INTRINSIC` follows upstream x64 Windows build practice. No `--workspace` or `--all-features`. Cargo resolves normal transitive dependencies and public downloads; the Rust setup and public dependency servers require network on the future hosted runner. This is not a hermetic or bit-for-bit reproducible build.

## Tests scheduled for the future job

1. `cargo test --locked --release --target x86_64-pc-windows-msvc -p codex-http-client --lib`.
2. `cargo test --locked --release --target x86_64-pc-windows-msvc -p codex-cli --lib --no-run` (CLI test compilation only).
3. Compile and execute only the injected `codex-app-server` integration test `worker_safe_logging`. Existing dependencies provide the real HTTP client and SQLite logging layer; no Cargo manifest/lockfile changes. This test does not start App Server or its auth/model services. Cargo may compile package auxiliary binaries for integration-test support; the product build still targets only codex-cli/codex.
4. Exact product release command above.

The synthetic test makes two loopback HTTP requests, one through each patched success-event path. A fresh in-RAM random seed produces fake Set-Cookie, JWT-shaped cookie, Authorization-like and normal-header values. No real credentials exist in the test home. It checks status/body/header delivery, exactly two success events and safe metadata. It scans SQLite plus existing WAL/SHM while the database is open, then all synthetic files after closing; missing WAL/SHM coverage fails. It checks raw stdout/stderr in memory and scans artifacts. UTF-8 and UTF-16 marker representations are covered by the supervisor. No raw child output is forwarded, including on test failure.

The fixture response is entirely synthetic; SQLite may naturally checkpoint its own synthetic test database when closed. This never opens or changes an existing worker database. TemporaryDirectory cleanup removes only the fresh synthetic tree, including on ordinary failure. Forced runner termination leaves no uploaded test data; the hosted VM is discarded. There is no automatic retry.

`tests/test_recipe.py` provides local stdlib-only tests for exact marker detection, safe names, nested WAL detection, redacted failures, environment filtering, no retry, local remote-run refusal, source mismatch, action pins and patch scope. These checks do not replace Rust compilation or the real client integration test. No Rust tests have run in Stage 3A.

## Artifact and provenance

Upload allowlist, only after all gates pass, retention seven days:

- `codex-safe.exe`
- `safe-logging-probe.exe` — the synthetic integration-test harness, for later local repeat without installing Rust
- `provenance.json` — source, patch SHA-256, recipe hashes/commit, workflow/run identity, runner/compiler versions and test summary; binary and harness SHA-256
- `SHA256SUMS`

No databases, WAL/SHM, raw compiler/test logs, environment dumps, personal config, source archive or generated random fixture values are uploaded. Binary debug/source paths may identify the generic hosted runner directory, not the local user's home. The probe is compiled before fixture generation.

Attestation is proposed but disabled. GitHub artifact attestations require an eligible plan/repository: public repositories are supported on current Free/Pro/Team plans; private/internal support requires Enterprise Cloud. Before enabling, review and pin a specific attestation action commit and add only `id-token: write` and `attestations: write` for that job. Attest both binary digests and the provenance document. Verify the expected repository, workflow, recipe commit and invocation. An unsigned JSON and a hash list from the same download do not authenticate origin. An attestation proves the build identity, not absence of vulnerabilities or secrets. [Official attestation documentation](https://docs.github.com/en/actions/concepts/security/artifact-attestations).

## Later local verification — do not run in Stage 3A

1. Download only the artifact from the explicitly approved successful run. Verify the recipe commit and source pin against the reviewed record. If attestations are enabled, verify their signatures and expected repository/workflow/commit using GitHub's documented verification procedure. Otherwise explicitly accept the weaker provenance based on the independently inspected authenticated run; do not call it an attested build.
2. Obtain the provenance document's SHA-256 independently from that verified run/attestation, not only from the downloaded hash list. `python scripts/postdownload.py --artifact <download-folder> --expected-provenance-sha <trusted-sha256>` checks the allowlist, provenance pin and both executable digests without executing them. This offline script does not itself verify GitHub signatures or workflow identity.
3. Copy verified files into a newly approved worker-only lab candidate directory; never replace desktop Codex or change PATH. No production integration.
4. With separate explicit approval, run `postdownload.py` with the same inputs plus `--run-approved-synthetic-test --empty-lab-parent <new-empty-lab-test-directory>`. The supervisor captures outputs, supplies an empty synthetic profile, starts only the verified probe, checks markers and removes its fresh temporary subtree. It never launches codex-safe.exe or accesses a live home/keyring.
5. Only after that passes, propose a separately authorized auth-only test. Do not repeat any historical refresh claim or live smoke. A successful synthetic test does not authorize login, refresh or model work.

## Publication boundary, cost and Stage 3B

Only files listed in `recipe-files.json` plus the manifest itself may be published into a clean recipe repository. Do not upload the parent lab, audit records, attachments, production, local paths, worker home, credentials or existing Git history. No GitHub repository or push exists from this step. GitHub naturally receives the selected repository/account and run metadata when the user later publishes; it receives no local account/profile data from these recipe files.

Planning estimate: 60–180 runner minutes for a cold build and tests, unmeasured; the job stops after 180 minutes and may fail for time/disk/memory. Standard hosted runners in public repositories are free under current policy. Private repositories consume plan allowance and then charge the repository owner; artifact storage is separate. Check the selected plan's current Windows rate and spending limit before approval. A rough compute illustration at $0.010/min is $0.60–$1.80 outside allowance, not a quote or guaranteed total. No billable run has occurred. [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Stage 3B authorization must identify repository owner/name, public/private visibility, approval to publish only the manifest allowlist, one manual workflow run, budget/time cap, and whether to add reviewed attestation support. Then: review final recipe commit; publish; dispatch once; monitor; fail closed on missing dependencies or failed tests; retrieve verified artifact metadata; report and stop. No automatic rerun, deployment, auth or model smoke. A failure needs diagnosis and a separately approved next run.

## Stage 3B.1: NASM source dependency

NASM repository: https://github.com/netwide-assembler/nasm
Pinned commit: `4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065`.
Checkout path: `nasm-src`, with the same full-SHA checkout action and no persisted credentials.

The build step verifies HEAD, Git tree, clean checkout and `version` equal to 3.02. It imports the installed VS 2022 x64 developer environment for this process and requires existing `nmake.exe`, `cl.exe`, `link.exe`, `lib.exe` and `perl.exe`. It records Perl's version and executes only `nmake /f Mkfiles\msvc.mak`. The upstream default target builds nasm.exe and ndisasm.exe; only nasm.exe is used. Official Perl rules generate the files absent from Git; no manual upstream source changes, configure/bootstrap workaround, downloads or installation occur. Missing tools or any failed command stop the job without retry.

After compilation, the step requires NASM version 3.02, rejects tracked source modifications and unexpected generated files, and records the generated file inventory, source commit/tree, compiler versions and binary SHA-256 in nasm-provenance.json. The NASM directory is appended only to GITHUB_PATH for later job steps. Native preflight verifies that the resolved NASM comes from nasm-src, runs --version and checks the binary hash against that evidence. Its runner metadata embeds the NASM evidence, so the existing provenance.json contains it without changing the four-file artifact allowlist. Neither NASM binaries nor the intermediate evidence file are uploaded separately.

The original Codex patch, Rust version, build/test commands, synthetic HTTP test and artifact allowlist are unchanged. No new workflow run is authorized by publication itself. NASM compilation has not been exercised locally; local checks cover recipe integrity, syntax and safety contracts. A future run may still fail on a dependency or unexpected generated output and must not be retried automatically.

Official pinned build references:
- https://github.com/netwide-assembler/nasm/blob/4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065/INSTALL
- https://github.com/netwide-assembler/nasm/blob/4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065/Mkfiles/msvc.mak

## Stage 3B.2 architecture diagnostics

See [ARCHITECTURE_DIAGNOSIS.md](ARCHITECTURE_DIAGNOSIS.md). NASM now builds in the same cmd.exe developer session as two fail-closed x64/Windows SDK compile probes. The environment is no longer reconstructed in PowerShell. This is diagnostic hardening: the existing failure may instead be the pinned NASM source including stringapiset.h without windows.h. No NASM source workaround is included, and this commit does not claim the failure is fixed. No new run was executed.

## Stage 3B.3 — exact upstream NASM Windows SDK backport

The base remains NASM 3.02 commit `4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065`.
The only authorized tracked NASM source change is `nasmlib/file.c`, using the exact hunk from official upstream fix `ace0078261329437224d4875b289647279a41fa1`:
https://github.com/netwide-assembler/nasm/commit/ace0078261329437224d4875b289647279a41fa1

`nasm-windows-sdk.patch` replaces direct stringapiset.h inclusion with the complete upstream explanatory comment, WIN32_LEAN_AND_MEAN and windows.h. Its SHA-256 is `591d8b3fb2d85465b58212ac0eb7a4a31273a856a815c08031aaafdc5d95b863`. The patch initializes Windows SDK architecture context naturally; no architecture macro workaround, forced include or newer source graph is used.

Before patching, the existing Python runtime verifies the base commit, clean source/index, patch hash, full file preimage hash and the exact three-line include fragment. Git apply must succeed without fallback. The resulting full file hash and tracked diff scope are checked before NMAKE and again after compilation. The public upstream source diff is logged before build generation. Additional tracked changes, mismatched images or a second patch application fail closed.

NASM provenance adds base source, upstream fix commit, patched file, patch SHA-256 and reason: official upstream Windows SDK compatibility fix. The architecture probes and same developer session remain required. All Codex pins, safe-logging patch, build/tests and artifact upload restrictions are unchanged. Existing Python is required; nothing is installed. The older Stage 3B.2 diagnosis describes the unpatched baseline; this section authorizes only this upstream backport.

Publication is preparation only. No fourth workflow run has been executed by the agent. Native success on this recipe remains to be verified by the user's next manually authorized run.