---
tags: ["#plan", "#acp-bridge-auth"]
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-provider-auth-strategy-adr]]"
  - "[[2026-02-21-gemini-provider-auth-strategy-adr]]"
  - "[[2026-02-21-acp-bridge-auth-research]]"
  - "[[2026-02-21-gemini-bridge-auth-research]]"
  - "[[2026-02-21-provider-auth-billing-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `acp-bridge-auth` implementation plan

Extend `ClaudeProvider` and `GeminiProvider` with proactive OAuth token refresh and
API-key-override debug logging so that ACP bridge subprocesses authenticate reliably
without user intervention across both providers.

The Claude provider already has a v1 injection guard (`_load_claude_oauth_token`). This
plan adds the v2 token refresh increment and brings the Gemini provider to parity.

## Proposed Changes

Three source files are modified; one test file is added or extended.

**`src/vaultspec/protocol/providers/claude.py`** — currently has `_load_claude_oauth_token()`
which reads `accessToken` from `~/.claude/.credentials.json` and injects it as
`CLAUDE_CODE_OAUTH_TOKEN` if neither that env var nor `ANTHROPIC_API_KEY` is present. The
function has no expiry awareness and performs no refresh. The v2 increment adds expiry
checking and a stdlib-only `urllib.request` refresh call, conforming to the implementation
path described in [[2026-02-21-claude-provider-auth-strategy-adr]].

**`src/vaultspec/protocol/providers/gemini.py`** — currently performs no auth wrangling.
`prepare_process()` calls `os.environ.copy()` and then directly builds the process spec.
Two new module-level helper functions (`_load_gemini_oauth_creds`,
`_refresh_gemini_oauth_token`) and a three-branch auth check block are added after the
`env = os.environ.copy()` line, conforming to
[[2026-02-21-gemini-provider-auth-strategy-adr]].

**`src/vaultspec/protocol/tests/test_providers.py`** (existing) or a new sibling file
`test_provider_auth.py` — new test classes are added for the auth paths introduced in
Steps 1 and 2. The existing test patterns use `pytest`, `caplog`, `tmp_path`, and
`unittest.mock.patch`. The new tests follow those conventions exactly.

## Tasks

- Phase 1 — Claude token refresh (v2 increment)
    1. Extend `_load_claude_oauth_token()` with expiry awareness and refresh
    2. Add `logger.debug` for the `ANTHROPIC_API_KEY` override path in `prepare_process()`

- Phase 2 — Gemini OAuth wrangling (new)
    1. Add `_load_gemini_oauth_creds()` helper
    2. Add `_refresh_gemini_oauth_token()` helper
    3. Add three-branch auth check block in `GeminiProvider.prepare_process()`

- Phase 3 — Unit tests
    1. Claude auth test cases (five scenarios)
    2. Gemini auth test cases (five scenarios)

## Steps

- Name: Claude token expiry check and refresh
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p1-s1.md`)
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-21-claude-provider-auth-strategy-adr]], [[2026-02-21-acp-bridge-auth-research]]

---

- Name: Claude API-key-override debug log
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p1-s2.md`)
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-21-claude-provider-auth-strategy-adr]]

---

- Name: Gemini `_load_gemini_oauth_creds()` helper
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p2-s1.md`)
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-21-gemini-provider-auth-strategy-adr]], [[2026-02-21-gemini-bridge-auth-research]]

---

- Name: Gemini `_refresh_gemini_oauth_token()` helper
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p2-s2.md`)
- Executing sub-agent: vaultspec-complex-executor
- References: [[2026-02-21-gemini-provider-auth-strategy-adr]], [[2026-02-21-provider-auth-billing-research]]

---

- Name: Gemini three-branch auth check in `prepare_process()`
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p2-s3.md`)
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-21-gemini-provider-auth-strategy-adr]]

---

- Name: Claude provider auth unit tests
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p3-s1.md`)
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-21-claude-provider-auth-strategy-adr]]

---

- Name: Gemini provider auth unit tests
- Step summary: Step Record (`.vault/exec/2026-02-21-acp-bridge-auth/2026-02-21-acp-bridge-auth-p3-s2.md`)
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-21-gemini-provider-auth-strategy-adr]]

## Phase 1 — Claude token refresh (v2 increment in `claude.py`)

### What already exists

`_load_claude_oauth_token()` (lines 23–35 of `claude.py`) reads
`~/.claude/.credentials.json`, traverses the `claudeAiOauth` key, and returns
`accessToken` as a string or `None`. It does not check `expiresAt` and makes no
network call. The injection guard in `prepare_process()` (lines 115–123) calls this
function and injects the result as `CLAUDE_CODE_OAUTH_TOKEN` when neither that token nor
`ANTHROPIC_API_KEY` is present.

### What changes

`_load_claude_oauth_token()` is extended in place. After reading `accessToken` it reads
`expiresAt` from the same `claudeAiOauth` dict. Because `expiresAt` is a Unix timestamp
in **milliseconds**, it is divided by 1000 before comparing against `time.time()`. A
5-minute proactive buffer (300 seconds) is applied so that a token expiring imminently
is treated as expired.

If the token is still valid, the function returns it unchanged.

If the token is expired, the function reads `refreshToken` from the same dict and POSTs
to the Anthropic OAuth token refresh endpoint using `urllib.request` only — no new
dependencies are introduced. On a successful response the function deserialises the JSON
body, writes the updated `accessToken` and `expiresAt` back to `.credentials.json`
atomically (write to a sibling temp file, then `os.replace()` to swap), and returns the
fresh token. On any failure (network error, non-200 status, malformed JSON, missing
`refreshToken`) the function logs a `logger.warning` with the failure reason and returns
`None`. The caller already handles `None` by logging its own warning and proceeding
without injection.

The `import time` and `import tempfile` (or equivalent temp-file approach using
`pathlib`) are added to the existing import block at the top of `claude.py`. No other
imports are required.

A `logger.debug` line is added inside `prepare_process()` at the branch where
`ANTHROPIC_API_KEY` is detected, to confirm the key-override path was taken. This line
is at debug level to avoid polluting normal output; it is useful when users investigate
billing or auth routing issues.

### Acceptance criteria

- When `expiresAt / 1000 > time.time() + 300`, no refresh POST is issued and the
  existing `accessToken` is returned.
- When `expiresAt / 1000 <= time.time() + 300`, a POST is issued to the OAuth endpoint.
  On a 200 response the new `accessToken` is returned and `.credentials.json` is
  overwritten atomically.
- When the POST fails (any exception or non-200), `logger.warning` is emitted and
  `None` is returned.
- When `ANTHROPIC_API_KEY` is present in env, `logger.debug` confirms the key-override
  path and no file I/O is performed on `.credentials.json`.
- No new third-party dependencies are introduced.
- `expiresAt` comparison uses integer millisecond division, not multiplication.

## Phase 2 — Gemini OAuth wrangling (new, in `gemini.py`)

### What already exists

`GeminiProvider.prepare_process()` calls `os.environ.copy()` (line 159) and then
immediately proceeds to write the system prompt temp file. There is no auth-related code
at all. The `import pathlib` is a TYPE_CHECKING-only import (lines 22–24); `json`,
`time`, and `urllib.request` are not imported in this file.

### What changes

Two module-level helper functions are added above the `GeminiProvider` class definition,
following the same structural placement as `_load_claude_oauth_token()` in `claude.py`.

**`_load_gemini_oauth_creds()`** opens `~/.gemini/oauth_creds.json` using
`pathlib.Path.home() / ".gemini" / "oauth_creds.json"`. This path resolves correctly on
Windows via `pathlib`. It returns the parsed JSON dict on success, or `None` if the file
is absent, unreadable, or not valid JSON. No exception propagates to the caller.

**`_refresh_gemini_oauth_token(creds: dict)`** takes the parsed creds dict, reads
`refresh_token`, `client_id`, `client_secret`, and `token_uri`. It POSTs to `token_uri`
using `urllib.request` with `grant_type=refresh_token`. On a 200 response it updates
`access_token` and `expiry` in the dict, writes the updated dict back to
`~/.gemini/oauth_creds.json` atomically (temp file + `os.replace()`), and returns the
updated dict. On any failure it logs `logger.warning` with the reason and returns
`None`. The `creds` dict is not mutated on failure.

The expiry field in `oauth_creds.json` is an ISO 8601 string (e.g.,
`"2026-02-21T12:00:00Z"`). Expiry comparison uses `datetime.datetime.fromisoformat()`
(available in Python 3.7+) or a stdlib-compatible equivalent. A 5-minute buffer is
applied to match the Claude provider's proactive refresh policy.

The three-branch auth check block is inserted in `prepare_process()` immediately after
`env = os.environ.copy()` (currently line 159) and before the system-prompt temp file
block. The structure mirrors the pseudocode in [[2026-02-21-gemini-provider-auth-strategy-adr]]:

- If `GEMINI_API_KEY` is in `env`: emit `logger.debug` confirming the key-override path
  and take no further action. The key propagates naturally via `os.environ.copy()`.
- Elif `~/.gemini/oauth_creds.json` exists: load the creds, check the `expiry` field
  with a 5-minute buffer. If expired, call `_refresh_gemini_oauth_token()` and log a
  warning if it returns `None`. If not expired, no action is taken. In all sub-cases the
  binary reads the file directly on startup — no env injection is needed or possible.
- Else: emit `logger.warning` directing the user to either set `GEMINI_API_KEY` or run
  `gemini auth login`. The subprocess is still spawned; it will produce a diagnosable
  error.

The `import pathlib` is moved out of the `TYPE_CHECKING` block so it is available at
runtime. `import json`, `import time`, `import datetime`, and `import urllib.request`
are added to the top-level imports.

### Acceptance criteria

- When `GEMINI_API_KEY` is in env, `logger.debug` fires and no file I/O is performed.
- When `oauth_creds.json` exists and `expiry` is in the future (plus 5-min buffer), no
  refresh POST is issued.
- When `oauth_creds.json` exists and `expiry` is in the past (within buffer), a POST is
  issued to `token_uri`. On success the file is rewritten atomically. On failure a
  warning is logged and the subprocess is spawned anyway.
- When neither `GEMINI_API_KEY` is set nor `oauth_creds.json` exists, `logger.warning`
  names both setup paths.
- `pathlib` is a runtime import (not TYPE_CHECKING-only) after this change.
- No new third-party dependencies are introduced.

## Phase 3 — Tests

### No-mock mandate

**Mocking, monkey-patching, stubbing, and skipping are unconditionally prohibited.**
`unittest.mock`, `MagicMock`, `patch`, `@patch`, `pytest-mock`, `monkeypatch` on
callables, and any other form of test double that replaces real behaviour with a fake
are banned. Tests that rely on these patterns do not pass code review regardless of
whether they turn green. The goal is production confidence, not passing tests. A test
that mocks the thing being tested proves nothing.

This mandate also shapes the **implementation design** in Phases 1 and 2. Functions
that hardcode file paths and call `urllib.request.urlopen` internally cannot be tested
without mocking. The implementation must therefore accept injectable parameters so that
tests can supply real values — real files, real servers — without substitution.

### Design constraint: dependency injection for testability

The Phase 1 and Phase 2 implementations must accept the following as explicit
parameters with production-safe defaults:

- **Credentials file path** (`creds_path: pathlib.Path | None = None`) — defaults to
  the real home-relative path. Tests supply a `tmp_path`-based real file.
- **OAuth endpoint URL** (`token_url: str | None = None`) — defaults to the real
  Anthropic / Google endpoint. Tests supply the URL of a real local HTTP server spun
  up in the test process.

This is not a workaround; it is correct design. Parameters that a function depends on
belong in its signature. Hardcoding home directory paths and production URLs into
function bodies is the antipattern, not the solution.

### Test file location and conventions

Tests are added to `src/vaultspec/protocol/tests/test_providers.py` (extending the
existing file) or a new sibling file `test_provider_auth.py`. All new test classes
carry `pytestmark = [pytest.mark.unit]` and follow the `caplog`/`tmp_path` fixture
patterns established in the existing test classes.

**File I/O**: all tests write real JSON credential files to `tmp_path` directories and
pass those paths explicitly via the injected `creds_path` parameter. No file path is
intercepted or replaced via any patching mechanism.

**Network calls**: tests that exercise the refresh flow spin up a real local HTTP
server using Python's stdlib `http.server.HTTPServer` (or `socketserver.TCPServer`)
in a `pytest` fixture, listening on `localhost:0` (OS-assigned port). The server
returns a real HTTP response with a real JSON body. The test passes this server's URL
via the injected `token_url` parameter. The server is torn down after the test. No
`urlopen` substitution of any kind is used.

**Environment variables**: tests that exercise the API-key-override path set and unset
real environment variables using `os.environ` directly within the test, restoring them
in teardown (or using `monkeypatch.setenv` which is permitted for env vars — env var
manipulation is not mocking). The `prepare_process()` call is real; the env dict it
reads from is the real `os.environ` state at call time.

### Claude auth test cases (five scenarios)

These test `_load_claude_oauth_token()` and the injection guard in
`ClaudeProvider.prepare_process()` by supplying real inputs.

- **Valid token, no refresh triggered**: write a real credentials JSON to `tmp_path`
  with `expiresAt` set to `(time.time() + 3600) * 1000`. Call `_load_claude_oauth_token(creds_path=tmp_creds)`.
  Assert the returned token equals `accessToken` from the file. Assert the file is
  unmodified (compare mtime or content).
- **Expired token, refresh succeeds**: write a real credentials JSON with `expiresAt`
  set to `(time.time() - 1) * 1000`. Start a real local HTTP server that returns
  `{"access_token": "new-token", "expires_in": 3600}`. Call
  `_load_claude_oauth_token(creds_path=tmp_creds, token_url=server_url)`. Assert the
  returned token is `"new-token"`. Assert the credentials file on disk now contains
  the updated `accessToken`.
- **Expired token, refresh fails (server returns 400)**: write expired credentials.
  Start a real local HTTP server that returns HTTP 400. Call
  `_load_claude_oauth_token(creds_path=tmp_creds, token_url=server_url)`. Assert
  `logger.warning` is emitted via `caplog`. Assert `None` is returned. Assert the
  credentials file on disk is unchanged.
- **Credentials file missing**: call `_load_claude_oauth_token(creds_path=tmp_path / "nonexistent.json")`.
  Assert `None` is returned with no exception raised.
- **`ANTHROPIC_API_KEY` in env**: set `os.environ["ANTHROPIC_API_KEY"] = "test-key"`,
  call `prepare_process()`, assert `CLAUDE_CODE_OAUTH_TOKEN` is absent from the
  returned `ProcessSpec.env`, assert `logger.debug` is emitted. Restore env in
  teardown.

### Gemini auth test cases (five scenarios)

These test `_load_gemini_oauth_creds()`, `_refresh_gemini_oauth_token()`, and the auth
block in `GeminiProvider.prepare_process()`.

- **Valid token, no refresh triggered**: write a real `oauth_creds.json` to `tmp_path`
  with `expiry` 5+ minutes in the future. Call
  `_load_gemini_oauth_creds(creds_path=tmp_creds)`. Assert the returned dict matches
  the file contents. Assert no warning is logged and the file is unmodified.
- **Expired token, refresh succeeds**: write expired creds with real `token_uri` field
  set to the local test server URL. Start a real local HTTP server returning
  `{"access_token": "refreshed", "expires_in": 3600}`. Call
  `_refresh_gemini_oauth_token(creds, token_url=server_url)`. Assert the returned dict
  has the updated `access_token`. Assert the credentials file on disk is updated
  atomically (original content gone, new content present).
- **Expired token, refresh fails (server returns 500)**: start a real local HTTP
  server returning HTTP 500. Assert `logger.warning` fires. Assert `None` is returned.
  Assert the credentials file is unchanged.
- **Credentials file missing, no `GEMINI_API_KEY`**: call `prepare_process()` with
  `creds_path` pointing to a nonexistent file and `GEMINI_API_KEY` absent from env.
  Assert `logger.warning` names both setup paths.
- **`GEMINI_API_KEY` present**: set `os.environ["GEMINI_API_KEY"] = "test-key"`, call
  `prepare_process()`, assert `logger.debug` fires, assert no file I/O occurs on the
  (nonexistent) creds path (verified by observing the creds file path was never
  opened — no mock needed; simply don't create the file and assert no exception).
  Restore env in teardown.

### Acceptance criteria

- All ten test cases pass under `pytest -m unit` with zero mocks, patches, stubs, or
  skips of any kind.
- Every test that exercises a network path uses a real local HTTP server; no
  `urlopen`, `requests`, or HTTP client is intercepted.
- Every test that exercises file I/O reads and writes real files in `tmp_path`.
- `caplog` assertions verify exact log level (`DEBUG` vs `WARNING`) and message
  substring for each path.
- Atomic write is verified by reading the credentials file after the call and asserting
  the full updated content is present — no partial writes, no temp files left behind.

## Parallelization

Phase 1 (Claude) and Phase 2 (Gemini) are independent and can be dispatched to two
separate executor agents in parallel. Phase 3 (tests) depends on both Phase 1 and
Phase 2 being complete; it must run after both are merged. Within Phase 2, steps 2-s1
and 2-s2 (the two helper functions) are independent and could be parallelized, but
because they live in the same file a single sequential executor is preferred to avoid
merge conflicts.

## Verification

**Automated gates (all must pass):**

- `pytest -m unit src/vaultspec/protocol/tests/` — all pre-existing tests continue to
  pass; all new auth tests pass.
- `ruff check src/vaultspec/protocol/providers/claude.py src/vaultspec/protocol/providers/gemini.py`
  — no lint errors introduced.
- `mypy src/vaultspec/protocol/providers/claude.py src/vaultspec/protocol/providers/gemini.py`
  — no new type errors; `pathlib` is a runtime import in `gemini.py`.

**Correctness checks requiring reviewer attention:**

The `expiresAt` millisecond division is a known footgun (documented in
[[2026-02-21-claude-provider-auth-strategy-adr]]). Code review must explicitly verify
that `expiresAt / 1000` (not `expiresAt * 1000`) is used. The real-file tests make
this easier to catch because test values are actual timestamps, not magic mock numbers.

Atomic write correctness (temp file in the same directory as the target, then
`os.replace`) is exercised by the real-file tests — after the call, the test reads the
target file and confirms updated content is present and no temp file remains. The
reviewer confirms the temp file is in the same directory (same filesystem) to guarantee
atomicity on all platforms.

**End-to-end validation:**

Both Claude and Gemini sessions are fully authenticated in this environment. The
end-to-end test path is: intentionally write an expired token into a `tmp_path`
credentials file, call the refresh function against a real local HTTP server that
returns a valid token shape, confirm the file is updated and the token is injected.
This is exercised by the Phase 3 tests. No mocks needed, no live Anthropic/Google
endpoints hit in CI — the local server provides the real HTTP exchange.
