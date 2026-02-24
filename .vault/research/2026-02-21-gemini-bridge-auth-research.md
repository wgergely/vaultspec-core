---
tags:
  - "#research"
  - "#acp-bridge-auth"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-bridge-auth-research]]"
  - "[[2026-02-20-a2a-team-gemini-research]]"
---
# `acp-bridge-auth` research: Gemini CLI child-process authentication

Parallel investigation to `"[[2026-02-21-acp-bridge-auth-research]]"` (Claude). Maps Gemini
CLI auth flows to identify gaps in `GeminiProvider.prepare_process()` and determine the
correct fix strategy.

## Findings

### Architecture (fundamental difference from Claude)

`GeminiProvider` spawns the **`gemini` binary directly** as the ACP server — there is no
Python bridge layer. The binary speaks the ACP stdio protocol natively via `--experimental-acp`:

```python
# gemini.py
executable, prefix_args = resolve_executable("gemini", _which_fn)
args = ["--experimental-acp", "--model", model]
return ProcessSpec(executable=executable, args=prefix_args + args, env=env, ...)
```

On Windows: `cmd.exe /c <gemini.cmd> --experimental-acp --model <model>`. There is no
`gemini_bridge.py`. No Python SDK for Gemini is present in `pyproject.toml` or `uv.lock` —
only `claude-agent-sdk` is a direct dependency.

### Gemini CLI auth priority (env-driven)

`getAuthTypeFromEnv()` in the Gemini CLI resolves auth type in strict order:

| Priority | Env var | Auth type | Non-interactive? |
|---|---|---|---|
| 1 | `GOOGLE_GENAI_USE_GCA=true` | OAuth (browser, cached) | Only if `~/.gemini/oauth_creds.json` fresh |
| 2 | `GOOGLE_GENAI_USE_VERTEXAI=true` | Vertex AI | Yes (with ADC) |
| 3 | `GEMINI_API_KEY` set | Direct API key | **Yes — fully** |
| 4 | None | OAuth browser flow | **No — hangs without TTY** |

There is **no analog to `CLAUDE_CODE_ENTRYPOINT=sdk-py`** — Gemini has no subprocess-mode
signal that changes auth behavior. Resolution is purely env-var and file-based.

### Credential file

```
~/.gemini/oauth_creds.json
```

Written by `gemini auth login` (Google OAuth browser flow). Path constant: `GEMINI_DIR = '.gemini'`
relative to `homedir()`. On Windows: `%USERPROFILE%\.gemini\oauth_creds.json`.

This file contains Google OAuth access + refresh tokens. The subprocess inherits filesystem
access and can read the file directly — **unlike Claude**, where `CLAUDE_CODE_ENTRYPOINT=sdk-py`
suppresses credential-file reading and demands explicit env-var injection.

### What `GEMINI_API_KEY` is

- **Source**: Google AI Studio (`aistudio.google.com`), not Vertex AI
- **Scope**: Project-scoped, long-lived (no expiry by default, unlike OAuth access tokens)
- **Behavior**: `createContentGeneratorConfig()` reads `process.env['GEMINI_API_KEY']`
  directly — no prompts, no file I/O, fully non-interactive

This is the recommended token for subprocess/non-interactive use. Directly analogous to
`ANTHROPIC_API_KEY` for Claude.

### What `approval_mode` is

Gemini-CLI-specific flag `--approval-mode` with values `default | auto_edit | yolo | plan`.
Controls tool/file modification approval policy. `yolo` = equivalent of Claude's
`bypassPermissions`. Exposed in agent YAML as `approval_mode`. Correctly flagged as
`_GEMINI_ONLY_FEATURES` in `claude.py`.

### Current `GeminiProvider` auth gap

```python
# gemini.py — current auth block
env = os.environ.copy()
# ... sets only GEMINI_SYSTEM_MD
# NO auth injection
```

Compare to `ClaudeProvider`:

```python
# claude.py — after fix
if "CLAUDE_CODE_OAUTH_TOKEN" not in env and "ANTHROPIC_API_KEY" not in env:
    token = _load_claude_oauth_token()   # reads ~/.claude/.credentials.json
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    else:
        logger.warning("No Claude OAuth token found ...")
```

`GeminiProvider` has no equivalent. If `GEMINI_API_KEY` is set in the parent env it
propagates automatically via `os.environ.copy()` — no explicit injection needed. But if the
user authenticated only via `gemini auth login` (Google OAuth), and `oauth_creds.json`
expires, the subprocess fails silently or hangs on device-code input.

### Subprocess headless behavior

`isHeadlessMode()` in Gemini CLI detects absence of TTY. In headless mode:

- `GEMINI_API_KEY` in env → authenticates immediately ✓
- `~/.gemini/oauth_creds.json` valid on disk → reads from file ✓
- Neither → falls into OAuth flow → **hangs or throws `FatalAuthenticationError`** ✗

### Why Gemini is less broken than Claude (currently)

Claude's issue: `CLAUDE_CODE_ENTRYPOINT=sdk-py` actively suppresses the credential-file
auth path, requiring explicit `CLAUDE_CODE_OAUTH_TOKEN`. The file IS there but Claude refuses
to read it.

Gemini's issue: The binary DOES read `~/.gemini/oauth_creds.json` when no API key is set.
No suppression mechanism. The child process can authenticate via cached OAuth tokens without
any intervention — until those tokens expire.

### Fix strategy for `GeminiProvider`

**No injection fix is needed for typical cases.** `GEMINI_API_KEY` propagates naturally.
`oauth_creds.json` is read by the binary itself.

What IS missing (parity with `ClaudeProvider` post-fix):

1. **Defensive warning** — if neither `GEMINI_API_KEY` is in env nor `~/.gemini/oauth_creds.json`
   exists, log a warning so auth failures are diagnosable.
2. **No token injection possible** — unlike Claude (where `CLAUDE_CODE_OAUTH_TOKEN` accepts
   the raw access token), there is no Gemini env var to inject a raw OAuth token. The
   binary reads the JSON file directly. Token refresh, if needed, must go through
   `~/.gemini/oauth_creds.json` on disk.

### Recommended setup for non-interactive subagent use

Set `GEMINI_API_KEY` from Google AI Studio. Long-lived, no expiry, no refresh needed.
Avoids all OAuth expiry complexity. Store in `.env` or system environment.
