---
order: 20
---

# Primary Workflow

This project follows the vaultspec pipeline defined in `system/framework.md`.
The pipeline maps user intent to skills and agent personas that produce documented
artifacts.

## Software Engineering Tasks

- **Understand:** Analyze the user's request and the relevant codebase context.
  Use search tools in parallel to understand file structures, existing
  patterns, and conventions before proposing changes.
- **Route:** Determine whether the request warrants the full vaultspec pipeline
  (Research → Specify → Plan → Execute → Verify) or is a trivial fix that can
  be handled directly. When in doubt, check `.vault/` for existing artifacts
  related to the request.
- **Execute:** For pipeline work, invoke the appropriate vaultspec skill as
  defined in the bootstrap. For direct work, implement changes following
  project conventions.
- **Verify:** Run the project's test suite and linting/type-checking commands.
  Prefer non-interactive "run once" modes. If unsure about the correct
  commands, ask the user.
- **Finalize:** After verification passes, await the user's next instruction.
  Do not remove or revert changes or created files (including tests).
