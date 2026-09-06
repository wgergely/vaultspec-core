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
[hook behavior and project policy](framework.md#decisions-you-make-once). Installing
`.pre-commit-config.yaml` alone does not activate the hooks.

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

Links between vault documents are Obsidian-style wiki-links, quoted, and they belong in
`related:` only:

```yaml
related:
  - '[[2026-02-06-payment-retries-research]]'
  - '[[2026-02-06-payment-retries-adr]]'
```

The first ones are usually set when the document is scaffolded: every
`vaultspec-core vault add` takes `--related`, which is how an ADR arrives already
pointing at its research. Afterwards, change them with `vaultspec-core vault link add`
and `vault link remove` rather than by hand. Three rules govern the result:

- Quote them. Unquoted, YAML reads `[[...]]` as a nested sequence.
- Use no relative paths. The namespace is flat, so `[[document-stem]]` resolves wherever
  the document lives. A `../` prefix breaks on the first reorganisation.
- Link only documents that exist. The `dangling` check finds the ones that do not.

In body prose, use neither wiki-links nor Markdown path links. Cite code by locator
instead, in backticks: `src/billing/retry.py:42`, commit `abc1234`, or
`vaultspec-core@0.1.59`. The `body-links` check enforces this.

Vault documents cite code; code never cites the vault. Keeping links out of body prose
keeps the graph in one place, where the checks can see it.

## Values you must never write by hand

A hand-written value can disagree with the content it describes. A computed one cannot.

`modified` is a last-modified stamp, refreshed by every command that writes the
document.

`body_hash` is a fingerprint of the body that `modified` attests. It appears in no
template, because it cannot exist before the body it hashes. It is what makes an edit
that skipped the tooling detectable: the `modified-stamp` check compares the live body
against this value and never consults file timestamps.

`body_schema` records which body structure the document follows, so the `body-sections`
check knows which sections to require. New documents are written as `body-v2`.

A ledger carries no `step_id`; each row's first cell holds the canonical identifier,
`S01`, not the display path `P01.S01`.

Edit a body outside the tooling without restamping, and the check says so:

```
! .vault/exec/2026-02-04-editor-demo/2026-02-04-editor-demo-S01.md
  Stale modified stamp '2026-02-04'; the document body no longer matches its
  attested fingerprint (unstamped edit).
  fix: refresh to '2026-02-06' and re-attest the body
```

## Template placeholders

Templates carry two kinds of placeholder, and they are not interchangeable.

Author-replaced placeholders use curly braces and lowercase kebab-case: `{feature}`,
`{topic}`, `{title}`. Fill them in as you write.

Machine-filled placeholders use snake_case and are substituted by the command that
scaffolds the document:

| Placeholder       | Filled by                            |
| ----------------- | ------------------------------------ |
| `{plan_stem}`     | `vaultspec-core vault exec log`      |
| `{document_list}` | `vaultspec-core vault feature index` |

If one of these survives into a committed document, the document was created by hand
rather than by the command that owns it. The `placeholders` check finds them, and the
author-replaced ones above, because it matches the tokens the templates ship rather than
every pair of braces: `{topic}` left in a body is an error and exits `1`, while a
`{not_a_template_token}` of your own is reported clean. That is the check doing its job
\- it looks for scaffolding you forgot to fill - but it is not a general brace scan,
which is worth knowing before relying on it to find something else.

## Filenames

`vaultspec-core vault add` decides the filename. You will read these patterns in
directory listings, so they are here for reference:

| Document           | Pattern                                  |
| ------------------ | ---------------------------------------- |
| Top-level          | `yyyy-mm-dd-{feature}-{type}.md`         |
| With a topic infix | `yyyy-mm-dd-{feature}-{topic}-{type}.md` |
| Ledger             | `yyyy-mm-dd-{feature}-ledger.md`         |
| Feature index      | `{feature}.index.md`                     |

Narrative segments are lowercase kebab-case. Container identifiers keep their canonical
uppercase form: `W01`, `P02`, `S03`.

Every type but one sits directly in its directory. A ledger sits a level down, in a
folder named for the feature:
`.vault/exec/2026-02-04-editor-demo/2026-02-04-editor-demo-ledger.md`.

To give a feature a second decision record or a second piece of research, pass `--topic`
to `vaultspec-core vault add` rather than inventing a filename. Only `adr`, `audit`,
`reference`, and `research` accept it.

To rename an existing document, use `vaultspec-core vault rename`, which re-points the
`related:` entries that pointed at the old name.

## Plan structure

The tooling parses a plan's rows; for every other document it only checks them. Ledger
rows point at the identifiers in those rows, so a change to the grammar breaks records
already written.

### Tiers

The tier declared in frontmatter decides which containers exist:

| Tier | Structure                                                                |
| ---- | ------------------------------------------------------------------------ |
| `L1` | Steps only                                                               |
| `L2` | Phases above Steps                                                       |
| `L3` | Waves above Phases above Steps                                           |
| `L4` | An Epic frame above Waves, and a declared project-management association |

Choose by the complexity of the work, not by counting containers. A plan does not earn
`L3` by having enough rows to fill three Waves; it earns `L3` when the work has three
stages that must land in order.

Change tier later with `vaultspec-core vault plan tier promote` or `tier demote`.
Promotion adds containers and renumbers nothing. Demotion refuses to collapse a
container that has several children unless you say so explicitly.

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

`[ ]` is open and `[x]` is closed. Nothing records "in progress". If a row turns out to
be half done, split it with `vaultspec-core vault plan step add` and close the part that
landed.

Write plain ASCII hyphens. The `PLAN060` rule rejects em-dashes and en-dashes anywhere
in a plan: body, headings, frontmatter, and comment hints. `vault plan check --fix`
replaces them with an ASCII spaced hyphen.

Wiki-links and Markdown links are forbidden in a plan body, as they are in any body. The
documents that authorise the work go in the plan's `related:` frontmatter once, and
every Step inherits that chain. Per-row reference footers do not exist.

### Display paths

The identifier written in a row depends on the tier:

| Tier       | Step path     | Phase heading | Wave heading |
| ---------- | ------------- | ------------- | ------------ |
| `L1`       | `S07`         | none          | none         |
| `L2`       | `P02.S07`     | `P02`         | none         |
| `L3`, `L4` | `W01.P02.S07` | `W01.P02`     | `W01`        |

Display paths are computed from the current grouping. Move a Phase to another Wave and
every Step under it displays a new path, while its canonical identifier stays what it
always was.

### Identifiers

`S##`, `P##`, and `W##` are immutable and append-only. They are numbered per document,
and a Step's number is independent of the Phase holding it, so `S07` is `S07` wherever
it sits.

Gaps are never reused. Remove Step 7 and the next Step added is 8, not 7. The number is
retired with the row, which is what keeps the record durable: a ledger row written
months ago names `S07`, and no later edit can hand `S07` to different work.

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

N self-similar actions means N rows. Never collapse them into "for each handler, add the
header" or "across all callers, rename the flag". No check enforces this; it is a
convention, and the reason is verification. A collapsed row cannot be half closed, so
its ledger rows cannot say which callers were touched, and nothing catches the one that
was missed.

## Where to go next

The [framework manual](./framework.md) covers the workflow these documents record.
[Verifying a workspace and a vault](./verification.md) covers the checks named on this
page and what each one proves.
