---
tags:
  - "#exec"
  - "#acp-bridge-auth"
date: "2026-02-21"
phase: "p2"
step: "s1"
related:
  - "[[2026-02-21-gemini-provider-auth-strategy-adr]]"
---

# `acp-bridge-auth` p2-s1: Gemini OAuth wrangling

## Status: completed

## Changes

**File:** `src/vaultspec/protocol/providers/gemini.py`

### Import fixes
- Moved `import pathlib` from `TYPE_CHECKING` block to top-level runtime imports
- Added `import json`, `import datetime`, `import urllib.parse`, `import urllib.request`

### New helpers

**`_load_gemini_oauth_creds(creds_path)`**
- Loads `~/.gemini/oauth_creds.json` (or injected path), returns parsed dict or `None`
- No exception propagates to caller

**`_refresh_gemini_oauth_token(creds, token_url, creds_path)`**
- POSTs to `token_uri` with `grant_type=refresh_token` using `urllib.request`
- On success: updates `access_token` and `expiry`, writes back atomically via temp file + `os.replace()`
- On failure: logs warning, returns `None` — input dict never mutated

**`_is_gemini_token_expired(creds)`**
- Parses ISO 8601 expiry with Z-suffix handling (Python <3.11 compat)
- Compares against `now + 5min` buffer

### `prepare_process()` changes
- Added `creds_path: pathlib.Path | None = None` keyword-only parameter
- Three-branch auth check inserted after `env = os.environ.copy()`:
  - `GEMINI_API_KEY` present → debug log, skip OAuth
  - `oauth_creds.json` found → check expiry, refresh if stale
  - Neither found → warning with actionable remediation message

## Verification
- `python -m py_compile` passes with no errors
