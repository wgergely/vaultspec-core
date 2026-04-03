# Prose & Style - Rule System

> Condensed from the Google Developer Documentation Style Guide and the Microsoft
> Writing Style Guide. Use alongside `diataxis-rules.md` for complete coverage.
>
> Sources:
>
> - https://developers.google.com/style
> - https://learn.microsoft.com/en-us/style-guide/welcome/

______________________________________________________________________

## 1. Voice

Write like a knowledgeable friend explaining something at a whiteboard. Conversational,
not casual. Warm, not sloppy.

- **Active voice by default.** Make the doer the subject. "The server sends a response,"
  not "A response is sent by the server."
- **Passive is acceptable** when the actor is unknown, irrelevant, or when you want to
  emphasize the object ("The file is deleted after 30 days.").
- **Second person ("you") as default.** Address the reader directly. Reserve "we" for the
  authoring organization with a clear antecedent.
- **Imperative for instructions.** "Click Submit," "Run the command," "Add the flag."
  Implied "you." No "please."
- **Present tense by default.** Describe what the software *does*, not what it *will do*.

______________________________________________________________________

## 2. Brevity

Shorter is always better. Every word must earn its place.

| Cut this                     | Write this                                 |
| ---------------------------- | ------------------------------------------ |
| "In order to"                | "To"                                       |
| "It is necessary to"         | "You must" / "You need to"                 |
| "You can use X to do Y"      | "Use X to do Y" / start with the verb      |
| "There is a command that..." | Name the command directly                  |
| "Allows you to"              | "Lets you"                                 |
| "As a matter of fact"        | cut entirely                               |
| "And/or"                     | "or" (or "and" - pick one, or restructure) |
| "Create a new project"       | "Create a project" ("new" is redundant)    |
| "Please click"               | "Click"                                    |

Rules:

- **Lead with what matters most.** Front-load the key information. Readers scan before
  they read.
- **One idea per sentence.** If a sentence has two ideas, split it.
- **Cut "you can."** Start with the verb instead.
- **Cut "there is / there are / there were."** Restructure around the real subject.
- **Cut filler:** "basically," "actually," "really," "quite," "very," "just," "that,"
  "in this case," "as mentioned above."
- **Sentences under 26 words.** If it's longer, split or prune.
- **Paragraphs under 5 sentences.** If longer, break it up.

______________________________________________________________________

## 3. Clarity

- **One term per concept.** Pick a word and stick to it. Don't alternate between
  "repository," "repo," and "project" for the same thing.
- **Define acronyms on first use.** Spell out, then parenthetical:
  "Content Delivery Network (CDN)."
- **Conditions before instructions.** "If the build fails, run `make clean`" -
  not "Run `make clean` if the build fails."
- **Specific over vague.** "Takes about 5 minutes" - not "Takes a moment."
- **No double negatives.** "You can access" - not "You can't not access."
- **Distinguish similar terms precisely.** Authentication ≠ authorization.
  Deprecate ≠ remove.

______________________________________________________________________

## 4. Tone

- **Conversational, not casual.** Sound like a person, not a textbook and not a
  group chat.
- **Confident, not arrogant.** State facts. Don't hedge unnecessarily, but don't
  over-promise.
- **Helpful, not patronizing.** Never call something "easy," "simple," "obvious,"
  or "trivial." What's easy for one reader is hard for another.
- **Neutral on error.** When things go wrong, describe what happened and what to do
  next. Don't blame the user. Don't be cute about failures.
- **No exclamation marks** in technical documentation. Save them for release notes or
  marketing, if at all.
- **No humor that sacrifices clarity.** If a joke adds confusion or doesn't translate,
  cut it.
- **Use contractions.** "It's," "you'll," "don't," "can't." They sound human.
  Avoid contracting nouns + verbs where ambiguity arises ("The key's value" - unclear).

______________________________________________________________________

## 5. Formatting

- **Sentence case for all headings.** Capitalize only the first word and proper nouns.
  Never Title Case Every Word.
- **Numbered lists for sequential steps.** Bulleted lists for unordered items.
- **Serial (Oxford) comma. Always.** "Android, iOS, and Windows."
- **One space after periods.** Never two.
- **Avoid em dashes** except where absolutely justified. Use spaced hyphens ( - )
  instead. "Use pipelines - logical groups - to organize work."
- **No periods on headings, subheadings, or list items under 3 words.**
- **Bold for UI elements.** "Click **Settings**." Code font for code, commands,
  filenames, and parameters.
- **Meaningful link text.** "See the [authentication guide](...)" -
  not "Click [here](...)."

______________________________________________________________________

## 6. Inclusive Language

Write for everyone. Documentation reaches a global audience with varying backgrounds,
abilities, and English proficiency.

### Gender

- Use "they/them" as singular gender-neutral pronoun.
- Prefer second person ("you") to avoid the problem entirely.
- Never use "he/she," "s/he," or "his/her."
- Use gender-neutral role terms: "staffs" not "mans," "chair" not "chairman,"
  "workforce" not "manpower."

### Race & Culture

- No slang that could be cultural appropriation.
- No generalizations about people, countries, or cultures.
- When listing regions, use parallel references (don't mix continents with countries).

### Ability

- Focus on people, not conditions. "Users who are blind" - not "blind users."
- Don't mention disability unless relevant.
- No pity language: "suffers from," "stricken with," "confined to."

### Technical Terminology

| Use this             | Not this                 |
| -------------------- | ------------------------ |
| allowlist / denylist | whitelist / blacklist    |
| primary / replica    | master / slave           |
| on-path attacker     | man-in-the-middle        |
| perimeter network    | demilitarized zone (DMZ) |
| stop responding      | hang                     |

### Words to Avoid

| Avoid                      | Reason                            | Alternative                               |
| -------------------------- | --------------------------------- | ----------------------------------------- |
| "easy," "simple," "just"   | assumes reader's skill level      | describe the steps; let the reader decide |
| "obviously," "of course"   | patronizing                       | cut entirely                              |
| "etc."                     | vague                             | list the items, or "such as X, Y, and Z"  |
| "crazy," "insane," "lame"  | ableist                           | "unexpected," "broken," "unhelpful"       |
| "for instance"             | confuses with database "instance" | "for example"                             |
| "impact" (as verb)         | imprecise                         | "affect"                                  |
| "leverage" (as verb)       | jargon                            | "use"                                     |
| "utilize"                  | unnecessarily formal              | "use"                                     |
| "in order to"              | wordy                             | "to"                                      |
| "please" (in instructions) | unnecessarily deferential         | cut it                                    |

______________________________________________________________________

## 7. Accessibility

Write so everyone can read, navigate, and understand your documentation - including
people using screen readers, keyboard navigation, or translation tools.

- **No images of text.** Use actual text for code, commands, and terminal output.
- **Alt text on every image.** Describe the intent, not the decoration. Use empty alt
  for purely decorative images.
- **No directional references.** "The following table" - not "the table below" or
  "the right sidebar." Screen readers and reflowed layouts break spatial assumptions.
- **Describe link destinations.** "Download the configuration file" - not
  "click here."
- **Don't rely on color alone** to communicate state. Add a text label.
- **Unique, descriptive headings.** Never skip heading levels (h1 -> h3).
- **Left-align text.** No center or full justification.
- **No ALL CAPS.** Screen readers may spell them out letter by letter.
- **No camelCase in prose.** Screen readers struggle with it.
- **Avoid flashing or flickering elements.**

______________________________________________________________________

## 8. Self-Check

Before publishing, verify:

- \[ \] Read it aloud - does it sound like a person talking?
- \[ \] Every sentence starts with the most important word or phrase
- \[ \] No sentence exceeds 26 words
- \[ \] No "you can," "there is," "please," or "easy/simple"
- \[ \] Active voice throughout (passive only where justified)
- \[ \] One term per concept, consistent across the document
- \[ \] All acronyms defined on first use
- \[ \] Conditions precede instructions
- \[ \] Headings are sentence case
- \[ \] Serial commas present
- \[ \] Link text is descriptive
- \[ \] Alt text on all images
- \[ \] No directional references ("above," "below," "right")
- \[ \] Inclusive language - no gendered, ableist, or racialized terms
