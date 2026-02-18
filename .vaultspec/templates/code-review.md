---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/exec/ location)
# Feature tag (replace {feature} with your feature name, e.g., #editor-demo)
tags:
  - "#exec"
  - "#{feature}"
# ISO date format (e.g., 2026-02-06)
date: "{yyyy-mm-dd}"
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-plan]]")
related:
  - "[[{yyyy-mm-dd-*}]]"
---

# `{feature}` code review

<!-- STATUS MUST BE ONE OF: PASS | FAIL | REVISION REQUIRED -->

**Status:** `{PASS|FAIL|REVISION REQUIRED}`

## Audit Context

- **Plan:** `[[{yyyy-mm-dd-feature-plan}]]`
- **Scope:** List of files or modules reviewed

## Findings

Classify findings by Severity: CRITICAL, HIGH, MEDIUM, LOW

### Critical / High (Must Fix)

- **[CRITICAL]** `{Location}`: `{Description}`
- **[HIGH]** `{Location}`: `{Description}`

### Medium / Low (Recommended)

- **[MEDIUM]** `{Location}`: `{Description}`
- **[LOW]** `{Location}`: `{Description}`

## Recommendations

Actionable next steps. If FAIL, list specific requirements for re-submission.

## Notes
