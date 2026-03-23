---
# REQUIRED TAGS (minimum 2): one directory tag + one feature tag
# DIRECTORY TAGS: #adr #audit #exec #plan #reference #research
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/audit/ location)
# Feature tag (replace {feature} with your feature name, e.g., #editor-demo)
# Additional tags may be appended below the required pair
tags:
  - '#audit'
  - '#{feature}'
# ISO date format (e.g., 2026-02-06)
date: '{yyyy-mm-dd}'
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-plan]]")
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

# `{feature}` Code Review

<!-- Persistent log of audit findings appended below. -->

<!-- Use: {TOPIC}-### | {LEVEL} | {Summary} \n {DESCRIPTION} format-->
