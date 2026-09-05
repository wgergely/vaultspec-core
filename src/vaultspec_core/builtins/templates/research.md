---
tags:
  - '#research'
  - '#{feature}'
date: '{yyyy-mm-dd}'
modified: '{yyyy-mm-dd}'
body_schema: 'body-v1'
related:
  - '[[{yyyy-mm-dd-*}]]'
---

<!-- FRONTMATTER RULES:
     tags: one directory tag (hardcoded #research) and one feature tag.
     Replace {feature} with a kebab-case feature tag, e.g. #foo-bar.
     Exactly these two tags are allowed; do not append additional tags.

     Related: use wiki-links as '[[yyyy-mm-dd-foo-bar]]'.

     modified: CLI-maintained last-modified stamp; set at scaffold time,
     refreshed by mutating CLI verbs and vault check fix; never hand-edit.

     DO NOT add fields beyond those scaffolded; metadata lives
     only in the frontmatter. -->

<!-- LINK RULES:
     - [[wiki-links]] are ONLY for .vault/ documents in the related: field above.
     - NEVER use [[wiki-links]] or markdown [label](path) links in the document body.
     - Cite external sources as bare URLs. Cite code, commits, packages, and
       standards as inline backtick locators: `src/module.py:42`, commit
       `abc1234`, `package@1.2.3`, RFC 9110. -->

<!-- DOCUMENT BOUNDARY:
     Research grounds; the ADR decides. Frame the option space with evidence
     and trade-offs; at most name the option the evidence favors and what
     the ADR must settle. Never record the decision here - a decision
     outside the ADR forks and goes stale when the ADR chooses otherwise. -->

# `{feature}` research: `{topic}`

<!-- Lead: the question, why it matters to `{feature}`, and what was
     concluded - the evidence picture, not a decision. -->

## Findings

<!-- One ### subsection per line of inquiry. Claim first, evidence after.
     Anchor every non-obvious claim to a re-fetchable locator (URL,
     `file:line`, commit SHA, `package@version`, RFC number). Link, do not
     copy. Pin versions, dates, numbers. State each fact once: link what a
     related vault document already records; do not repeat what an earlier
     section establishes. Name alternatives and why kept or rejected. State
     what was not investigated. Cut anything that changes no decision. -->

## Sources

<!-- Each locator cited above, once: `path:line` backtick locators for code,
     bare URLs for external references. Flag unverified general-knowledge
     claims. -->
