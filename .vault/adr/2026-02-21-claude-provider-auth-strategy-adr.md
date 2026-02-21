---
tags:
  - "#adr"
  - "#acp-bridge-auth"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-bridge-auth-research]]"
  - "[[2026-02-21-provider-auth-billing-research]]"
---

# `acp-bridge-auth` adr: OAuth token injection with API key override in `ClaudeProvider.prepare_process()` | (**status:** `accepted`)

## Problem Statement

When `ClaudeProvider.prepare_process()` spawns the ACP bridge subprocess, the child
`claude` binary inherits the parent environment but cannot complete authentication
non-interactively. The parent Claude Code session authenticates via
`~/.claude/.credentials.json`, but the bridge sets `CLAUDE_CODE_ENTRYPOINT=sdk-py`
on the innermost `claude` subprocess, which suppresses the interactive credential-file
auth flow. If the `accessToken` in `.credentials.json` has expired (TTL ~1h), the child
raises `acp.exceptions.RequestError: Verify your account to continue`, terminating every
sub-agent invocation silently.

The project also needs to respect users who prefer API-key billing (`ANTHROPIC_API_KEY`)
over their Max/Pro subscription, without imposing OAuth wrangling on that path.

## Considerations

**Auth lookup order in the child `claude` binary:**

1. `ANTHROPIC_API_KEY` (API billing, pay-per-token)
2. `CLAUDE_CODE_OAUTH_TOKEN` (subscription billing, purpose-built for headless use)
3. `~/.claude/.credentials.json` (OAuth credentials file, requires interactive refresh)

**Billing isolation:** `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` are entirely
separate billing systems. Setting `ANTHROPIC_API_KEY` silently redirects all charges
to api.anthropic.com at pay-per-token rates, bypassing the user's Max subscription.
The correct zero-cost path for subscription users is `CLAUDE_CODE_OAUTH_TOKEN`.

**Token structure** (`~/.claude/.credentials.json` → `claudeAiOauth`):
- `accessToken` — short-lived (~1h), `sk-ant-oat01-...` prefix
- `refreshToken` — long-lived, used to obtain new access tokens via OAuth token refresh
- `expiresAt` — Unix timestamp in **milliseconds** (not seconds)
- `subscriptionType` — e.g., `max`

**OAuth token refresh endpoint:** Anthropic's standard OAuth refresh flow accepts a
`grant_type=refresh_token` POST with the `refreshToken` value and returns a new
`accessToken` with an updated `expiresAt`.

**Headless token alternative:** `claude setup-token` generates a purpose-built
long-lived `CLAUDE_CODE_OAUTH_TOKEN` intended for exactly this non-interactive,
subprocess-spawning use case. It is the cleanest long-term solution for users who
want to avoid refresh logic entirely.

**No supported M2M path:** There is no official machine-to-machine auth API for
Claude subscription billing (Anthropic issue #1454, unresolved as of 2026-02-21).
The approaches above are the only practical options.

## Constraints

- The bridge process is spawned with `CLAUDE_CODE_ENTRYPOINT=sdk-py`, which prevents
  the child `claude` binary from running its interactive auth flow regardless of
  whether `.credentials.json` exists.
- Runtime auth fallback mid-process is not feasible: if the child binary fails auth
  after process spawn, there is no IPC mechanism to inject a new token and retry.
  Diagnostic guidance is therefore limited to startup-time warnings.
- The `expiresAt` field is in Unix **milliseconds**; comparisons against `time.time()`
  require conversion (`expiresAt / 1000`).
- Anthropic's ToS ban on OAuth tokens in third-party apps (early 2026) does not apply
  here: vaultspec spawns the official `claude` CLI binary, not a third-party API client.

## Implementation

`ClaudeProvider.prepare_process()` applies auth in the following priority order at
process spawn time:

**Path 1 — API key override (highest priority)**

If `ANTHROPIC_API_KEY` is present in the inherited environment, no token wrangling is
performed. The key propagates naturally via `os.environ.copy()` and the child binary
will use it. This path accepts that the user has consciously opted into API billing.

If the child subsequently fails with the `RequestError: Verify your account` pattern,
a startup-time warning directs the user to either correct the API key or remove it to
allow OAuth fallback. Dynamic mid-process switching is not attempted.

**Path 2 — OAuth token injection (default)**

If `ANTHROPIC_API_KEY` is absent and `CLAUDE_CODE_OAUTH_TOKEN` is not already set:

1. Read `~/.claude/.credentials.json` → `claudeAiOauth`.
2. Check `expiresAt` (ms): if `expiresAt / 1000 > time.time() + buffer`, the
   `accessToken` is still valid — inject it as `CLAUDE_CODE_OAUTH_TOKEN`.
3. If expired, use `refreshToken` to POST to Anthropic's OAuth token refresh endpoint.
   On success, write the refreshed `accessToken` (and updated `expiresAt`) back to
   `.credentials.json` and inject the new token. On failure, log a warning and proceed
   without injecting (child will likely fail auth).

The current implementation (v1) performs step 1 and 2 but not step 3. Token refresh
(step 3) is the next planned increment — see [[2026-02-21-acp-bridge-auth-research]].

**Path 3 — Missing auth warning**

If neither `ANTHROPIC_API_KEY` is set nor `.credentials.json` is readable/present, a
`logger.warning` is emitted at spawn time identifying the gap. No exception is raised
at this point; the child process will surface the auth error directly.

The injection guard is:

```python
if "CLAUDE_CODE_OAUTH_TOKEN" not in env and "ANTHROPIC_API_KEY" not in env:
    token = _load_claude_oauth_token()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    else:
        logger.warning(
            "No Claude OAuth token found in ~/.claude/.credentials.json "
            "and ANTHROPIC_API_KEY is not set — child agents may fail to authenticate"
        )
```

This guard preserves any pre-existing `CLAUDE_CODE_OAUTH_TOKEN` in the environment
(e.g., set by `claude setup-token` in the user's shell profile) and does not
interfere with explicit API key usage.

## Rationale

**Why OAuth injection over API-key-only:** The primary user profile is a Max/Pro
subscriber. Requiring them to generate an API key adds separate billing and contradicts
the zero-additional-cost design intent. `CLAUDE_CODE_OAUTH_TOKEN` is explicitly
designed by Anthropic for non-interactive, headless invocation under subscription
billing — it is the correct solution for this use case.

**Why allow API key override:** A significant minority of users may prefer API billing
(granular cost control, no subscription), use vaultspec in CI environments with an API
key injected as a secret, or lack a subscription entirely. Respecting `ANTHROPIC_API_KEY`
when present requires no code change and matches the child binary's own priority order.

**Why not raise on missing auth:** Failing loudly at spawn time with an exception would
mask cases where a user has deliberately configured their environment in an unusual
way (e.g., running a custom `claude` binary that accepts different auth). Warning is the
appropriate severity — the error will surface from the child process if auth truly fails.

**Why not use `claude setup-token` as the mandatory path:** It requires an additional
manual setup step not documented in vaultspec's onboarding. Automatic wrangling of the
existing `.credentials.json` works for users who have logged in via `claude auth login`
without any extra steps.

**Why defer token refresh to a follow-up increment:** Token refresh adds network I/O
and error-handling complexity at process spawn time. The v1 fix resolves the primary
failure mode (valid but unexported access token). Refresh handling is the natural next
increment once the core injection path is validated.

See [[2026-02-21-provider-auth-billing-research]] for the billing isolation analysis
that underpins the API-key-override rationale.

## Consequences

**Positive:**
- Eliminates the `RequestError: Verify your account` failure for subscription users
  whose session-scoped `accessToken` is still valid at spawn time.
- Zero additional cost for Max/Pro subscribers: `CLAUDE_CODE_OAUTH_TOKEN` routes
  through subscription billing, not pay-per-token.
- Existing `ANTHROPIC_API_KEY` users are unaffected — the guard is a no-op when the
  key is present.
- Pre-configured `CLAUDE_CODE_OAUTH_TOKEN` in the shell environment (e.g., via
  `claude setup-token`) is also preserved — the guard is a no-op in that case too.
- Clear warning emitted at spawn time when auth credentials are entirely missing,
  enabling fast diagnosis.

**Negative / risks:**
- v1 does not refresh expired tokens. If `accessToken` is already expired when
  `prepare_process()` runs, the child will still fail. Users with expired tokens
  must restart their Claude Code session or manually re-authenticate.
- Injecting an access token from `.credentials.json` creates an implicit dependency
  on the parent session's credential file path. Users running vaultspec in Docker or
  other sandboxed environments without a home directory will hit the missing-auth path.
- Writing back a refreshed token to `.credentials.json` (planned for v2) introduces
  a write-side dependency on the credential file. Concurrent Claude Code sessions
  writing to the same file require care (atomic writes, last-write-wins semantics).
- The `expiresAt` millisecond interpretation is a non-obvious footgun. Incorrect
  comparison (treating ms as seconds) produces an `expiresAt` 1000x too far in the
  future, meaning the refresh branch is never taken even for expired tokens. Code
  review must verify the `/ 1000` division is present.

**Alternatives considered:**

- **API-key-only:** Requires all users to generate an Anthropic API key, adds
  pay-per-token billing, and is hostile to subscription users. Rejected.
- **Credentials-file-only (no token injection):** The current broken state — the
  child binary reads the file but cannot refresh the token non-interactively when
  `CLAUDE_CODE_ENTRYPOINT=sdk-py` is set. Rejected as insufficient.
- **No fallback warning on API key failure:** Silent failures are harder to diagnose.
  A startup-time warning pointing to the likely cause is lower-cost than debugging a
  failed child process. Rejected in favour of the diagnostic warning.
- **Mandatory `claude setup-token` onboarding step:** Cleaner long-term, but adds
  friction for new users and requires documentation changes before any fix lands.
  Deferred, not rejected — `setup-token` remains the recommended long-lived solution.
