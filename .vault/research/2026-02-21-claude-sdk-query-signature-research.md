---
tags:
  - '#research'
  - '#acp-claude-multimodal'
date: '2026-02-21'
related:
  - '[[2026-02-21-acp-claude-multimodal-plan]]'
---

# Claude SDK Query Signature Findings

## 1. Signature Inspection

Command: `python -c "import claude_agent_sdk; import inspect; print(inspect.signature(claude_agent_sdk.ClaudeSDKClient.query))"`

Output: `(self, prompt: str | collections.abc.AsyncIterable[dict[str, typing.Any]], session_id: str = 'default') -> None`

## 2. Analysis

The `query` method accepts:

1. `str`: A simple text prompt.
1. `AsyncIterable[dict[str, Any]]`: A stream of raw message dicts.

It does **not** explicitly list `list[dict]` or `UserMessage` in the type hint, but typically `AsyncIterable` covers lists (if synchronous iterables are accepted or if it handles conversion). However, the type hint specifically says `AsyncIterable`.

If we need to send a single complex message (text + image), we might need to wrap it in an async generator or check if the SDK handles standard iterables.

Wait, looking at the reference `acp-claude-code`, they use `query({ prompt: toAsyncIterable([userMessage]) ... })`.

The Python SDK `query` signature suggests it wants a **stream of messages**.

If we pass a `str`, the SDK likely wraps it in a UserMessage internally.
If we want to pass images, we likely need to construct a `dict` representing the message (with `role="user"` and `content=[...]`) and yield it from an async iterable.

## 3. Plan Adjustment

We cannot just pass a list of blocks. We must pass an **async iterable of message dicts**.

We need a helper:

```python
async def _make_message_stream(message_dict):
    yield message_dict
```

And then call:

```python
await sdk_client.query(_make_message_stream(user_message))
```
