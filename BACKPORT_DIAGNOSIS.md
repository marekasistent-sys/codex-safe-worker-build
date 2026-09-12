# Stage 3B.4 backport verifier diagnosis

Run 34691324693 reported only the generic failure. Its destroyed runner cannot
be inspected retrospectively. Local reproduction on the exact Git commit and
published patch proves a postimage line-ending defect consistent with that run:
BASE, PATCH_HASH, clean status, PRE_HASH, the single PREIMAGE and git apply --check
all pass; applying the patch succeeds, then the old postimage check rejects it.

Base: 4a56d66ed9626d5a3ded5414c9d8b7f1a48ce065.
Canonical file blob: c8088326ad778931eda4081db9e9f4a63c59511b.
Canonical and local LF preimage SHA-256:
cecdbdb8652c0ae4cae9242920bb832faf43f451d6b4d92ff36872db4fa8805d.
PREIMAGE occurs exactly once. PRE_HASH was correct.

Correct LF postimage SHA-256:
ddf6f4dd8bcfc572df1f3e588298bba72b19bebccf66a1a2ca20a256576b4767.
The old POST_HASH, 969abc93302ab7bc06a14e4d11e1ae234523e1b569eb3c7e6a6add2f891597f1,
is exactly the SHA-256 of that same postimage converted to CRLF. The workflow
explicitly disables core.autocrlf. The earlier local fixture inherited host Git
configuration and therefore failed to expose this representation mismatch.

The verifier now checks both HEAD:file blob identity and canonical bytes (Git
blob SHA-1 plus SHA-256), then exact worktree content allowing only uniform LF
or uniform CRLF. Mixed line endings and every other byte difference fail closed.
The unchanged patch hash, one-file diff scope, clean source, index and exact
postimage checks remain mandatory. Only closed-set diagnostic constants escape
the exception handler; unknown errors reveal no exception text.

The upstream fix remains ace0078261329437224d4875b289647279a41fa1.
The patch, architecture probes, NASM build, Codex source/build/tests, artifact
allowlist and manual-only workflow are unchanged. No workflow is dispatched by
this change. No installation, authentication or model operation is involved.
