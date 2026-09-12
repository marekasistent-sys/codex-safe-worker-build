# Pristine-only safe stderr diagnosis

The next manual run uses --pristine-only. It keeps Cargo --message-format=json,
the pinned Codex source, Rust 1.95.0 and the original compile arguments. It performs
one pristine compile, checks source and lockfile integrity, and stops on PASS or
FAIL. It does not apply logging.patch, compile the patched variant, execute tests,
or create/upload release artifacts. The upload step is disabled for this diagnostic
recipe. The existing full build path remains available in code for later review;
the published workflow explicitly selects only the diagnostic mode.

Structured Cargo JSON diagnostics remain unchanged. On failure, a separate pure
function examines captured stderr bytes in RAM and returns only one fixed category:
LOCKFILE_REJECTED, DEPENDENCY_RESOLUTION_FAILED, DEPENDENCY_DOWNLOAD_FAILED,
GIT_FETCH_FAILED, PACKAGE_OR_TARGET_SELECTION_ERROR, TARGET_NOT_INSTALLED,
RUST_VERSION_INCOMPATIBLE, BUILD_SCRIPT_FAILED, LINKER_NOT_FOUND, LINKER_FAILED,
CARGO_CONFIG_ERROR, or UNKNOWN. A frozen set of regular-expression patterns supplies
the mapping. No matching text, path, URL, command, environment or payload is returned.
No matches or conflicting categories return UNKNOWN. Raw stderr is neither printed,
persisted nor added to artifacts. Exceptions export no payload; uncertain process
outcomes stop without retry.

These categories are diagnostic hints, not proof of a root cause. The previous
pristine and patched failures do not identify the cause, and an empty Cargo JSON
stream does not establish one. After the next manually authorized run, search the
official OpenAI Codex upstream, issues, PRs and later commits for the observed
category and any safely established specific error before proposing a workaround.
If UNKNOWN remains, retain that uncertainty. No source workaround is included here.

Local tests cover every category, unknown and ambiguous inputs, path/URL/payload
non-export, process errors, no retry, one pristine compile, no patch/test execution,
and workflow diagnostic selection. No live Cargo build is run locally.
