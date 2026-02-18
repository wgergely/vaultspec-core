# Contributing

## Development Warning

> [!CAUTION]
> **Framework Development:** This repository is for the development of the
> framework itself. **DO NOT** run `cli.py config sync` or similar commands
> to "install" the framework into this root directory. The `.vaultspec/`
> folder here is the source of truth, and syncing it to the root (e.g.,
> creating a root `AGENTS.md`) will cause recursive context issues and
> potential data loss during development.
