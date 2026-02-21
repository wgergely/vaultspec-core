---
tags:
  - "#exec"
  - "#acp-bridge-auth"
date: "2026-02-21"
step: "p1-s1"
related:
  - "[[2026-02-21-claude-provider-auth-strategy-adr]]"
  - "[[2026-02-21-acp-bridge-auth-research]]"
---

# `acp-bridge-auth` p1-s1: Claude v2 token refresh — implementation

## Summary

Extended `_load_claude_oauth_token()` in `src/vaultspec/protocol/providers/claude.py`
from a simple credential read (v1) to a full expiry-aware OAuth refresh flow (v2).

## Changes

**File:** `src/vaultspec/protocol/providers/claude.py`

### New imports
- `time` — for `time.time()` expiry comparisons
- `tempfile` — for atomic credential file writes
- `urllib.error`, `urllib.parse`, `urllib.request` — stdlib-only HTTP for token refresh

### New module-level constants
- `_DEFAULT_CREDS_PATH` — `~/.claude/.credentials.json`
- `_DEFAULT_TOKEN_URL` — `https://console.anthropic.com/v1/oauth/token`
- `_EXPIRY_BUFFER_SECONDS = 300` — 5-minute proactive refresh buffer

### `_load_claude_oauth_token()` signature change
Added injectable parameters for testability without mocks:
```python
def _load_claude_oauth_token(
    creds_path: pathlib.Path | None = None,
    token_url: str | None = None,
) -> str | None
```

### Expiry check
- Reads `expiresAt` (milliseconds) from `claudeAiOauth`
- Converts to seconds via `/ 1000` (never multiply — documented footgun)
- Returns existing `accessToken` if `expiresAt/1000 > time.time() + 300`

### Refresh flow (when expired/missing)
- Reads `refreshToken`, `clientId`, `clientSecret` from credentials
- POSTs `grant_type=refresh_token` to `token_url` via `urllib.request` (no new deps)
- On 200: parses `access_token` + `expires_in`/`expires_at`, computes new `expiresAt` (ms)
- Writes atomically: temp file in same directory as credentials, then `os.replace()`
- On any failure: `logger.warning(...)` with reason, returns `None`

### `prepare_process()` update
Restructured auth guard to emit the required debug log:
```python
if "ANTHROPIC_API_KEY" in env:
    logger.debug("ANTHROPIC_API_KEY present — using API key path, skipping OAuth wrangling")
elif "CLAUDE_CODE_OAUTH_TOKEN" not in env:
    token = _load_claude_oauth_token()
    ...
```

## Verification

- Syntax check: `python -c "import ast; ast.parse(...)"` → OK
- Import check: `from vaultspec.protocol.providers.claude import _load_claude_oauth_token, ClaudeProvider` → OK
