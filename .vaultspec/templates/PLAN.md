---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #exec #plan #reference #research #<feature>
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/plan/ location)
# Feature tag (replace <feature> with your feature name, e.g., #editor-demo)
tags:
  - "#plan"
  - "#<feature>"
# ISO date format (e.g., 2026-02-06)
date: <yyyy-mm-dd>
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-adr]]")
related:
  - "[[<yyyy-mm-dd-*>]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# <feature> <phase> plan

<Brief description of the proposed feature|change|refactor.>

## Proposed Changes

<Describe what work needs to be done at a high level. Reference <adr>s, <research>, <reference>, and other plan or reference files where appropriate so implementation remains grounded in architectural decisions.>

## Tasks

<Use numbered phases for complex features:>

<!IMPORTANT: This document must be updated between execution runs to track progress.>

- <Phase 1>
    1 <Step 1.1>
    2 <Step 1.2>
- <Phase 2>
    1 <Step 2.1>
    2 <Step 2.2>

<Use tasks for simpler features:>

- <Task 1>
- <Task 2>
- <Task 3>

## Parallelization

<Brief opinion on how tasks might be parallelized, if at all.>

## Verification

<Clear mission success criteria. Focus on feature coverage against the original <adr>s and <research> documents.>

<Research and ideate on how to ensure besides unit testing that we have fulfilled our mission?>

<Example: "Run unit and integration tests (all pass). However, could not visually confirm that the feature was functional. Further work is required to implementation features to enable better testing." <- Be honest and remember that tests can be cheated!>
