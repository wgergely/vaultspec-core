---
tags:
  - "#adr"
  - "#cli-architecture"
date: 2026-03-05
related:
  - "[[2026-03-05-cli-architecture-audit]]"
  - "[[2026-03-05-cli-path-resolution-adr]]"
---

# ADR: CLI Parsing Engine Migration (Typer + Rich)

## Status
Accepted

## Context
During the audit for the --target flag implementation ([[2026-03-05-cli-architecture-audit]]), severe structural limitations were discovered within the current rgparse-based CLI layer:
1. **Inheritance Failure:** Global flags (--root, --content-dir) do not naturally cascade to nested subcommands (e.g., ules list), causing them to disappear from --help menus.
2. **sys.argv Hacking:** __main__.py intercepts and rewrites sys.argv using raw string matching to route commands. If a user types aultspec --target /foo vault audit (a standard CLI pattern), the string matcher hits the --target flag instead of the ault namespace, causing an immediate crash.
3. **Module-level Side Effects:** The rgparse execution sequence currently forces workspace resolution to happen at module-load time, causing uninitialized repositories to crash on import before --help can even be printed.

We initially considered building a complex, interleaved "master tree" using rgparse.ArgumentParser to solve this. However, a dependency audit revealed that the project already relies on modern external libraries (pydantic, uvicorn, httpx). Furthermore, ich is already a hard dependency in pyproject.toml, yet the CLI uses a custom printer.py instead of leveraging it.

## Decision
We will abandon the standard library rgparse for the CLI interface layer and migrate the entire aultspec CLI to **[Typer](https://typer.tiangolo.com/)**.

* **Typer Integration:** Typer (which is built on top of click and integrates natively with pydantic) uses standard Python 3 type hints to construct complex, multi-level command groups. This natively resolves the sys.argv routing crashes, allows --target to be handled as a global context variable effortlessly, and standardizes --help and --version across all levels of the CLI.
* **Rich Integration:** We will integrate Typer's native ich support for terminal formatting, deprecating the custom printer.py duality. Error messages, help menus, and standard output will be styled uniformly using the ich Console.
* **Context Passing:** The globally resolved WorkspaceLayout (from the --target flag) will be passed down to subcommands using 	yper.Context.obj, eliminating the need for cli_common.py to mutate the global _t.ROOT_DIR singleton behind the scenes.

## Consequences

* **Positive:** 
  * Permanently eliminates the fragility of sys.argv string-matching.
  * Significantly reduces boilerplate code in ault_cli.py, spec_cli.py, and __main__.py.
  * Provides a highly professional, beautifully formatted terminal UX out-of-the-box via ich.
  * Naturally supports interleaved global flags (e.g., aultspec --target /dir command).
* **Negative:** 
  * Requires a substantial rewrite of the CLI entrypoints (ault_cli.py, spec_cli.py, hooks_cli, server_cli, 	eam_cli—though the latter three are being removed via gent-removal).
  * Adds 	yper as a new hard dependency to pyproject.toml (which inherently brings in click).