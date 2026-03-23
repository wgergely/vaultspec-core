---
# REQUIRED TAGS (minimum 2): one directory tag + one feature tag
# DIRECTORY TAGS: #adr #audit #exec #plan #reference #research
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/adr/ location)
# Feature tag (replace {feature} with your feature name, e.g., #editor-demo)
# Additional tags may be appended below the required pair
tags:
  - '#adr'
  - '#{feature}'
# ISO date format (e.g., 2026-02-06)
date: '{yyyy-mm-dd}'
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-research]]")
related:
  - '[[{yyyy-mm-dd-*}]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

<!-- LINK RULES:
     - [[wiki-links]] are ONLY for .vault/ documents in the related: field above.
     - NEVER use [[wiki-links]] or markdown links in the document body.
     - NEVER reference file paths in the body. If you must name a source file,
       class, or function, use inline backtick code: `src/module.py`. -->

# `{feature}` adr: `{title}` | (**status:** `{accepted|rejected|deprecated}`)

## Problem Statement

Briefly describe the architectural problem or concern.

## Considerations

Key factors, constraints, requirements. Tech/libraries considered.

## Constraints

Technical limitations, time constraints, etc.

## Implementation

High-level description of HOW it will be implemented. Reference `{research}`
and `{reference}` specs.

## Rationale

Why this option was chosen. Reference `{research}` findings and external
`{reference}` patterns.

## Consequences

Difficulties, implementation consequences, future considerations.
