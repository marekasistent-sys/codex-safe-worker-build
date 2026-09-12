# Differential HTTP compilation, diagnostic only

Each manually dispatched job first compiles the pristine pinned Codex commit
3d2ee51ca2d5db578f328aa75e20aa22c0197c9a, then applies only the existing logging
patch and performs the same HTTP-client library compile. Both commands use
--locked --release --target x86_64-pc-windows-msvc -p codex-http-client --lib
--no-run --message-format=json with Rust 1.95.0 on the same runner.

The two variants use separate fresh target directories, the same Cargo download
cache, environment and checked Cargo.lock. No pristine test binary is executed.
Synthetic harness installation is deferred until after the comparison, so it
does not alter either compile input. Clean source is checked before and after
the pristine compile; patched file bytes and lockfile are checked after the
patched compile. Unexpected source changes stop the comparison.

Each completed variant emits exactly its PRISTINE_HTTP_COMPILE_PASS/FAIL or
PATCHED_HTTP_COMPILE_PASS/FAIL status. A nonzero pristine compile still permits
the one authorized patched comparison, not a retry of the same variant. A timeout
or process launch error stops immediately because process completion is uncertain.
PASS requires both Cargo success and one valid expected test executable.

Any failed variant blocks test execution and later builds. Only both PASS permit
the original pipeline to execute the already-built patched HTTP-client tests and
then the existing CLI/synthetic/release checks. There is no third HTTP compilation.

Interpretation:
- Pristine FAIL and patched FAIL: a compile failure exists without the logging
  patch. The patch is not required to produce failure; this alone cannot exclude
  an additional patch regression or prove identical causes.
- Pristine PASS and patched FAIL: stop as a suspected patch-induced compile
  regression and investigate before any workaround.
- Pristine FAIL and patched PASS: stop; the differing result requires review.
- Both PASS: compilation is demonstrated for both variants; HTTP test results
  remain a separate question.

## Structured diagnostics only

Following the [Cargo JSON protocol](https://doc.rust-lang.org/cargo/reference/external-tools.html#json-messages),
the parser reads only stdout JSON objects and projects fixed event types,
allowlisted package/target names, diagnostic levels, E followed by exactly four
digits, categories and the number of error diagnostics. Full package IDs are
never emitted. Unknown packages/targets/codes become null. Neither message,
rendered, spans, paths, command lines, environment nor stderr is inspected for
classification or exported. All --message-format=json calls use this parser.

Structured compiler errors are RUST_COMPILER_ERROR; errors compiling a
custom-build target are BUILD_SCRIPT_FAILED. A build-script-executed event alone
does not prove failure. Cargo's stable JSON protocol has no dedicated linker or
dependency-resolution failure discriminator; without permitted structured evidence
these remain UNKNOWN rather than being inferred from text. Zero JSON error
diagnostics does not mean a successful build; exit status controls PASS/FAIL.

UPSTREAM-FIRST remains required after results exist. No new workaround, upstream
source change, dependency change, installation, authentication or model operation
is introduced. No workflow is dispatched during recipe preparation/publication.
