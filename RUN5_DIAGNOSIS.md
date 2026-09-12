# Run 5: diagnostic-only update; upstream first

Run 34692196787, recipe b281a59cccb02adcdba88391d7062d2c9320f193,
passed NASM, native preflight and the Rust action. The verifier returned only
COMMAND_FAILED. It discarded captured subprocess output and did not publish
intermediate STEPS. The job has no traceback or phase markers. Consequently the
exact failing command, dependency and compiler error are UNKNOWN. Elapsed time
does not prove which command failed. No new build was run to reconstruct it.

This change emits fixed START/PASS states and failure enums for tool version
probes, source preparation and these unchanged commands:

| Failure enum | Existing command (target x86_64-pc-windows-msvc) |
| --- | --- |
| HTTP_CLIENT_LIB_TEST_FAILED | cargo test --locked --release --target TARGET -p codex-http-client --lib |
| CODEX_CLI_LIB_COMPILE_FAILED | cargo test --locked --release --target TARGET -p codex-cli --lib --no-run |
| SYNTHETIC_TEST_COMPILE_FAILED | cargo test --locked --release --target TARGET -p codex-app-server --test worker_safe_logging --no-run --message-format=json |
| SYNTHETIC_TEST_FAILED | existing synthetic executable and leak/summary checks |
| CODEX_RELEASE_BUILD_FAILED | cargo build --locked --release --target TARGET -p codex-cli --bin codex |

Captured output stays in RAM. Only fixed error-category labels are emitted;
these are hints, not proof of a dependency defect. No names, paths, snippets,
environment, compiler messages or exception payloads are exported. Unknown
errors remain UNKNOWN. There is no retry, artifact expansion or test removal.

## Upstream-first evidence and limits

The pinned Codex commit is dated 2026-09-04. Its
[CLI manifest](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/cli/Cargo.toml)
does declare a library target, so removing --lib has no established basis.

Searches of official openai/codex issues, PRs and commits covered Windows builds,
codex-http-client, locked builds, Rust 1.95 and HTTP-client commits after the pin.
No exact-error search is possible until that error has evidence.

- [Issue 43616](https://github.com/openai/codex/issues/43616) reports five Windows
  HTTP-client TLS fallback test failures on another commit. This is a user report
  in the upstream repository, not confirmation of the cause of this run.
- [Commit aa4a870](https://github.com/openai/codex/commit/aa4a870e0663edf9efc8a33035236c657f66f06d)
  (September 5, PR 43125) adds explicit Windows native voice tool selection.
- [Commit 008bbd5](https://github.com/openai/codex/commit/008bbd5884122dc95aaece19ecfe0fc6a59dcf36)
  (September 5, PR 43126) exposes Windows native tools through Bazel targets.
- [Commit ce7fbb3](https://github.com/openai/codex/commit/ce7fbb373b14b37a5d163735c395e355e272d618)
  (September 11, PR 44922) changes Windows voice release packaging and tools.

These post-pin changes do not establish a fix for the unknown failing Cargo
command. None is applied. After a manually authorized diagnostic run, identify
the failing command and sanitized error class, then search the exact upstream
error/dependency and review the smallest relevant official change before any
workaround. If classification is insufficient, retain UNKNOWN rather than
exposing raw logs or guessing.

## Independent action warning

The [exact pinned action manifest](https://github.com/dtolnay/rust-toolchain/blob/e081816240890017053eacbb1bdf337761dc5582/action.yml)
defines targets, target and components inputs, but no toolchain input. Its parse
step hardcodes 1.95.0. Remove only the unsupported toolchain input. The full action
SHA and Rust version checks remain unchanged. This warning is not attributed as
the cause of Run 5.

No workflow dispatch, authentication, model operation, installation or production
change is part of this diagnostic update.
