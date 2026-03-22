---
tags:
  - '#exec'
  - '#acp-bridge-auth'
date: '2026-02-21'
related:
  - '[[2026-02-21-claude-provider-auth-strategy-adr]]'
  - '[[2026-02-21-gemini-provider-auth-strategy-adr]]'
---

# `acp-bridge-auth` Code Quality Audit | **verdict: PASS**

## Files Reviewed

- `src/vaultspec/protocol/providers/claude.py`
- `src/vaultspec/protocol/providers/gemini.py`
- `src/vaultspec/protocol/tests/test_provider_auth.py`

## Critical Checks

| #   | Check                                     | Verdict | Evidence                                                                                                                                                                                                                                                |
| --- | ----------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `expiresAt` uses `/1000` (ms to sec)      | PASS    | `claude.py:62` — `expires_at_sec = expires_at_ms / 1000`                                                                                                                                                                                                |
| 2   | No mocks, patches, stubs, or skips        | PASS    | Zero matches for `unittest.mock`, `MagicMock`, `patch`, `mocker`, `monkeypatch`, `stub`, `pytest.mark.skip`, `skipIf`                                                                                                                                   |
| 3   | Dependency injection on auth helpers      | PASS    | `_load_claude_oauth_token(creds_path, token_url)` at line 33; `_load_gemini_oauth_creds(creds_path)` at line 52; `_refresh_gemini_oauth_token(creds, token_url, creds_path)` at line 63; `GeminiProvider.prepare_process(creds_path)` at line 238       |
| 4   | Atomic write (same-dir temp + os.replace) | PASS    | Claude: `tempfile.NamedTemporaryFile(dir=creds_dir)` + `os.replace()` at lines 131-141. Gemini: `target.parent / f".oauth_creds_tmp_..."` + `os.replace()` at lines 118-121                                                                             |
| 5   | `pathlib` is runtime import in gemini.py  | PASS    | `import pathlib` at `gemini.py:7`, module level (not inside `TYPE_CHECKING`)                                                                                                                                                                            |
| 6   | No new third-party dependencies           | PASS    | `pyproject.toml` diff shows only build system migration (setuptools to hatchling) and path restructuring; zero new runtime deps                                                                                                                         |
| 7   | `logger.debug` for API key paths          | PASS    | `claude.py:226` logs `ANTHROPIC_API_KEY present`; `gemini.py:270` logs `GEMINI_API_KEY present`                                                                                                                                                         |
| 8   | `logger.warning` (not raise) on failures  | PASS    | Claude: warnings at lines 72, 96, 103, 111, 143, 232. Gemini: warnings at lines 79, 97, 104, 123, 276, 284. No exceptions raised on auth failure                                                                                                        |
| 9   | All 10 test scenarios present             | PASS    | Claude 5: valid token (line 97), expired+refresh OK (112), expired+refresh 400 (134), missing file (155), API key skip (163). Gemini 5: valid token (226), expired+refresh OK (241), expired+refresh 500 (268), missing creds (287), API key skip (325) |
| 10  | Test servers are real (no mock HTTP)      | PASS    | `http.server.HTTPServer(("127.0.0.1", 0), _Handler)` at `test_provider_auth.py:59`; all network tests hit this real localhost server                                                                                                                    |

## Additional Observations

- Gemini atomic write includes cleanup of the temp file on failure (`tmp.unlink(missing_ok=True)` at `gemini.py:125`), which is a nice defensive touch.
- Claude's refresh path correctly handles three response shapes: `expires_at` (absolute seconds), `expires_in` (relative seconds), and a 1-hour fallback (`claude.py:117-124`).
- The Gemini `_is_gemini_token_expired()` helper handles both `Z`-suffix and `+00:00` ISO formats with a fallback `strptime` path (`gemini.py:133-149`).
- Tests for `prepare_process()` integration (scenarios 5 for each provider) correctly manage environment variable backup/restore in `finally` blocks.

## Verdict

**PASS** — All 10 critical checks satisfied. No issues found.
