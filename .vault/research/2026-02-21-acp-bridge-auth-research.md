---
tags:
  - "#research"
  - "#acp-bridge-auth"
date: "2026-02-21"
related:
  - "[[2026-02-20-team-mcp-integration-research]]"
  - "[[2026-02-07-acp-research]]"
---
# `acp-bridge-auth` research: Claude SDK child-process authentication failure

Investigation into `acp.exceptions.RequestError: Verify your account to continue` raised
when the Python ACP bridge spawns a child `claude` process via `claude-agent-sdk`. The
parent Claude Code session is fully authenticated via OAuth (Max subscription); the child
fails because the short-lived OAuth access token expires and cannot be refreshed
non-interactively.

## Findings

### Architecture (subprocess chain)

Two-level spawn:

1. **Parent (Claude Code)** → `spawn_agent_process()` → **Bridge process**
   (`python -m vaultspec.protocol.acp.claude_bridge`)
2. **Bridge process** → `ClaudeSDKClient.connect()` → **`claude.exe`** (innermost subprocess)

The bridge is an ACP Agent server (JSON-RPC over stdin/stdout). It wraps `ClaudeSDKClient`
which spawns the actual `claude` binary.

### SDK bundled vs. system CLI

The SDK (v0.1.36) bundles its own `claude.exe` at
`.venv/Lib/site-packages/claude_agent_sdk/_bundled/claude.exe` (v2.1.49). `_find_cli()`
checks the bundled binary **first**, then `shutil.which("claude")`.

The bridge overrides this correctly:

```python
# claude_bridge.py:252
self._cli_path: str | None = shutil.which("claude")
```

If `shutil.which("claude")` returns `None`, the SDK silently falls back to its bundled
binary.

### SDK environment chain

`SubprocessCLITransport.connect()` builds the child env as:

```python
process_env = {
    **os.environ,           # bridge subprocess env
    **self._options.env,    # ClaudeAgentOptions.env (empty dict by default)
    "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
    "CLAUDE_AGENT_SDK_VERSION": __version__,
}
```

`ClaudeProvider.prepare_process()` does `env = os.environ.copy()` and removes `CLAUDECODE`.
The ACP transport's `DEFAULT_INHERITED_ENV_VARS` stripping is overridden by the full env
dict passed to `spawn_agent_process()`, so the bridge process receives the complete parent
environment.

### Authentication lookup order (child `claude` binary)

1. `CLAUDE_CODE_OAUTH_TOKEN` env var
2. `ANTHROPIC_API_KEY` env var
3. `~/.claude/.credentials.json` (OAuth tokens from interactive login)

The parent session sets **none** of these in its env — it relies on `.credentials.json`.
The child inherits the same env, reads `.credentials.json`, and fails when the
`accessToken` is expired because it cannot perform the browser-based OAuth refresh flow.

### Root cause

`~/.claude/.credentials.json` contains:

- `accessToken`: present (`sk-ant-oat01-...` prefix)
- `expiresAt`: `1771679340667` ms = **2026-02-21T13:09:00 UTC** (short-lived, ~1h window)
- `refreshToken`: present
- `subscriptionType`: `max`

The child `claude` process reads the file, finds the token, but:
- If the token is expired, the CLI cannot refresh it without a browser
- `CLAUDE_CODE_ENTRYPOINT=sdk-py` suppresses the interactive auth flow
- The CLI surfaces the error as `"Verify your account to continue"` via stream-json output
- The SDK converts it to `RequestError`

### Fix implemented

`ClaudeProvider.prepare_process()` now reads `accessToken` from `.credentials.json` and
injects it as `CLAUDE_CODE_OAUTH_TOKEN` before spawning the bridge:

```python
# providers/claude.py
if "CLAUDE_CODE_OAUTH_TOKEN" not in env and "ANTHROPIC_API_KEY" not in env:
    token = _load_claude_oauth_token()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
```

This propagates the same valid token the parent session is using into the child's env,
bypassing the credentials-file-based auth path entirely. Token refresh on expiry is a
known limitation — see open work below.

### Limitations of current fix

- `accessToken` is short-lived (~1h). If the token has already expired by the time
  `prepare_process()` runs, the child will still fail.
- A more robust fix requires proactive token refresh using the `refreshToken` field,
  hitting Anthropic's OAuth token endpoint before injecting the access token.
- `ANTHROPIC_API_KEY` (long-lived) is the most reliable alternative, but the user
  authenticates via Max subscription OAuth, not API key.

### A2A frontier patterns (for reference)

The A2A protocol (Google / agent interop standard) uses **OAuth 2.0 Token Exchange**
(RFC 8693) for parent→child auth delegation: the parent exchanges its token for a
downscoped child token via the authorization server. Claude Code has no equivalent
mechanism for subprocess auth delegation — auth is entirely credential-file or env-var
based.

### Open work

- Token refresh logic: on `expiresAt` approaching, read `refreshToken` and call
  Anthropic's token refresh endpoint to get a fresh `accessToken` before injecting it.
- Consider `claude setup-token` as a one-time setup that produces a long-lived
  `CLAUDE_CODE_OAUTH_TOKEN` stored in `.env` or a secrets manager, decoupling subagent
  auth from session-scoped access tokens entirely.
