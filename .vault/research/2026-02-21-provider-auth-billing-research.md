---
tags:
  - "#research"
  - "#acp-bridge-auth"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-bridge-auth-research]]"
  - "[[2026-02-21-gemini-bridge-auth-research]]"
---
# `acp-bridge-auth` research: Subscription billing vs. API key costs

Billing research to determine whether API keys can be used with existing monthly
subscriptions (Claude Max, Gemini Advanced) without incurring additional costs, and
what the correct free auth path is for non-interactive subprocess spawning.

## Findings

### Claude

**Subscription (Max $100/mo) and API (api.anthropic.com) are entirely separate billing
systems with zero overlap.**

- `ANTHROPIC_API_KEY` = pay-per-token at api.anthropic.com rates. Setting it silently
  switches Claude Code away from subscription billing with no warning.
- `CLAUDE_CODE_OAUTH_TOKEN` = subscription-billed. Generated via `claude setup-token`.
  Designed for exactly this use case: non-interactive, headless Claude Code invocation
  under subscription billing.
- The short-lived `accessToken` in `~/.claude/.credentials.json` (expires ~1h) is the
  underlying OAuth credential. The `setup-token` flow generates a purpose-built token
  from this session.
- Anthropic banned OAuth tokens in **third-party apps** (early 2026, ToS). Spawning
  the official `claude` CLI binary (as vaultspec does) is not affected by this ban.
- No supported machine-to-machine auth path for subscription billing yet (issue #1454,
  unresolved). `CLAUDE_CODE_OAUTH_TOKEN` is the closest approximation.

**Auth priority (Claude Code):** `ANTHROPIC_API_KEY` > `CLAUDE_CODE_OAUTH_TOKEN` > `~/.claude/.credentials.json`

**Credential file:** `~/.claude/.credentials.json`
- `claudeAiOauth.accessToken` — short-lived (~1h), `sk-ant-oat01-...` prefix
- `claudeAiOauth.refreshToken` — long-lived, used to obtain new access tokens
- `claudeAiOauth.expiresAt` — Unix ms timestamp

### Gemini

**Google One AI Premium / Gemini Advanced provides zero benefit toward Gemini API or
CLI usage.** The two products share no billing.

- `GEMINI_API_KEY` from AI Studio = separate developer billing. Has a free tier:
  Gemini 2.5 Flash-Lite 1,000 RPD free, no credit card required. Still separate from
  the Gemini Advanced subscription.
- `gemini auth login` (Google OAuth) = **"Code Assist for Individuals"** — a free
  Google developer entitlement (1,000 req/day, 60 RPM). Not subscription-billed, not
  API-billed. Free.
- Credentials cached at `~/.gemini/oauth_creds.json` after `gemini auth login`.
- The subprocess reads this file directly (no suppression mechanism, unlike Claude's
  `CLAUDE_CODE_ENTRYPOINT=sdk-py`). Works until tokens expire.
- `GEMINI_API_KEY` is the clean headless path but adds separate billing (even if the
  free tier covers low volume). OAuth credentials file is the zero-cost path.

**Auth priority (Gemini CLI):**
`GOOGLE_GENAI_USE_GCA=true` > `GOOGLE_GENAI_USE_VERTEXAI=true` > `GEMINI_API_KEY` > `~/.gemini/oauth_creds.json`

**Credential file:** `~/.gemini/oauth_creds.json`
- Contains Google OAuth access + refresh tokens
- Written by `gemini auth login`

### Decision drivers

| Factor | Claude | Gemini |
|---|---|---|
| Preferred zero-cost auth | `CLAUDE_CODE_OAUTH_TOKEN` / `.credentials.json` | `~/.gemini/oauth_creds.json` (OAuth login) |
| API key adds cost? | **Yes** — always separate billing | Technically yes, but free tier exists |
| API key override useful? | Yes — for users with API access | Yes — for users with AI Studio key |
| Token expiry risk | High (~1h access token) | Moderate (Google OAuth tokens, longer-lived) |
| Refresh possible? | Yes — `refreshToken` present in credentials file | Yes — Google OAuth refresh flow |
| Right default | OAuth wrangling + refresh | OAuth wrangling + refresh |
| Override if key present | Yes — respect `ANTHROPIC_API_KEY` | Yes — respect `GEMINI_API_KEY` |
| Fallback if key fails | Yes — fall back to OAuth | Yes — fall back to OAuth |
