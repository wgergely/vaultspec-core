---
tags:
  - '#adr'
  - '#acp-bridge-auth'
date: '2026-02-21'
related:
  - '[[2026-02-21-gemini-bridge-auth-research]]'
  - '[[2026-02-21-provider-auth-billing-research]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `acp-bridge-auth` adr: `GeminiProvider OAuth wrangling + API key override` | (**status:** `accepted`)

## Problem Statement

`GeminiProvider.prepare_process()` performs no authentication wrangling before spawning the `gemini` binary as an ACP server. The binary reads `~/.gemini/oauth_creds.json` directly when no API key is present, so basic cases work without intervention. However, three failure modes are unaddressed:

1. OAuth credentials are expired and no refresh is attempted before spawn -- the subprocess hangs or throws a `FatalAuthenticationError` with no diagnosable log output from vaultspec.
1. Neither `GEMINI_API_KEY` nor `~/.gemini/oauth_creds.json` exists -- the binary falls into an interactive browser OAuth flow, hanging the headless ACP session silently.
1. `GEMINI_API_KEY` is set but invalid -- the binary fails with no vaultspec-level guidance on corrective action.

The gap is not injection (unlike the Claude provider, where `CLAUDE_CODE_ENTRYPOINT=sdk-py` actively suppresses credential-file reading and forces explicit `CLAUDE_CODE_OAUTH_TOKEN` injection). The gap is: no proactive token refresh, and no defensive warnings when auth is missing or stale.

## Considerations

### Auth priority in the Gemini CLI

`getAuthTypeFromEnv()` resolves auth in strict priority order:

| Priority | Env var / condition              | Auth type                         | Headless-safe?                      |
| -------- | -------------------------------- | --------------------------------- | ----------------------------------- |
| 1        | `GOOGLE_GENAI_USE_GCA=true`      | Google Cloud auth / browser OAuth | Only if `oauth_creds.json` is fresh |
| 2        | `GOOGLE_GENAI_USE_VERTEXAI=true` | Vertex AI (ADC)                   | Yes                                 |
| 3        | `GEMINI_API_KEY` present         | Direct API key (AI Studio)        | Yes — recommended headless path     |
| 4        | None of the above                | Browser OAuth flow                | No — hangs without TTY              |

There is no `CLAUDE_CODE_ENTRYPOINT`-equivalent for Gemini. The binary's auth path is determined entirely by env vars and the presence of the OAuth credentials file on disk. vaultspec cannot inject a raw OAuth access token via env var — the binary reads the JSON file directly.

### OAuth credentials file structure

`~/.gemini/oauth_creds.json` is written by `gemini auth login` and contains a standard Google OAuth payload:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": [...],
  "expiry": "2026-02-21T12:00:00Z"
}
```

The `refresh_token` is long-lived and can be used against Google's token endpoint (`https://oauth2.googleapis.com/token`, POST with `grant_type=refresh_token`) to obtain a fresh `access_token` before process spawn. The refreshed `access_token` must be written back to the file -- it cannot be injected via env var.

### Billing implications

As documented in \[[2026-02-21-provider-auth-billing-research]\]:

- `GEMINI_API_KEY` (AI Studio) and `gemini auth login` (OAuth / Code Assist for Individuals) are entirely separate billing systems.
- OAuth login confers the "Code Assist for Individuals" free entitlement: 1,000 req/day, 60 RPM. No credit card, no subscription required.
- `GEMINI_API_KEY` has a separate free tier (Flash-Lite 1,000 RPD) but is a distinct product with distinct quotas.
- Google Gemini Advanced / Google One AI Premium subscriptions provide zero benefit toward either the CLI or the API. They are completely separate products.

### Contrast with ClaudeProvider

`ClaudeProvider` (post-fix) explicitly:

1. Checks for `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_API_KEY` in env.
1. If neither is present, reads `~/.claude/.credentials.json`, extracts the `accessToken` (short-lived, ~1h), and injects it as `CLAUDE_CODE_OAUTH_TOKEN`.
1. Logs a warning if the file is absent or the token is missing.

This injection is required because `CLAUDE_CODE_ENTRYPOINT=sdk-py` suppresses the credential-file auth path in the `claude` binary -- without explicit injection, OAuth auth would silently fail even if the file is present and valid.

`GeminiProvider` does not have this suppression problem. The binary reads `oauth_creds.json` naturally. The required additions are narrower: proactive refresh of expired tokens before spawn, and defensive warnings when no auth path is viable.

## Constraints

- **No raw token injection path exists**: There is no Gemini env var accepting a raw OAuth `access_token`. Refreshed tokens must be written back to `~/.gemini/oauth_creds.json` on disk before the subprocess is spawned.
- **File write implies cross-process risk**: Writing a shared credentials file from vaultspec before spawning the subprocess creates a TOCTOU window if another Gemini process is running concurrently. This is an acceptable tradeoff given the alternative is silent auth failure.
- **Windows path**: The credentials file lives at `%USERPROFILE%\.gemini\oauth_creds.json`. `pathlib.Path.home() / ".gemini" / "oauth_creds.json"` resolves correctly on all platforms.
- **Vertex AI path is out of scope**: Vertex AI auth (ADC / `GOOGLE_GENAI_USE_VERTEXAI=true`) requires Google Cloud project configuration and is a separate deployment target. This ADR addresses the developer-local auth paths only.
- **Token refresh is best-effort**: If the refresh network call fails (offline, revoked credentials), the subprocess is still spawned and will fail on its own with a clearer error than "hanging for TTY". vaultspec logs a warning and proceeds.

## Implementation

The implementation is confined to `GeminiProvider.prepare_process()` in `src/vaultspec/protocol/providers/gemini.py`, following the env block that constructs `env = os.environ.copy()`.

### Decision: Three-state auth check

```
if GEMINI_API_KEY in env:

    # Override path — propagates naturally via os.environ.copy()

    # No wrangling needed. Log debug confirmation.

elif ~/.gemini/oauth_creds.json exists:

    # Default path — binary reads file directly.

    # Check expiry. If expired, attempt refresh via Google token endpoint.

    # Write refreshed token back to file.

    # If refresh fails, log warning and proceed (subprocess will give a clear error).

else:

    # No auth path — log a clear warning identifying both setup options.

    # Proceed anyway (subprocess will fail with a diagnosable error).

```

### OAuth refresh flow (default path)

When `oauth_creds.json` exists and the `expiry` field is in the past:

1. Read `refresh_token`, `client_id`, `client_secret`, `token_uri` from the file.
1. POST to `token_uri` (typically `https://oauth2.googleapis.com/token`) with:
   - `grant_type=refresh_token`
   - `refresh_token=<value>`
   - `client_id=<value>`
   - `client_secret=<value>`
1. On success: update `access_token` and `expiry` in the JSON, write back to the file atomically (write to a temp file alongside, then `os.replace()`).
1. On failure: log `logger.warning("Gemini OAuth token refresh failed: %s. Subprocess may fail to authenticate.")` and continue.

The refresh call uses `urllib.request` (stdlib) to avoid adding an HTTP client dependency for a single POST.

### API key override path

`GEMINI_API_KEY` propagates via `os.environ.copy()` with no additional action required. A `logger.debug` line confirms the path taken. This mirrors the behavior of `ANTHROPIC_API_KEY` on the Claude side.

### Fallback warning on API key failure

If `GEMINI_API_KEY` is set but the subprocess fails, the error surfaces from the `gemini` binary itself. vaultspec cannot intercept this at spawn time without attempting a preflight API call (which adds latency and complexity). The diagnostic path is therefore: the subprocess exits with a non-zero code and an auth error message, and the vaultspec orchestrator surfaces that error. No additional startup diagnostic is added for this case beyond the debug-level confirmation that the API key path was taken.

### Warning on missing auth

If neither `GEMINI_API_KEY` is present nor `~/.gemini/oauth_creds.json` exists:

```python
logger.warning(
    "No Gemini authentication found. Set GEMINI_API_KEY (from AI Studio) "
    "or run 'gemini auth login' to create ~/.gemini/oauth_creds.json. "
    "The subprocess may hang waiting for interactive auth."
)
```

## Rationale

The decision to lead with the OAuth credentials file (and apply proactive refresh) rather than requiring `GEMINI_API_KEY` reflects two findings from \[[2026-02-21-provider-auth-billing-research]\]:

1. The OAuth path is zero-cost (Code Assist for Individuals free quota). Requiring `GEMINI_API_KEY` would push all users toward a separately-billed product even when they have already authenticated via `gemini auth login`.
1. Token expiry is the primary failure mode. Proactive refresh before spawn eliminates the silent-hang failure class without requiring user intervention on a per-session basis.

The API key override exists for users who prefer a long-lived, non-expiring credential -- particularly in CI/CD or shared environments where `gemini auth login` is not practical. Long-lived API keys have no refresh burden and are the Gemini equivalent of `ANTHROPIC_API_KEY`.

The decision to not implement dynamic mid-process fallback (API key fails → switch to OAuth) reflects the startup-time nature of auth decisions. The `prepare_process()` call is a single point of configuration before spawn. Post-spawn auth switching would require IPC with the running binary, which the ACP protocol does not support.

The decision to use `urllib.request` for the token refresh POST avoids adding `httpx` or `requests` as a dependency for a single use case. The Gemini OAuth token endpoint is a simple POST with a well-defined response schema; no session management or redirect handling is needed.

## Consequences

**Positive**:

- OAuth token expiry is handled proactively, eliminating the silent-hang failure class.
- Users who run `gemini auth login` once get transparent renewal without manual re-authentication.
- `GEMINI_API_KEY` users are unaffected -- the override path adds zero overhead.
- Missing auth produces a clear, actionable warning rather than a silent hang.
- The implementation is confined to `prepare_process()` with no new dependencies.
- Behavioral parity with `ClaudeProvider`: both providers now have a documented auth priority, an override path, and defensive warnings.

**Negative**:

- Writing back to `~/.gemini/oauth_creds.json` from vaultspec is a side effect with cross-process implications. If another `gemini` process is active and also refreshing, the write could race. This is mitigated by the atomic `os.replace()` pattern but not fully eliminated.
- The refresh adds a network round-trip to `prepare_process()` on the first call after token expiry (~200ms on a typical connection). Subsequent calls hit the cache via the updated file.
- `urllib.request` error handling is more verbose than `httpx`. The implementation must handle connection errors, non-200 responses, and malformed JSON explicitly.
- The OAuth credentials file path is user-home-relative. In containerized environments where `HOME` is non-standard, the file may not exist even if the user intends OAuth auth. The warning in the "missing auth" case covers this.

**Future considerations**:

- If Google introduces a Gemini env var for raw token injection (analogous to `CLAUDE_CODE_OAUTH_TOKEN`), the refresh-and-write approach can be replaced with injection, eliminating the file write side effect.
- Vertex AI auth (ADC / `GOOGLE_GENAI_USE_VERTEXAI=true`) is a plausible future requirement for enterprise deployments. When added, it should be inserted before the OAuth file check in the priority ladder, mirroring the Gemini CLI's own priority order.
- If the refresh call failure rate in practice proves problematic (e.g., revoked tokens not detected until subprocess spawn), a preflight health check could be added -- but this is deferred until evidence of user impact.
