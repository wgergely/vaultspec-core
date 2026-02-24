# Test Project

This directory serves as the reproducible test workspace for the vaultspec
framework. The `.vault/` subdirectory is tracked in git as the seed corpus for
RAG and integration tests. All other contents (`*.lance/`, `.vaultspec/`,
`.claude/`, `.gemini/`) are gitignored.

You can use this to test the CLI synchronization and tool configuration by
pointing to this directory as the workspace root:

```powershell
python .vaultspec/lib/scripts/cli.py config sync --root ./test-project --force
```
