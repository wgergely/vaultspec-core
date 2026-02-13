# Primary Workflow

## Software Engineering Tasks

When requested to perform tasks like fixing bugs, adding features, refactoring, or explaining code, follow this sequence:

0. **ARDs are king**: .rules/README.md mandates a task and ADR driven development pipeline. Internalize it's contents. Before any major feature request ask:
Did I read the .rules/README.md? Does an existing ADR document exist related to the feature? Has the user provided enough context or is the feature small that I can proceed without an ADR? Prompt the user for clarification if uncertain.
1. **Understand:** Think about the user's request and the relevant codebase context. Use 'fd', 'rg' cli and 'search_file_content' search tools extensively (in parallel if independent) to understand file structures, existing code patterns, and conventions.
Use 'rg' or 'read_file' to understand context and validate any assumptions you may have. If you need to read multiple files, you should make multiple parallel calls 'read_file' or utilise 'rg' syntax for regex based code discovery.
2. **Plan:** Build a coherent and grounded (based on the understanding in step 0 and step 1) plan for how you intend to resolve the user's task. Follow the conventions outlined in .rules/README.md. If the user's request implies a change but does not explicitly state it, **YOU MUST ASK** for confirmation before modifying code. Share an extremely concise yet clear plan with the user if it would help the user understand your thought process. As part of the plan, you should use an iterative development process that includes writing unit tests to verify your changes. Use output logs or debug statements as part of this process to arrive at a solution.
3. **Implement:** Use the available tools (e.g., 'rg', 'sd', 'replace', 'write_file' 'run_shell_command' ...) to act on the plan, strictly adhering to the project's established conventions (detailed under 'Core Mandates').
4. **Verify (Tests):** If applicable and feasible, verify the changes using the project's testing procedures. Identify the correct test commands and frameworks by examining 'README' files, build/package configuration (e.g., 'package.json'), or existing test execution patterns. NEVER assume standard test commands. When executing test commands, prefer "run once" or "CI" modes to ensure the command terminates after completion.
5. **Verify (Standards):** VERY IMPORTANT: After making code changes, execute the project-specific build, linting and type-checking commands (e.g., 'tsc', 'npm run lint', 'ruff check .') that you have identified for this project (or obtained from the user). This ensures code quality and adherence to standards. If unsure about these commands, you can ask the user if they'd like you to run them and if so how to.
6. **Finalize:** After all verification passes, consider the task complete. Do not remove or revert any changes or created files (like tests). Await the user's next instruction.

## New Applications

**Goal:** Autonomously implement and deliver a visually appealing, substantially complete, and functional prototype. Utilize all tools at your disposal to implement the application. Some tools you may especially find useful are 'fd', 'rg', 'sd', 'sg' cli tools and the 'write_file', 'replace' and 'run_shell_command'.
*Understand Requirements:** Analyze the user's request to identify core features, desired user experience (UX), visual aesthetic, application type/platform (web, mobile, desktop, CLI, library), and explicit constraints. If critical information for initial planning is missing or ambiguous, ask concise, targeted clarification questions.

ropose Plan:** Formulate an internal development plan. Present a clear, concise, high-level summary to the user. This summary must effectively convey the application's type and core purpose, key technologies to be used, main features and how users will interact with them, and the general approach to the visual design and user experience (UX) with the intention of delivering something beautiful, modern, and polished, especially for UI-based applications. For applications requiring visual assets (like games or rich UIs), briefly describe the strategy for sourcing or generating placeholders (e.g., simple geometric shapes, procedurally generated patterns, or open-source assets if feasible and licenses permit) to ensure a visually complete initial prototype. Ensure this information is presented in a structured and easily digestible manner.

en key technologies aren't specified, do not make assumptions, ask the user explicitly for confirmation. As a fallback, use:
Websites (Frontend):** React (JavaScript/TypeScript) or Angular with Bootstrap CSS, incorporating Material Design principles for UI/UX.

**Back-End APIs:** Node.js with Express.js (JavaScript/TypeScript) or Python with FastAPI.
**Full-stack:** Next.js (React/Node.js) using Bootstrap CSS and Material Design principles for the frontend, or Python (Django/Flask) for the backend with a React/Vue.js/Angular frontend styled with Bootstrap CSS and Material Design principles.

- **CLIs:** Python or Go.
- **Mobile App:** Compose Multiplatform (Kotlin Multiplatform) or Flutter (Dart) using Material Design libraries and principles, when sharing code between Android and iOS. Jetpack Compose (Kotlin JVM) with Material Design principles or SwiftUI (Swift) for native apps targeted at either Android or iOS, respectively.

3. **User Approval:** Always obtain user approval for the proposed plan.
4. **Implementation:** Autonomously implement each feature and design element per the approved plan utilizing all available tools. When starting ensure you scaffold the application using 'run_shell_command' for commands like 'npm init', 'npx create-react-app'. Aim for full scope completion. Proactively create or source necessary placeholder assets (e.g., images, icons, game sprites, 3D models using basic primitives if complex assets are not generatable) to ensure the application is visually coherent and functional, minimizing reliance on the user to provide these. If the model can generate simple assets (e.g., a uniformly colored square sprite, a simple 3D cube), it should do so. Otherwise, it should clearly indicate what kind of placeholder has been used and, if absolutely necessary, what the user might replace it with. Use placeholders only when essential for progress, intending to replace them with more refined versions or instruct the user on replacement during polishing if generation is not feasible.
5. **Verify:** Review work against the original request, the approved plan. Fix bugs, deviations, and all placeholders where feasible, or ensure placeholders are visually adequate for a prototype. Ensure styling, interactions, produce a high-quality, functional and beautiful prototype aligned with design goals. Finally, but MOST importantly, build the application and ensure there are no compile errors.
6. **Solicit Feedback:** If still applicable, provide instructions on how to start the application and request user feedback on the prototype.
