# Product Health Audit (Team)

Start an code health audit. Do NOT trust tests as a valid indicator for code health. Tests can be written in a way that they pass without actually revealing the true functionality and behavior of the codebase. Instead, focus on the quality of the code itself, its maintainability, readability, and how well it adheres to the project mission goals. Is it well structured? Does it follow best practices? Is it easy to understand and modify? These are the indicators of code health that we should be focusing on.

## Identify

- Tests that do not provide insight into the actual integration and production flow. This includes tests that are too narrowly focused, do not cover edge cases, or are written in a way that they can pass without truly validating the functionality of the code.
- Mocks, patches, stubs, false positives. These are NOT acceptable and are indicative of bad programming.Tests must be written in a way that they reveal the true behavior of the codebase in a production environment.
- Stale or badly optimized or structured tests.
- Unittest module imports. These are NOT supported. Always favor pytest for testing in Python.
- conftest.py files. Ensure they do not contain duplicate fixtures, unsupported markers. Audit them to ensure they define every required highlevel fixtures required for successful e2e and integration testing. DO NOT allow tests to try to solve issues individually that should be centralized.

## Verify

- Python and rust unit tests that do not reside in their source module's test directory.
- Integration tests and e2e tests are the only tests to be kep in the main module's tests/ directory.

[!Note] Any monkey patching must be explicitly approved by the user and are generally discouraged. If monkey patching is necessary, it must be done in a way that does not obscure the true behavior of the codebase and must be clearly documented.

## Team Composition

- Supervisor: This Opus agent supervises the team in read-only mode. The Supervisor's role is to step in when detect "low-effort" work and code. This is the quality enfocer who will reject any work that doesn't pass the mustard.
- Investigator1-3: These SOnnet agents arre responsible for reading the codebase, identifying issues, and providing detailed reports on code health. They will focus on different aspects of the codebase, such as maintainability, readability, and adherence to best practices. They will work in parallel to ensure a comprehensive audit of the codebase and report back to the the team lead.
- CodingAgent1-2: Opus agents responsible for coding work. Does not execute tests. Focuses solely on writing code that compiles and runs, without any regard for test outcomes. Works in parallel with CodingAgent2.
- TestRunner1-2: Read-only Haiku test runners responsible for running tests and reporting failures. This is the ONLY agent that runs tests. It does not write code or modify the codebase in any way. Its sole responsibility is to execute tests and report the results.

The team lead must never itself perform any heavy lifting and must instead only focus on managing the work and flow of the team, stepping in when agents are stuck, in loop or in need of further instructions. The team lead is the only agent that can communicate with the user and must ensure that all communication is clear, concise, and informative. The team lead is also responsible for ensuring that all agents are working effectively and efficiently, and that the overall goals of the audit are being met.
