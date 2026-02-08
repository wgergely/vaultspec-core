# Research, Design, Task Driven Development Framework

This project provides a comprehensive framework for structured AI-driven software development. It enforces a strict **Research → Decide → Plan → Execute** workflow to ensure maintainability, context preservation, and high-quality output.

## Core Components

* **Rules & Workflows:** Defines the protocols for research, architectural decision records (ADRs), planning, and execution.

* **Agent Definitions:** Specifies roles and responsibilities for specialized sub-agents (e.g., Researcher, Planner, Executor, Reviewer).

* **Templates:** Standardized formats for all documentation and artifacts.

* **Compatibility:** Designed for use with AI coding assistants like Gemini CLI, Google Antigravity, and Claude Code.

> [!CAUTION]
> **Framework Development:** This repository is for the development of the framework itself. **DO NOT** run `cli.py config sync` or similar commands to "install" the framework into this root directory. The `.rules/` folder here is the source of truth, and syncing it to the root (e.g., creating a root `AGENTS.md`) will cause recursive context issues and potential data loss during development.
