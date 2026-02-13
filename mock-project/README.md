# Mock Project

This is a temporary folder used for testing the framework.
It is explicitly ignored by `.gitignore` in the repository root.

You can use this to test the CLI synchronization and tool configuration by pointing to this directory as the workspace root:

```powershell
python .vaultspec/scripts/cli.py config sync --root ./mock-project --force
```
