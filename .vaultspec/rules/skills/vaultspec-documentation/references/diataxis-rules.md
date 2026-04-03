# Diataxis - Documentation Rule System

> Condensed adherence guide. Source: https://diataxis.fr/

______________________________________________________________________

## 1. The Framework

All documentation is exactly one of four types. Never blend them. When content drifts
across a boundary, extract it and **link** to the correct document instead.

```
              ACQUISITION                APPLICATION
              (learning)                 (working)
            +----------------------+----------------------+
   ACTION   |     TUTORIAL         |     HOW-TO GUIDE     |
   (doing)  |     "Teach me"       |     "Help me do X"   |
            +----------------------+----------------------+
  COGNITION |     EXPLANATION      |     REFERENCE        |
  (knowing) |     "Tell me about"  |     "Let me look up" |
            +----------------------+----------------------+
```

**To classify any piece of content, ask two questions:**

- Is this about **doing** something or **knowing** something?
- Is the user **learning** or **working**?

Apply this at any granularity - a sentence, a paragraph, an entire page.

______________________________________________________________________

## 2. Tutorial Rules

> A lesson. The learner acquires skills by doing, guided by a tutor.

**Golden rule: Don't try to teach. Create experiences that enable learning.**

DO:

- State the destination upfront ("In this tutorial, we will...")
- Produce a visible result at every step, however small
- Keep steps concrete, sequential, unambiguous ("First, do x. Now, do y.")
- Narrate expectations ("The output should look something like...")
- Point out details the learner will miss ("Notice that the prompt changed...")
- Make steps reversible so the learner can repeat them
- Test the tutorial with real users - fix every stumbling point
- Accept full authorial responsibility for the learner's success

DO NOT:

- Explain *why* something works
- Offer choices between approaches
- Include information "for completeness"
- Generalize or abstract
- Assume the learner can fill gaps
- Ship an untested tutorial

**Exercises must be:** meaningful, completable, logically ordered, and usefully complete.

**Drift check ->** drifting toward application? It's becoming a How-to Guide.
Drifting toward theory? It's becoming Explanation.

______________________________________________________________________

## 3. How-to Guide Rules

> A recipe. A competent user needs directions to reach a known goal.

**Golden rule: Action and only action.**

DO:

- Title as "How to [specific outcome]"
- Open with scope ("This guide shows you how to...")
- Sequence steps by dependency and workflow logic
- Use conditional imperatives for variant paths ("If you want x, do y.")
- Maintain flow - don't force context-switching between tools
- Anticipate what the user needs next; minimize backtracking
- Offload detail with links ("Refer to the X reference for full options.")
- Start and end at meaningful, practical boundaries
- Write from the user's perspective, not the tool's

DO NOT:

- Explain how the machinery works -> link to Reference
- Teach or scaffold learning -> link to Tutorial
- Include reference material for completeness -> link to Reference
- Document procedural trivia ("click Save to save")
- Write from the tool's perspective
- Address every edge case - prioritize practical usability

**Tutorial vs. How-to - the critical distinction:**

|             | Tutorial                           | How-to Guide                    |
| ----------- | ---------------------------------- | ------------------------------- |
| User        | Learner (doesn't know what to ask) | Practitioner (knows their goal) |
| Author      | Controls the path                  | Serves the user's goal          |
| Choices     | None                               | Conditional ("if x, do y")      |
| Explanation | Ruthlessly minimized               | Absent entirely                 |

**Drift check ->** drifting toward learning? It's becoming a Tutorial.
Drifting toward theory? It's becoming Reference.

______________________________________________________________________

## 4. Reference Rules

> A map. The user consults technical descriptions while working.

**Golden rule: Describe and only describe.**

DO:

- Mirror the product's own structure (modules -> sections)
- Use a single, repeatable format for every entry in a section
- State facts: parameters, return values, types, flags, limits, errors
- Provide terse usage examples that clarify without instructing
- Use imperative warnings where needed ("You must...", "Never...")
- Be complete within scope - gaps destroy trust
- Prioritize: accuracy -> precision -> completeness -> clarity

DO NOT:

- Embed tutorials or step-by-step instruction -> link to Tutorial / How-to
- Explain design decisions or history -> link to Explanation
- Offer opinions or recommend approaches
- Vary formatting between entries
- Organize by user workflow - organize by product architecture
- Omit items for brevity

**Drift check ->** drifting toward doing? It's becoming a How-to Guide.
Drifting toward learning/context? It's becoming Explanation.

______________________________________________________________________

## 5. Explanation Rules

> A discussion. The user builds understanding through reflection.

**Golden rule: Illuminate, don't instruct.**

DO:

- Organize around a topic or "why" question, not a task or machine
- Make connections - link concepts to each other and to external ideas
- Provide context: history, design rationale, constraints, implications
- Discuss the bigger picture: choices, alternatives, trade-offs
- Embrace perspective and opinion - this is the only type that expects it
- Present multiple viewpoints when the landscape is contested
- Use analogies to build bridges ("An X in system Y is analogous to...")
- Keep scope bounded - the "why question" is your boundary test

DO NOT:

- Write step-by-step procedures -> link to Tutorial / How-to
- Catalog technical specs -> link to Reference
- Present a single "correct" view when alternatives exist
- Let scope drift unbounded
- Undervalue this type - it's the connective tissue of mastery

**Drift check ->** drifting toward doing? It's becoming a Tutorial.
Drifting toward lookup/application? It's becoming Reference.

______________________________________________________________________

## 6. Quality Checklist

Apply to any document, regardless of type:

**Functional quality** (objective - measure these):

- \[ \] **Accurate** - conforms to the subject matter
- \[ \] **Complete** - covers the documented scope without gaps
- \[ \] **Consistent** - uniform presentation throughout
- \[ \] **Useful** - delivers practical value to the reader
- \[ \] **Precise** - exact, unambiguous language

**Deep quality** (subjective - judge these):

- \[ \] **Flow** - movement between sections feels natural and unforced
- \[ \] **Anticipation** - proactively addresses what the reader needs next
- \[ \] **Feel** - the document feels good to use
- \[ \] **User-centric** - fitted to human needs, not organizational convenience

Deep quality requires functional quality. Never skip the checklist.

______________________________________________________________________

## 7. Quick Decision Matrix

Use this when you're unsure what type of document to write or when reviewing existing docs:

| Signal in your content              | You are writing | Should be in |
| ----------------------------------- | --------------- | ------------ |
| "Follow these steps to learn..."    | Tutorial        | Tutorial     |
| "To achieve X, do Y then Z..."      | How-to Guide    | How-to Guide |
| "X accepts parameters A, B, C..."   | Reference       | Reference    |
| "The reason X works this way is..." | Explanation     | Explanation  |
| "Here's why, and also do this..."   | **Mixed**       | **Split it** |
| "Step 3: (and here's why)..."       | **Mixed**       | **Split it** |

**When in doubt: split and link.**
