---
# REQUIRED TAGS (minimum 2): one directory tag + one feature tag
# DIRECTORY TAGS: #adr #audit #exec #plan #reference #research
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/reference/ location)
# Feature tag (replace {feature} with your feature name, e.g., #editor-demo)
# Additional tags may be appended below the required pair
tags:
  - "#reference"
  - "#{feature}"
# ISO date format (e.g., 2026-02-06)
date: "{yyyy-mm-dd}"
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-research]]")
related:
  - "[[{yyyy-mm-dd-*}]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `{feature}` reference: `{topic}`

Brief description of what was researched and what sources were consulted.

Include any concrete references to files, line numbers, modules, etc. This is
the information that coding agents will consult during implementation.

## Findings

Findings pertinent to `{feature}` being considered. Include implementation
details and architecture overviews considered insightful, essential, or
relevant. Adapt format to content.
