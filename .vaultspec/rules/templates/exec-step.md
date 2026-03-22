---
# REQUIRED TAGS (minimum 2): one directory tag + one feature tag
# DIRECTORY TAGS: #adr #audit #exec #plan #reference #research
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/exec/ location)
# Feature tag (replace {feature} with your feature name, e.g., #editor-demo)
# Additional tags may be appended below the required pair
tags:
  - '#exec'
  - '#{feature}'
# ISO date format (e.g., 2026-02-06)
date: '{yyyy-mm-dd}'
# Related documents as quoted wiki-links - MUST link to parent PLAN
# (e.g., "[[2026-02-04-feature-plan]]")
related:
  - '[[{yyyy-mm-dd-*-plan}]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `{feature}` `{phase}` `{step}`

Brief summary of work done.

- Modified: `[[{file1}]]`
- Created: `[[{file2}]]`

## Description

Detailed description of implementation details.

## Tests

Brief description of tests and validation results.
Link any audit reports related to `{phase}` or `{step}`.
