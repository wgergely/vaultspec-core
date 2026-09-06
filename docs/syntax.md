# Document syntax

Create documents with `vaultspec-core vault add`; record execution with
`vaultspec-core vault exec log`, which creates the plan's ledger when needed.

## Who owns what

Frontmatter, field by field:

| Field         | Who changes it | How                                                                |
| ------------- | -------------- | ------------------------------------------------------------------ |
| `tags`        | The tool       | Set from `--feature` at scaffold. Do not add more.                 |
| `date`        | The tool       | Set at scaffold; the filename embeds the same date.                |
| `modified`    | The tool       | Refreshed by every command that writes the document.               |
| `body_schema` | The tool       | Records which body structure the document follows.                 |
| `body_hash`   | The tool       | A fingerprint of the body that `modified` attests.                 |
| `related`     | You            | `--related` when scaffolding, then `vault link add` and `remove`.  |
| `tier`        | You            | Through `vaultspec-core vault plan tier promote` or `tier demote`. |
| `generated`   | The tool       | Marks a file that is rebuilt rather than authored.                 |

Bodies, by document type:

| Body                             | Who changes it | How                                                          |
| -------------------------------- | -------------- | ------------------------------------------------------------ |
| Prose in any scaffolded document | You            | `vaultspec-core vault set-body`, or an editor plus a restamp |
| Rows in a plan                   | You            | `vaultspec-core vault plan` verbs only                       |
| Rows in a ledger                 | The tool       | `vaultspec-core vault exec log`                              |
| A feature index, whole file      | The tool       | `vaultspec-core vault feature index`                         |

Plan rows are the exception worth remembering: they look like ordinary body prose, and
they are not, because ledger rows point at the identifiers in them.

## Editing safely

Use `set-body` to replace prose and update `modified` and `body_hash`. By default, it
validates the result before writing and rejects changes with validation errors:

```bash
vaultspec-core vault set-body <document> --body-file new-body.md
vaultspec-core vault edit <document>              # body and frontmatter in one write
vaultspec-core vault rename <document> --to <new-stem>   # also re-points incoming links
```

If you edit in your own editor instead, the document's `body_hash` no longer matches its
body, and nothing has restamped `modified`. Run this afterwards:

```bash
vaultspec-core vault check all --fix
```

Review the changed files, then
[rerun validation](verification.md#check-records-before-committing).

Before enabling commit-time checks with `pre-commit install`, review
[hook behavior and project policy](framework.md#configure-project-integrations).
Installing `.pre-commit-config.yaml` alone does not activate the hooks.

## Frontmatter

Newly generated documents carry these six fields:

```yaml
---
tags:
  - '#plan'
  - '#payment-retries'
date: '2026-02-06'
modified: '2026-02-06'
body_schema: 'body-v2'
body_hash: 'sha256:...'
related:
  - '[[2026-02-06-payment-retries-adr]]'
---
```

Plans add `tier`; generated indexes add `generated`:

| Type  | Extra field | Holds                                              |
| ----- | ----------- | -------------------------------------------------- |
| plan  | `tier`      | The complexity tier: `L1`, `L2`, `L3`, or `L4`     |
| index | `generated` | Always `true`; the file is rebuilt, never authored |

Execution ledgers link to their parent plan in `related`; each row carries its Step
identifier. See [execution logging](CLI.md#vaultspec-core-vault-exec-log).

Add no fields beyond these. Metadata lives in frontmatter and nowhere else, so an
invented field has no reader and fails the `frontmatter` check.

## The tag pair

Exactly two tags. One names the directory, one names the feature.

| Directory           | Tag          |
| ------------------- | ------------ |
| `.vault/adr/`       | `#adr`       |
| `.vault/audit/`     | `#audit`     |
| `.vault/exec/`      | `#exec`      |
| `.vault/index/`     | `#index`     |
| `.vault/plan/`      | `#plan`      |
| `.vault/reference/` | `#reference` |
| `.vault/research/`  | `#research`  |

The feature tag is kebab-case and identical across every document in the feature's
lifecycle. It is what makes a trail findable: research, decision, plan, and audit all
carry `#payment-retries`, so one filter returns the whole story.

Use only the directory tag and the feature tag; `vault add --tags` rejects additional
tags.

## Linking

Put links between vault documents in `related:` as quoted Obsidian-style wiki-links:

```yaml
related:
  - '[[2026-02-06-payment-retries-research]]'
  - '[[2026-02-06-payment-retries-adr]]'
```

When creating a document, set links with `vaultspec-core vault add --related`.
Afterwards, use [link add](CLI.md#vaultspec-core-vault-link-add) or
[link remove](CLI.md#vaultspec-core-vault-link-remove).

- Quote wiki-links so YAML reads them as strings, not nested sequences.
- Store document stems without directories or `.md`: `[[document-stem]]`.
- Link only to existing documents. The `dangling` check reports unresolved links.

The `body-links` check rejects wiki-links and Markdown path links in body prose. Cite
code by locator instead, in backticks: `src/billing/retry.py:42`, commit `abc1234`, or
`vaultspec-core@0.1.59`.

Keep references one-way: vault documents cite code; source code must not cite vault
documents.

<p id="values-you-must-never-write-by-hand"></p>

## Generated metadata

The `modified-stamp` check compares the body against its stored `body_hash`, not
filesystem timestamps. Without a stored hash, it can't detect an unstamped body edit.

The `body-sections` check uses `body_schema` to check the document's sections. Newly
scaffolded documents use `body-v2`. See
[validation and repair](verification.md#check-records-before-committing).

## Template placeholders

Creation commands fill `{feature}` from `--feature` and `{title}` or `{topic}` from
`--title`. Complete remaining prose placeholders before committing.

| Placeholder       | Filled by                            |
| ----------------- | ------------------------------------ |
| `{plan_stem}`     | `vaultspec-core vault exec log`      |
| `{document_list}` | `vaultspec-core vault feature index` |

The `placeholders` check reports recognized tokens, date forms, and enum forms left in
body prose as errors. It skips comments, fenced code, and inline code except in
headings. It doesn't check every brace expression or fill missing content. See the
[check reference](CLI.md#vaultspec-core-vault-check) for commands and options.

## Filenames

Core generates filenames in these forms:

| Document           | Pattern                                  |
| ------------------ | ---------------------------------------- |
| Top-level          | `yyyy-mm-dd-{feature}-{type}.md`         |
| With a topic infix | `yyyy-mm-dd-{feature}-{topic}-{type}.md` |
| Ledger             | `yyyy-mm-dd-{feature}-ledger.md`         |
| Feature index      | `{feature}.index.md`                     |

Narrative segments are lowercase kebab-case. Ledgers use their parent plan's date and
feature in both the folder and filename:
`.vault/exec/2026-02-04-editor-demo/2026-02-04-editor-demo-ledger.md`.

For `adr`, `audit`, `reference`, and `research`, use
[vault add --topic](CLI.md#vaultspec-core-vault-add) to distinguish multiple records for
a feature.

## Plan structure

Edit plan rows with the [plan commands](CLI.md#vaultspec-core-vault-plan). Execution
ledgers reference the plan's Step identifiers.

### Tiers

The tier declared in frontmatter decides which containers exist:

| Tier | Structure                                                                |
| ---- | ------------------------------------------------------------------------ |
| `L1` | Steps only                                                               |
| `L2` | Phases above Steps                                                       |
| `L3` | Waves above Phases above Steps                                           |
| `L4` | An Epic frame above Waves, and a declared project-management association |

Change tiers with `vaultspec-core vault plan tier promote` or `tier demote`. Promotion
preserves canonical identifiers. See the
[plan command reference](CLI.md#vaultspec-core-vault-plan) for demotion and collapse
options.

### Row format

One row per unit of work:

```
- [ ] `W01.P02.S07` - Rewrite the retry backoff to read its ceiling from config; `src/billing/retry.py`.
```

Reading that row left to right:

| Part                       | Example                         |
| -------------------------- | ------------------------------- |
| Checkbox, two states only  | `- [ ]`                         |
| Display path, in backticks | `` `W01.P02.S07` ``             |
| Spaced ASCII hyphen        | `-`                             |
| Imperative-verb action     | `Rewrite the retry backoff ...` |
| Semicolon                  | `;`                             |
| File scope, in backticks   | `` `src/billing/retry.py` ``    |
| Trailing period            | `.`                             |

`[ ]` is open and `[x]` is closed. The format has no in-progress marker.

Write plain ASCII hyphens. The `PLAN060` rule rejects em-dashes and en-dashes anywhere
in a plan: body, headings, frontmatter, and comment hints. `vault plan check --fix`
replaces them with an ASCII spaced hyphen.

Put the records authorizing the work in the plan's `related:` frontmatter. Follow the
[linking rules](#linking).

### Display paths

The identifier written in a row depends on the tier:

| Tier       | Step path     | Phase heading | Wave heading |
| ---------- | ------------- | ------------- | ------------ |
| `L1`       | `S07`         | none          | none         |
| `L2`       | `P02.S07`     | `P02`         | none         |
| `L3`, `L4` | `W01.P02.S07` | `W01.P02`     | `W01`        |

Display paths reflect the current grouping. Moving a Phase to another Wave changes its
Steps' display paths without changing their canonical identifiers.

### Identifiers

Canonical identifiers (`S##`, `P##`, `W##`) are numbered per plan and stay stable across
moves and tier changes. A Step's number is independent of its Phase.

Removed identifiers aren't reused. The next Step number exceeds the highest live or
retired Step number.

Route every identifier-affecting change through the commands:

```
vaultspec-core vault plan step add <plan> --phase P02 --action "..." --scope "src/x.py"
vaultspec-core vault plan step check <plan> S07
vaultspec-core vault plan step remove <plan> S07
```

Run `vaultspec-core vault plan check <plan>` to check plan conventions;
`vault check all` does not include them. See
[plan commands](CLI.md#vaultspec-core-vault-plan) for options.

Duplicated canonical identifiers make ledger references ambiguous. Review the execution
records before repairing a conflict; validation cannot determine which Step an existing
record meant.

### One action, one row

Write a separate Step for each independently verifiable action so each has its own
completion state. Apply this convention during plan review; no check enforces it.

## Where to go next

The [framework manual](./framework.md) covers the workflow these documents record.
[Verifying a workspace and a vault](./verification.md) covers the checks named on this
page and what each one proves.
