# HTTP-client compile/run split

Run 7's null failure names do not confirm issue 43616 or prove that a test
executable existed. This diagnostic-only change separates the two effects.

1. HTTP_CLIENT_LIB_COMPILE runs:
   cargo test --locked --release --target x86_64-pc-windows-msvc
   -p codex-http-client --lib --no-run --message-format=json
2. Successful Cargo output is consumed in RAM to select exactly one compiler
   artifact for the codex_http_client library test and its expected source file.
   Its executable must exist in the target's release/deps directory, have the
   expected executable name, and traverse no symlink/junction. Missing or
   ambiguous artifacts fail closed before COMPILE_PASS.
3. Only after COMPILE_PASS, HTTP_CLIENT_LIB_TEST directly executes that already
   built binary. No second Cargo invocation or implicit rebuild is performed.

Compile failures emit only existing diagnostic categories and the fixed phase
failure enum. Raw output, artifact paths and compiler payloads are not emitted.
Test failures emit only the existing allowlisted test names and count. Unknown
summaries remain null/null. Timeouts or launch errors are UNKNOWN, with no retry.
The original test working directory and sanitized environment are preserved.

No Codex source, dependency, patch, toolchain, workflow or artifact allowlist
changes. Compile PASS is recorded separately in provenance; all later tests and
build steps keep their order. No workflow is dispatched by this update.

UPSTREAM-FIRST remains mandatory: after an authorized diagnostic run, research
the compile category before any workaround; if the complete failed-test set
matches the five tests in upstream issue 43616, report that exact name-set match
and stop. Matching names alone do not prove identical underlying Schannel errors.
No matching result is claimed from the earlier null/null evidence.
