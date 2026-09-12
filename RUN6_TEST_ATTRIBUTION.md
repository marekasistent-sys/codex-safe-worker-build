# Run 6: failed-test names only

Run 34692753051 on c0602bab4a10672199a5ab3828dfc1f48ce75180 recorded
HTTP_CLIENT_LIB_TEST_FAILED after successful version and source preparation
phases. It emitted UNKNOWN classification and no libtest summary. Captured
stdout/stderr were not retained. The failing test names and count are UNKNOWN;
even execution of individual tests, rather than a compile failure, is unproven.

The comparison with [upstream issue 43616](https://github.com/openai/codex/issues/43616)
is therefore NOT DETERMINABLE FROM RUN 6. The report is an issue in the official
repository, not a confirmed diagnosis for this recipe. It lists these five tests
under route_aware_client_pool::tls_fallback_tests:

- does_not_retry_a_non_replayable_streaming_request
- retries_a_native_tls_failure_after_another_request_caches_rustls
- retries_a_native_tls_protocol_failure_once_with_rustls
- retries_a_tls_protocol_failure_when_request_url_contains_certificate_markers
- successful_rustls_fallback_replays_the_request_and_reuses_the_destination

The diagnostic now outputs only failed_tests and failed_test_count for this
command's nonzero result. Names come from a reviewed allowlist of 81 public test
identifiers at the unchanged pinned source; source file Git blobs are recorded
in http-client-test-names.json. The parser requires exactly one complete failed
libtest summary, its final failures list, unique known names and a matching
nonzero count. It never emits process-derived strings or stderr. Missing,
unknown, partial or inconsistent results produce null/null (UNKNOWN), never a
claim of zero failures. Other phase enums remain unchanged.

The manifest includes the allowlist and parser. No Cargo arguments, tests,
Codex source, NASM patch, workflow, dependency or toolchain are changed. Fixtures
exercise exact issue names, different known names, CRLF, malformed summaries,
unknown/secret-like names, duplicate names and non-export of panic/stderr data.

No new workflow is dispatched. Only a future manually authorized run can supply
the discarded evidence. If its complete set equals the five names above, report
the name-set match and stop; that alone does not prove the same Schannel error.
If different known names are returned, research those exact names upstream before
any source change. If null is returned, retain UNKNOWN. No workaround is applied.
