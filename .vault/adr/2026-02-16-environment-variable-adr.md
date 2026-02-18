---
tags: ["#adr", "#framework"]
date: 2026-02-16
related:
  - "[[2026-02-16-env-var-research]]"
  - "[[2026-02-16-hardcoded-constants-research]]"
  - "[[2026-02-16-environment-variable-research]]"
---

## Environment Variable Standardization Blueprint

## Executive Summary

### Current State Assessment

The vaultspec codebase has **fragmented environment variable management** across multiple modules:

- **14 existing environment variables** scattered across 7 Python files (48+ access points)

- **38+ hardcoded configuration constants** that should be environment-configurable

- **Inconsistent naming patterns** (`VS_*`, `GEMINI_*`, module-level globals)

- **No centralized configuration registry** or validation framework

- **Duplicate test constants** in multiple conftest.py files

- **Silent failures** when invalid values are provided

### Vision for Standardized Config System

Create a unified, maintainable configuration system that:

1. **Centralizes all configuration** in a single `config.py` module
2. **Standardizes naming** using `VAULTSPEC_*` prefix for all environment variables
3. **Validates all configuration** with type safety and bounds checking

4. **Documents all variables** in a canonical registry (`.env.example`)
5. **Supports dependency injection** for testing without environment manipulation
6. **Eliminates duplicate constants** through shared test fixtures
7. **Provides clear precedence** (constructor param → env var → hardcoded default)

### High-Level Impact & Benefits

| Benefit | Impact |

|---------|--------|
| **Discoverability** | Developers immediately know all available configurations |
| **Maintainability** | Centralized registry prevents drift and duplication |
| **Type Safety** | Structured config with validation catches errors early |

| **Testing** | Easy to override without modifying os.environ |
| **Operations** | Clear `.env.example` and deployment documentation |
| **Extensibility** | Add new configs without discovering scattered patterns |
| **Auditability** | Single source of truth for configuration access |

---

## Complete Environment Variable Registry

This is the canonical table of **ALL environment variables that SHOULD exist** in the vaultspec system:

### Naming Convention

- **Prefix**: `VAULTSPEC_` (primary standard), legacy `VS_*` accepted during transition
- **Grouping**: `VAULTSPEC_{CATEGORY}_{ITEM}` (e.g., `VAULTSPEC_MCP_PORT`)

- **Format**: ALL_CAPS with underscores
- **Lists**: Comma-separated values (e.g., `tool1,tool2,tool3`)
- **Numeric**: Bare numbers for ports, decimal for timeouts/floats
- **Paths**: Absolute or relative; resolved at runtime

### Complete Registry

| Variable Name | Category | Current Value | Type | Default | Description | Priority | Risk | Status |
|---|---|---|---|---|---|---|---|---|
| `VAULTSPEC_ROOT_DIR` | Core | `os.getcwd()` | Path | `cwd` | Workspace root directory | HIGH | LOW | Existing (VS_ROOT_DIR) |

| `VAULTSPEC_AGENT_MODE` | Agent | "read-write" | Enum | "read-write" | Agent sandboxing policy (read-write/read-only) | HIGH | LOW | Existing (VS_AGENT_MODE) |
| `VAULTSPEC_SYSTEM_PROMPT` | Agent | `None` | String | `None` | System prompt override for agent | MEDIUM | LOW | Existing (VS_SYSTEM_PROMPT) |
| `VAULTSPEC_MAX_TURNS` | Agent | `None` | Int | `None` | Maximum number of agent turns | MEDIUM | MEDIUM | Existing (VS_MAX_TURNS) |
| `VAULTSPEC_BUDGET_USD` | Agent | `None` | Float | `None` | Maximum cost budget in USD | MEDIUM | MEDIUM | Existing (VS_BUDGET_USD) |
| `VAULTSPEC_ALLOWED_TOOLS` | Agent | `[]` | CSV | `[]` | Comma-separated list of allowed MCP tools | MEDIUM | LOW | Existing (VS_ALLOWED_TOOLS) |

| `VAULTSPEC_DISALLOWED_TOOLS` | Agent | `[]` | CSV | `[]` | Comma-separated list of disallowed MCP tools | MEDIUM | LOW | Existing (VS_DISALLOWED_TOOLS) |
| `VAULTSPEC_EFFORT` | Agent | `None` | String | `None` | Agent effort level (high/medium/low) | LOW | LOW | Existing (VS_EFFORT) |
| `VAULTSPEC_OUTPUT_FORMAT` | Agent | `None` | String | `None` | Output format specification (json/text) | LOW | LOW | Existing (VS_OUTPUT_FORMAT) |
| `VAULTSPEC_FALLBACK_MODEL` | Agent | `None` | String | `None` | Fallback model if primary fails | LOW | LOW | Existing (VS_FALLBACK_MODEL) |
| `VAULTSPEC_INCLUDE_DIRS` | Agent | `[]` | CSV | `[]` | Comma-separated list of include directories | LOW | LOW | Existing (VS_INCLUDE_DIRS) |

| `VAULTSPEC_MCP_ROOT_DIR` | MCP | Required | Path | — | MCP server workspace root | HIGH | HIGH | Existing (VS_MCP_ROOT_DIR) |
| `VAULTSPEC_MCP_TTL_SECONDS` | MCP | 3600.0 | Float | 3600.0 | MCP task retention period in seconds | HIGH | HIGH | Existing (VS_MCP_TTL_SECONDS) |
| `VAULTSPEC_MCP_PORT` | MCP | 10010 | Int | 10010 | MCP server listen port | HIGH | MEDIUM | NEW (hardcoded) |
| `VAULTSPEC_MCP_HOST` | MCP | "0.0.0.0" | String | "0.0.0.0" | MCP server bind address | HIGH | LOW | NEW (hardcoded) |
| `VAULTSPEC_A2A_DEFAULT_PORT` | A2A | 10010 | Int | 10010 | A2A agent card default port | MEDIUM | MEDIUM | NEW (hardcoded) |

| `VAULTSPEC_A2A_HOST` | A2A | "localhost" | String | "localhost" | A2A agent discovery host | MEDIUM | MEDIUM | NEW (hardcoded) |
| `VAULTSPEC_DOCS_DIR` | Storage | ".vault" | Path | ".vault" | Vault documentation directory | HIGH | HIGH | NEW (hardcoded) |
| `VAULTSPEC_FRAMEWORK_DIR` | Storage | ".vaultspec" | Path | ".vaultspec" | Framework root directory | MEDIUM | MEDIUM | NEW (hardcoded) |
| `VAULTSPEC_LANCE_DIR` | Storage | ".lance" | Path | ".lance" | Vector database directory | HIGH | HIGH | NEW (hardcoded) |
| `VAULTSPEC_INDEX_METADATA_FILE` | Storage | "index_meta.json" | String | "index_meta.json" | Index metadata filename | MEDIUM | MEDIUM | NEW (hardcoded) |

| `VAULTSPEC_CLAUDE_DIR` | Tools | ".claude" | Path | ".claude" | Claude tool configuration directory | MEDIUM | LOW | NEW (hardcoded) |
| `VAULTSPEC_GEMINI_DIR` | Tools | ".gemini" | Path | ".gemini" | Gemini tool configuration directory | MEDIUM | LOW | NEW (hardcoded) |
| `VAULTSPEC_ANTIGRAVITY_DIR` | Tools | ".antigravity" | Path | ".antigravity" | Antigravity tool configuration directory | LOW | LOW | NEW (hardcoded) |
| `VAULTSPEC_TASK_ENGINE_TTL_SECONDS` | Orchestration | 3600.0 | Float | 3600.0 | Task engine cleanup TTL in seconds | MEDIUM | MEDIUM | NEW (hardcoded) |
| `VAULTSPEC_GRAPH_TTL_SECONDS` | RAG | 300.0 | Float | 300.0 | VaultGraph cache TTL in seconds | MEDIUM | LOW | NEW (hardcoded) |

| `VAULTSPEC_EMBEDDING_BATCH_SIZE` | RAG | 64 | Int | 64 | GPU embedding batch size | MEDIUM | MEDIUM | NEW (hardcoded) |
| `VAULTSPEC_MAX_EMBED_CHARS` | RAG | 8000 | Int | 8000 | Maximum characters to embed per document | MEDIUM | MEDIUM | NEW (hardcoded) |
| `VAULTSPEC_IO_BUFFER_SIZE` | I/O | 8192 | Int | 8192 | ACP subprocess read buffer size | LOW | LOW | NEW (hardcoded) |
| `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` | I/O | 1000000 | Int | 1000000 | Maximum terminal output capture in bytes | LOW | LOW | NEW (hardcoded) |
| `VAULTSPEC_GEMINI_MIN_VERSION_WINDOWS` | Reference | "0.9.0" | String | "0.9.0" | Minimum Gemini CLI version for Windows (reference only) | LOW | NONE | NEW (hardcoded) |

| `VAULTSPEC_GEMINI_MIN_VERSION_RECOMMENDED` | Reference | "0.27.0" | String | "0.27.0" | Recommended Gemini CLI version (reference only) | LOW | NONE | NEW (hardcoded) |
| `VAULTSPEC_TEST_LANCE_SUFFIX` | Test | "-fast" | String | "-fast" | Lance directory suffix for test isolation | LOW | LOW | NEW (hardcoded) |
| `EDITOR` | Legacy | "zed -w" | String | "zed -w" | Default text editor command | LOW | LOW | Existing (standard Unix) |

**Summary:**

- **Total variables**: 33
- **Existing (VS_*)**: 14
- **New (VAULTSPEC_*)**: 19
- **Priority distribution**: 6 HIGH, 12 MEDIUM, 15 LOW/REFERENCE
- **Categories**: Agent (7), MCP (4), A2A (2), Storage (4), Tools (3), Orchestration (1), RAG (3), I/O (2), Test (1), Legacy (1), Reference (2)

---

## Core Config Module Design

### Proposed Structure: `.vaultspec/lib/src/core/config.py`

```python
"""
Centralized configuration module for vaultspec.

Provides a single source of truth for all environment variables,
with validation, type conversion, and sensible defaults.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


# ===== ENUMS =====

class AgentMode(str, Enum):
    """Agent sandboxing modes."""
    READ_WRITE = "read-write"
    READ_ONLY = "read-only"


# ===== CONFIG METADATA REGISTRY =====

@dataclass
class ConfigVariable:
    """Metadata for a single configuration variable."""
    name: str                          # Environment variable name
    var_type: type                     # Expected type (str, int, float, Path, etc)
    default: Any                       # Default value
    description: str                   # Human-readable description
    required: bool = False             # Must be set to proceed
    options: Optional[List[str]] = None # Valid values for enum-like vars
    min_value: Optional[float] = None  # Minimum for numeric values
    max_value: Optional[float] = None  # Maximum for numeric values
    parser: Optional[callable] = None  # Custom parser function


# ===== REGISTRY =====

CONFIG_REGISTRY: Dict[str, ConfigVariable] = {
    # Agent variables
    "VAULTSPEC_AGENT_MODE": ConfigVariable(
        name="VAULTSPEC_AGENT_MODE",
        var_type=str,
        default="read-write",
        description="Agent sandboxing policy (read-write or read-only)",
        options=["read-write", "read-only"],
    ),
    "VAULTSPEC_MAX_TURNS": ConfigVariable(
        name="VAULTSPEC_MAX_TURNS",
        var_type=int,
        default=None,
        description="Maximum number of agent turns",
        min_value=1,
    ),
    "VAULTSPEC_BUDGET_USD": ConfigVariable(
        name="VAULTSPEC_BUDGET_USD",
        var_type=float,
        default=None,
        description="Maximum cost budget in USD",
        min_value=0.0,
    ),
    "VAULTSPEC_ALLOWED_TOOLS": ConfigVariable(
        name="VAULTSPEC_ALLOWED_TOOLS",
        var_type=list,
        default=[],
        description="Comma-separated list of allowed MCP tools",
        parser=_parse_csv_list,
    ),
    "VAULTSPEC_DISALLOWED_TOOLS": ConfigVariable(
        name="VAULTSPEC_DISALLOWED_TOOLS",
        var_type=list,
        default=[],
        description="Comma-separated list of disallowed MCP tools",
        parser=_parse_csv_list,
    ),
    "VAULTSPEC_EFFORT": ConfigVariable(
        name="VAULTSPEC_EFFORT",
        var_type=str,
        default=None,
        description="Agent effort level (high, medium, low)",
        options=["high", "medium", "low"],
    ),
    "VAULTSPEC_OUTPUT_FORMAT": ConfigVariable(
        name="VAULTSPEC_OUTPUT_FORMAT",
        var_type=str,
        default=None,
        description="Output format specification (json, text)",
        options=["json", "text"],
    ),
    "VAULTSPEC_FALLBACK_MODEL": ConfigVariable(
        name="VAULTSPEC_FALLBACK_MODEL",
        var_type=str,
        default=None,
        description="Fallback model if primary fails",
    ),
    "VAULTSPEC_INCLUDE_DIRS": ConfigVariable(
        name="VAULTSPEC_INCLUDE_DIRS",
        var_type=list,
        default=[],
        description="Comma-separated list of include directories",
        parser=_parse_csv_list,
    ),
    "VAULTSPEC_SYSTEM_PROMPT": ConfigVariable(
        name="VAULTSPEC_SYSTEM_PROMPT",
        var_type=str,
        default=None,
        description="System prompt override for agent",
    ),
    "VAULTSPEC_ROOT_DIR": ConfigVariable(
        name="VAULTSPEC_ROOT_DIR",
        var_type=Path,
        default=None,  # Defaults to cwd at load time
        description="Workspace root directory",
        parser=_parse_path,
    ),

    # MCP variables
    "VAULTSPEC_MCP_ROOT_DIR": ConfigVariable(
        name="VAULTSPEC_MCP_ROOT_DIR",
        var_type=Path,
        default=None,
        description="MCP server workspace root",
        required=True,
        parser=_parse_path,
    ),
    "VAULTSPEC_MCP_PORT": ConfigVariable(
        name="VAULTSPEC_MCP_PORT",
        var_type=int,
        default=10010,
        description="MCP server listen port",
        min_value=1024,
        max_value=65535,
    ),
    "VAULTSPEC_MCP_HOST": ConfigVariable(
        name="VAULTSPEC_MCP_HOST",
        var_type=str,
        default="0.0.0.0",
        description="MCP server bind address",
    ),
    "VAULTSPEC_MCP_TTL_SECONDS": ConfigVariable(
        name="VAULTSPEC_MCP_TTL_SECONDS",
        var_type=float,
        default=3600.0,
        description="MCP task retention period in seconds",
        min_value=60.0,
    ),

    # A2A variables
    "VAULTSPEC_A2A_DEFAULT_PORT": ConfigVariable(
        name="VAULTSPEC_A2A_DEFAULT_PORT",
        var_type=int,
        default=10010,
        description="A2A agent card default port",
        min_value=1024,
        max_value=65535,
    ),
    "VAULTSPEC_A2A_HOST": ConfigVariable(
        name="VAULTSPEC_A2A_HOST",
        var_type=str,
        default="localhost",
        description="A2A agent discovery host",
    ),

    # Storage variables
    "VAULTSPEC_DOCS_DIR": ConfigVariable(
        name="VAULTSPEC_DOCS_DIR",
        var_type=Path,
        default=".vault",
        description="Vault documentation directory",
    ),
    "VAULTSPEC_FRAMEWORK_DIR": ConfigVariable(
        name="VAULTSPEC_FRAMEWORK_DIR",
        var_type=Path,
        default=".vaultspec",
        description="Framework root directory",
    ),
    "VAULTSPEC_LANCE_DIR": ConfigVariable(
        name="VAULTSPEC_LANCE_DIR",
        var_type=Path,
        default=".lance",
        description="Vector database directory",
    ),
    "VAULTSPEC_INDEX_METADATA_FILE": ConfigVariable(
        name="VAULTSPEC_INDEX_METADATA_FILE",
        var_type=str,
        default="index_meta.json",
        description="Index metadata filename",
    ),

    # Tool directories
    "VAULTSPEC_CLAUDE_DIR": ConfigVariable(
        name="VAULTSPEC_CLAUDE_DIR",
        var_type=Path,
        default=".claude",
        description="Claude tool configuration directory",
    ),
    "VAULTSPEC_GEMINI_DIR": ConfigVariable(
        name="VAULTSPEC_GEMINI_DIR",
        var_type=Path,
        default=".gemini",
        description="Gemini tool configuration directory",
    ),
    "VAULTSPEC_ANTIGRAVITY_DIR": ConfigVariable(
        name="VAULTSPEC_ANTIGRAVITY_DIR",
        var_type=Path,
        default=".antigravity",
        description="Antigravity tool configuration directory",
    ),

    # Orchestration variables
    "VAULTSPEC_TASK_ENGINE_TTL_SECONDS": ConfigVariable(
        name="VAULTSPEC_TASK_ENGINE_TTL_SECONDS",
        var_type=float,
        default=3600.0,
        description="Task engine cleanup TTL in seconds",
        min_value=60.0,
    ),

    # RAG variables
    "VAULTSPEC_GRAPH_TTL_SECONDS": ConfigVariable(
        name="VAULTSPEC_GRAPH_TTL_SECONDS",
        var_type=float,
        default=300.0,
        description="VaultGraph cache TTL in seconds",
        min_value=1.0,
    ),
    "VAULTSPEC_EMBEDDING_BATCH_SIZE": ConfigVariable(
        name="VAULTSPEC_EMBEDDING_BATCH_SIZE",
        var_type=int,
        default=64,
        description="GPU embedding batch size",
        min_value=1,
        max_value=512,
    ),
    "VAULTSPEC_MAX_EMBED_CHARS": ConfigVariable(
        name="VAULTSPEC_MAX_EMBED_CHARS",
        var_type=int,
        default=8000,
        description="Maximum characters to embed per document",
        min_value=100,
        max_value=100000,
    ),

    # I/O variables
    "VAULTSPEC_IO_BUFFER_SIZE": ConfigVariable(
        name="VAULTSPEC_IO_BUFFER_SIZE",
        var_type=int,
        default=8192,
        description="ACP subprocess read buffer size",
        min_value=256,
        max_value=1048576,
    ),
    "VAULTSPEC_TERMINAL_OUTPUT_LIMIT": ConfigVariable(
        name="VAULTSPEC_TERMINAL_OUTPUT_LIMIT",
        var_type=int,
        default=1000000,
        description="Maximum terminal output capture in bytes",
        min_value=10000,
        max_value=100000000,
    ),

    # Reference variables (read-only, not configurable at runtime)
    "VAULTSPEC_GEMINI_MIN_VERSION_WINDOWS": ConfigVariable(
        name="VAULTSPEC_GEMINI_MIN_VERSION_WINDOWS",
        var_type=str,
        default="0.9.0",
        description="Minimum Gemini CLI version for Windows",
    ),
    "VAULTSPEC_GEMINI_MIN_VERSION_RECOMMENDED": ConfigVariable(
        name="VAULTSPEC_GEMINI_MIN_VERSION_RECOMMENDED",
        var_type=str,
        default="0.27.0",
        description="Recommended Gemini CLI version",
    ),

    # Test variables
    "VAULTSPEC_TEST_LANCE_SUFFIX": ConfigVariable(
        name="VAULTSPEC_TEST_LANCE_SUFFIX",
        var_type=str,
        default="-fast",
        description="Lance directory suffix for test isolation",
    ),
}


# ===== HELPER PARSERS =====

def _parse_csv_list(value: str) -> List[str]:
    """Parse comma-separated list, stripping whitespace."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_path(value: str) -> Path:
    """Parse path string to Path object."""
    return Path(value).expanduser().resolve()


def _parse_int(value: str) -> int:
    """Parse string to integer."""
    return int(value)


def _parse_float(value: str) -> float:
    """Parse string to float."""
    return float(value)


# ===== MAIN CONFIG DATACLASS =====

@dataclass
class VaultSpecConfig:
    """
    Centralized configuration for vaultspec.

    All configuration is loaded from environment variables with sensible defaults.
    Type validation and bounds checking are performed at load time.
    """

    # Agent configuration
    agent_mode: str = "read-write"
    max_turns: Optional[int] = None
    budget_usd: Optional[float] = None
    allowed_tools: List[str] = field(default_factory=list)
    disallowed_tools: List[str] = field(default_factory=list)
    effort: Optional[str] = None
    output_format: Optional[str] = None
    fallback_model: Optional[str] = None
    include_dirs: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    root_dir: Path = field(default_factory=lambda: Path.cwd())

    # MCP configuration
    mcp_root_dir: Optional[Path] = None
    mcp_port: int = 10010
    mcp_host: str = "0.0.0.0"
    mcp_ttl_seconds: float = 3600.0

    # A2A configuration
    a2a_default_port: int = 10010
    a2a_host: str = "localhost"

    # Storage configuration
    docs_dir: Path = field(default_factory=lambda: Path(".vault"))
    framework_dir: Path = field(default_factory=lambda: Path(".vaultspec"))
    lance_dir: Path = field(default_factory=lambda: Path(".lance"))
    index_metadata_file: str = "index_meta.json"

    # Tool directories
    claude_dir: Path = field(default_factory=lambda: Path(".claude"))
    gemini_dir: Path = field(default_factory=lambda: Path(".gemini"))
    antigravity_dir: Path = field(default_factory=lambda: Path(".antigravity"))

    # Orchestration configuration
    task_engine_ttl_seconds: float = 3600.0

    # RAG configuration
    graph_ttl_seconds: float = 300.0
    embedding_batch_size: int = 64
    max_embed_chars: int = 8000

    # I/O configuration
    io_buffer_size: int = 8192
    terminal_output_limit: int = 1000000

    # Reference configuration
    gemini_min_version_windows: str = "0.9.0"
    gemini_min_version_recommended: str = "0.27.0"

    # Test configuration
    test_lance_suffix: str = "-fast"

    @classmethod
    def from_environment(cls, override: Optional[Dict[str, Any]] = None) -> "VaultSpecConfig":
        """
        Load configuration from environment variables.

        Args:
            override: Optional dict of attribute names to values, takes precedence over env vars

        Returns:
            VaultSpecConfig instance with all values loaded and validated

        Raises:
            ValueError: If required variables are missing or invalid
        """
        kwargs = {}

        for attr_name, config_var in CONFIG_REGISTRY.items():
            # Check override first
            if override and config_var.name.lower().replace("vaultspec_", "") in override:
                kwargs[config_var.name.lower().replace("vaultspec_", "")] = \
                    override[config_var.name.lower().replace("vaultspec_", "")]
                continue

            # Read from environment
            env_value = os.environ.get(config_var.name)

            if env_value is None:
                if config_var.required:
                    raise ValueError(
                        f"Required environment variable missing: {config_var.name}"
                    )
                kwargs[config_var.name.lower().replace("vaultspec_", "")] = config_var.default
                continue

            # Parse value
            try:
                if config_var.parser:
                    parsed_value = config_var.parser(env_value)
                elif config_var.var_type == int:
                    parsed_value = int(env_value)
                elif config_var.var_type == float:
                    parsed_value = float(env_value)
                elif config_var.var_type == Path:
                    parsed_value = Path(env_value).expanduser().resolve()
                else:
                    parsed_value = env_value

                # Validate options if provided
                if config_var.options and parsed_value not in config_var.options:
                    raise ValueError(
                        f"Invalid value for {config_var.name}: {parsed_value}. "
                        f"Must be one of: {', '.join(config_var.options)}"
                    )

                # Validate min/max if provided
                if config_var.min_value is not None and parsed_value < config_var.min_value:
                    raise ValueError(
                        f"Value for {config_var.name} ({parsed_value}) below minimum ({config_var.min_value})"
                    )
                if config_var.max_value is not None and parsed_value > config_var.max_value:
                    raise ValueError(
                        f"Value for {config_var.name} ({parsed_value}) exceeds maximum ({config_var.max_value})"
                    )

                kwargs[config_var.name.lower().replace("vaultspec_", "")] = parsed_value
                logger.debug(f"Loaded {config_var.name} = {parsed_value}")


            except (ValueError, TypeError) as e:
                logger.error(
                    f"Failed to parse {config_var.name}={env_value}: {e}. Using default: {config_var.default}"
                )

                kwargs[config_var.name.lower().replace("vaultspec_", "")] = config_var.default


        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""


        return asdict(self)


    def validate(self) -> None:
        """Validate all configuration after loading."""
        if self.mcp_root_dir is None:

            raise ValueError("MCP root directory is required")





        logger.info("Configuration validated successfully")


# ===== GLOBAL INSTANCE =====




_config: Optional[VaultSpecConfig] = None




def get_config(override: Optional[Dict[str, Any]] = None) -> VaultSpecConfig:
    """

    Get the global configuration instance.





    Creates one on first call, caches it for subsequent calls.

    Pass override dict to create a new instance for testing.

    """
    global _config




    if override is not None:


        # Testing: create fresh instance with overrides

        return VaultSpecConfig.from_environment(override)


    if _config is None:

        _config = VaultSpecConfig.from_environment()





    return _config




def reset_config() -> None:

    """Reset the global config instance (mainly for testing)."""


    global _config


    _config = None

```

### Key Design Features

#### 1. Import Strategy

- **No circular dependencies**: `config.py` imports only stdlib + third-party (logging, pathlib, dataclasses, enum)

- **Lazy loading**: Global instance created on first access

- **Test-friendly**: `reset_config()` and override dict support

#### 2. Default Precedence

```
Constructor param (override dict)

  → Environment variable

    → CONFIG_REGISTRY default

      → Python dataclass default
```

#### 3. Validation Patterns

- **Type checking**: Parser functions handle str→int/float/Path conversion
- **Range validation**: Min/max bounds for numeric values

- **Option validation**: Enum-like values must be in allowed list

- **Required validation**: Some vars must be set or raise ValueError

#### 4. Error Handling

- **Graceful degradation**: Invalid values logged as WARNING, falls back to default
- **Fail-fast for required**: Missing required vars raise ValueError immediately
- **Comprehensive logging**: All loads and errors logged for auditability

#### 5. Testing Support

```python

# Override via dict (no os.environ changes needed)

config = get_config(override={
    "mcp_port": 9999,
    "embedding_batch_size": 32
})

# Reset between tests

reset_config()


# Or use pytest fixture
@pytest.fixture

def config():

    config = get_config()
    yield config
    reset_config()
```

---

## Test Constants Consolidation

### Current Duplication Issue

The same constant `GPU_FAST_CORPUS_STEMS` is defined in **two places**:

- `.vaultspec/tests/conftest.py` (lines 37-58)
- `.vaultspec/lib/src/rag/tests/conftest.py` (lines 31-47)

This creates maintenance burden and risk of drift.

### Proposed Solution: `.vaultspec/tests/constants.py`

```python
"""

Centralized test constants for vaultspec test suite.

This module consolidates all test-only constants that were previously
scattered across multiple conftest.py files.
"""

from pathlib import Path

from typing import FrozenSet


# Project root and test fixture paths

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

TEST_PROJECT = PROJECT_ROOT / "test-project"
TEST_VAULT = TEST_PROJECT / ".vault"


# RAG test corpus (representative subset for fast tests)
GPU_FAST_CORPUS_STEMS: FrozenSet[str] = frozenset({
    "adr/2025-12-05-gemini-provider-acp-integration",
    "adr/2026-01-10-vector-store-incremental-indexing",
    "adr/2026-02-07-task-engine-phase-2-async",
    "exec/2025-11-15-initial-vaultspec-setup",


    "exec/2025-11-22-claude-bridge-phase-1",

    "exec/2026-01-05-rag-integration-phase-1",
    "exec/2026-02-01-subagent-mcp-phase-2",

    "plan/2025-12-01-q1-roadmap",


    "plan/2026-01-01-implementation-phases",
    "reference/agentic-patterns",

    "reference/python-async-patterns",
    "research/2026-01-15-lance-db-performance",
    "research/2026-02-07-a2a-research",
})


# Detection flags
try:


    import torch

    HAS_CUDA = torch.cuda.is_available()
except ImportError:

    HAS_CUDA = False



HAS_RAG = HAS_CUDA  # RAG tests only run on GPU systems




# Lance test directory suffixes (for test isolation)
LANCE_SUFFIX_FAST = "-fast"      # Fast corpus subset
LANCE_SUFFIX_FULL = "-full"      # Full corpus (slow tests)

LANCE_SUFFIX_UNIT = "-fast-unit" # Unit test isolation






# Test port ranges (safe ranges that don't conflict)
TEST_PORT_BASE = 10001

TEST_PORT_A2A_BASE = 10020


TEST_PORT_SUBAGENT = 10010  # MCP server default




# Test timeouts (seconds)
TIMEOUT_QUICK_TEST = 15

TIMEOUT_INTEGRATION_TEST = 120
TIMEOUT_E2E_TEST = 180

TIMEOUT_CLAUDE_E2E = 60
TIMEOUT_GEMINI_E2E = 60


TIMEOUT_MCP_E2E = 180


TIMEOUT_FULL_CYCLE = 180
TIMEOUT_A2A_E2E = 300




# Test delays (sleep values in seconds)

DELAY_SHORT = 0.2


DELAY_MEDIUM = 0.3
DELAY_LONG = 1.0


# ACP test helpers timeouts
ACP_TIMEOUT_READ = 10.0

ACP_TIMEOUT_MESSAGE = 30.0
```

### Updated conftest.py Files

**`.vaultspec/tests/conftest.py`:**

```python

# BEFORE (lines 37-58):



GPU_FAST_CORPUS_STEMS = frozenset({
    "adr/2025-12-05-gemini-provider-acp-integration",
    # ... 12 more items

})


# AFTER:
from tests.constants import GPU_FAST_CORPUS_STEMS, HAS_RAG, TEST_PROJECT




```

**`.vaultspec/lib/src/rag/tests/conftest.py`:**

```python
# BEFORE (lines 31-47):

GPU_FAST_CORPUS_STEMS = frozenset({

    "adr/2025-12-05-gemini-provider-acp-integration",




    # ... 12 more items
})


# AFTER:
from tests.constants import GPU_FAST_CORPUS_STEMS, LANCE_SUFFIX_FAST, LANCE_SUFFIX_FULL, LANCE_SUFFIX_UNIT

```

### Benefits

- **Single source of truth** for test constants
- **Easy to audit** all test configuration in one place
- **Clear intent** (constants named for their purpose)
- **Fixtures can reference** constants consistently across test suite

---

## Implementation Roadmap (4 Phases)

### Phase 1: Foundation (Week 1)

**Goal**: Create config.py infrastructure and enable gradual migration.

#### Deliverables

1. Create `.vaultspec/lib/src/core/config.py` with:

   - `VaultSpecConfig` dataclass
   - `CONFIG_REGISTRY` with all 33 variables
   - Helper functions for parsing

   - `get_config()` and `reset_config()` functions

2. Create `.vaultspec/tests/constants.py` with consolidated test constants

3. Create `.env.example` at project root with all Tier 1-2 variables:

   ```bash
   # .env.example
   # Core Configuration

   VAULTSPEC_ROOT_DIR=.
   VAULTSPEC_DOCS_DIR=.vault

   VAULTSPEC_FRAMEWORK_DIR=.vaultspec






   # MCP Server

   VAULTSPEC_MCP_ROOT_DIR=.

   VAULTSPEC_MCP_PORT=10010
   VAULTSPEC_MCP_HOST=0.0.0.0
   VAULTSPEC_MCP_TTL_SECONDS=3600.0


   # Agent Configuration
   VAULTSPEC_AGENT_MODE=read-write

   # VAULTSPEC_MAX_TURNS=          # Optional

   # VAULTSPEC_BUDGET_USD=         # Optional




   # VAULTSPEC_SYSTEM_PROMPT=      # Optional


   # ... rest of variables
   ```

4. Create ADR documenting the standardization decision (this document)

#### Files Modified

- Created: `.vaultspec/lib/src/core/config.py` (~250 lines)

- Created: `.vaultspec/lib/src/core/__init__.py`

- Created: `.vaultspec/tests/constants.py` (~60 lines)
- Modified: `.vaultspec/tests/conftest.py` (import GPU_FAST_CORPUS_STEMS from constants)
- Modified: `.vaultspec/lib/src/rag/tests/conftest.py` (import constants)

- Created: `.env.example` (~40 lines)

#### Validation Criteria

- ✓ `config.py` loads all 33 variables successfully

- ✓ Defaults match current hardcoded values

- ✓ Type conversion works for all types (int, float, Path, CSV list)

- ✓ Validation catches out-of-range values
- ✓ Test constants consolidated without duplication
- ✓ Old conftest.py files import from new constants module

#### Estimated Effort

- 4-6 hours development

- 2 hours testing
- 1 hour documentation

---

### Phase 2: Migration (Week 2)

**Goal**: Replace all 38+ hardcoded constants with env var reads.

#### Migration by Category

##### A. Directory Paths (7 files)

**`.vaultspec/lib/src/rag/store.py` (Line 122)**

```python
# BEFORE:
self.db_path = self.root_dir / ".lance"


# AFTER:

from core.config import get_config
cfg = get_config()

self.db_path = self.root_dir / cfg.lance_dir
```

**`.vaultspec/lib/src/vault/models.py` (Line 106)**

```python
# BEFORE:
class VaultConstants:


    DOCS_DIR = ".vault"


# AFTER:
class VaultConstants:
    @property

    def DOCS_DIR(self):




        from core.config import get_config
        return get_config().docs_dir

```

**`.vaultspec/scripts/cli.py` (Lines 145-190)**

```python
# BEFORE:

RULES_SRC_DIR = root / ".vaultspec" / "rules"

AGENTS_SRC_DIR = root / ".vaultspec" / "agents"

# ... etc







# AFTER:


from core.config import get_config

cfg = get_config()
RULES_SRC_DIR = root / cfg.framework_dir / "rules"
AGENTS_SRC_DIR = root / cfg.framework_dir / "agents"
# ... etc


```

##### B. Port Numbers (5 files)

**`.vaultspec/lib/src/protocol/a2a/agent_card.py` (Lines 9-10)**

```python





# BEFORE:
def agent_card_from_definition(..., host: str = "localhost", port: int = 10010):


# AFTER:
def agent_card_from_definition(..., host: str = None, port: int = None):
    from core.config import get_config
    cfg = get_config()
    host = host or cfg.a2a_host

    port = port or cfg.a2a_default_port

```

**`.vaultspec/lib/src/protocol/a2a/discovery.py` (Lines 47-48)**

```python


# BEFORE:

def write_agent_discovery(..., host: str = "localhost", port: int = 10010):

# AFTER:

def write_agent_discovery(..., host: str = None, port: int = None):


    from core.config import get_config
    cfg = get_config()


    host = host or cfg.a2a_host
    port = port or cfg.a2a_default_port

```

**`.vaultspec/scripts/subagent.py` (Line 181)**

```python
# BEFORE:

uvicorn.run(app, host="0.0.0.0", port=port)


# AFTER:
from core.config import get_config
cfg = get_config()
host = args.host or cfg.mcp_host


uvicorn.run(app, host=host, port=port)

```

##### C. Timeouts/TTLs (4 files)

**`.vaultspec/lib/src/rag/search.py` (Line 163)**

```python

# BEFORE:

def __init__(self, ..., graph_ttl_seconds: float = 300.0):


# AFTER:


def __init__(self, ..., graph_ttl_seconds: float = None):

    from core.config import get_config


    cfg = get_config()
    self._graph_ttl_seconds = graph_ttl_seconds or cfg.graph_ttl_seconds

```

**`.vaultspec/lib/src/orchestration/task_engine.py` (Line 231)**

```python


# BEFORE:
def __init__(self, ..., ttl_seconds: float = 3600.0):




# AFTER:****
def __init__(self, ..., ttl_seconds: float = None):
    from core.config import get_config
    cfg = get_config()
    self._ttl_seconds = ttl_seconds or cfg.task_engine_ttl_seconds



```

##### D. Batch & Buffer Sizes (4 files)

**`.vaultspec/lib/src/rag/embeddings.py` (Lines 95, 101)**

```python


# BEFORE:
DEFAULT_BATCH_SIZE = 64

MAX_EMBED_CHARS = 8000



# AFTER:

def get_batch_size():


    from core.config import get_config

    return get_config().embedding_batch_size



def get_max_embed_chars():


    from core.config import get_config
    return get_config().max_embed_chars
```

**`.vaultspec/lib/src/protocol/acp/client.py` (Lines 334, 340)**

```python
# BEFORE:

output_byte_limit or 1_000_000


chunk = await proc.stdout.read(8192)***


# AFTER:
from core.config import get_config
cfg = get_config()




output_byte_limit or cfg.terminal_output_limit

chunk = await proc.stdout.read(cfg.io_buffer_size)

```

#### Files Modified

- `6` RAG/storage files
- `5` Protocol/A2A files

- `3` Orchestration files
- `2` CLI scripts

Total: **16 files**, ~200 lines of changes

#### Validation Criteria

- ✓ All hardcoded constants replaced with config reads

- ✓ Defaults in config.py match original hardcoded values

- ✓ No behavioral change (all tests pass)
- ✓ Env vars are optional (graceful defaults)

- ✓ Logging shows which config values were loaded

#### Estimated Effort

- 8-10 hours development
- 4 hours testing

- 2 hours validation/debugging

---

### Phase 3: Test Infrastructure (Wee**3)**

**Goal**: Centralize test constants and create unified fixture library.

#### Deliverables

1. **Test Fixture Library** (`.vaultspec/tests/fixtures/config.py`):

```python
"""Pytest fixtures for configuration override."""






import pytest
from core.config import get_config, reset_config, VaultSpecConfig





@pytest.fixture

def vaultspec_config():



    """Get fresh config instance for test."""
    config = get_config()

    yield config
    reset_config()







@pytest.fixture
def config_override():



    """Factory fixture for creating config with overrides."""
    def _make_config(**overrides):
        reset_config()
        return get_config(override=overrides)

    return _make_config




@pytest.fixture
def with_custom_port(config_override):

    """Provide config with custom MCP port."""



    return config_override(mcp_port=1**99)**




@pytest.fixture
def with_small_batch(config_override):





    """Provide config with small embedding batch for testing."""

    return config_override(embedding_batch_size=8)
```

2. **Update all conftest.py files** to use constants and fixtures:

```python




# Old pattern:
GPU_FAST_CORPUS_STEMS = frozenset({...})  # Duplicated
HAS_RAG = check_cuda()




# New pattern:

from tests.constants import GPU_FAST_CORPUS_STEMS, HAS_RAG



from tests.fixtures.config import vaultspec_config, config_override
```

3. **Create pytest.ini configuration** for timeouts:

```ini

[pytest]


timeout = 60
timeout_method = thread




markers =
    timeout(seconds): timeout for this test
    quick: runs in < 15 seconds


    integration: requires external services
    e2e: full end-to-end test


```

#### Files Modified

- Created: `.vaultspec/tests/fixtures/__init__.py`

- Created: `.vaultspec/tests/fixtures**onfi**py` (~60 lines)
- Modified: All `conftest.py` files (import from constants/fixtures)

- Created: `pytest.ini` (~20 lines)

#### Validation Criteria

- ✓ All test constants consolidated in `tests/constants.py`

- ✓ No duplication of constants across conftest files
- ✓ Config override fixtures work correctly
- ✓ All existing tests pass without modification
- ✓ New tests can use `config_override` fixture

#### Estimated Effort

- 4-6 hours development
- 3 hours testing
- 1 hour documentation

---

### Phase 4: Documentation & Validation (Week 4)

**Goal**: Document configuration system and validate migration.

#### Deliverables

1. **Update README.md** with env var section:

```markdown
## Configuration




vaultspec uses environment variables for configuration. See `.env.example`
for all available options.



### Quick Start



```bash
# Copy example configuration
cp .env.example .env.local

# Edit for your environment



vim .env.local****


# Load configuration


export $(cat .env.local | xargs)

# Run application




python .vaultspec/scripts/cli.py

```

### Environment Variables

- **Agent**: `VAULTSPEC_AGENT_MODE`, `VAULTSPEC_MAX_TURNS`, etc.
- **MCP**: `VAULTSPEC_MCP_PORT`, `VAULTSPEC_MCP_HOST`, etc.

- **Storage**: `VAULTSPEC_LANCE_DIR`, `VAULTSPEC_DOCS_DIR`, etc.

- **RAG**: `VAULTSPEC_EMBEDDING_BATCH_SIZE`, `VAULTSPEC_MAX_EMBED_CHARS`

See `.env.example` for complete list with descriptions.

```




2. **Create config reference documentation** (`.vault/reference/environment-variables.md`):



   - Description of each variable
   - Use cases and examples

   - Common configurations (development, CI/CD, production)
   - Troubleshooting guide




3. **Create validation checklist**:

   ```markdown
   # Configuration Validatio Checklist


   - [ ] All 33 env vars defined in CONFIG_REGISTRY




   - [ ] All 38+ hardcoded constants migrated to env vars
   - [ ] Defaults in config.py match original hardcoded values
   - [ ] No direct os.environ calls outside config.py
   - [ ] Test constants consolidated in tests/constants.py


   - [ ] All tests pass with new config system
   - [ ] CI/CD configuration updated to use env vars


   - [ ] .env.example documents all Tier 1-2 variables

   - [ ] No circular dependencies in import chain
   - [ ] Performance baseline verified (no regression)
   ```

4. **Create deployment guide** (`.vau**/pla**2026-02-16-config-deployment.md`):
   - How to set env vars in Docker

   - How to set env vars in Kubernetes

   - How to set env vars in GitHub Actions
   - How to set env vars in local development

#### Files Created/Modified

- Modified: `README.md` (new section ~50 lines)
- Created: `.vault/reference/environment-variables.md` (~200 lines)

- Created: `.vault/plan/2026-02-16-config-deployment.md` (~150 lines)
- Created: `VALIDATION_CHECKLIST.md` (~100 lines)

#### Validation Criteria

- ✓ All documentation is up-to-date

- ✓ `.env.example` matches CONFIG_REGISTRY
- ✓ Examples work as documented

- ✓ Deployment guide tested in test environment

- ✓ CI/CD pipeline uses env vars correctly

#### Estimated Effort

- 3-4 hours documentation

- 2 hours testing/validation
- 1 hour review/refinement

---

### Phase 5: Deprecation & Cleanup (Optional, Week 5+)

**Goal**: Remove legacy VS_*variables in favor of VAULTSPEC_* prefix (long-term).

#### Strategy

- Phase 1-4 use `VS_*` variables as aliases for `VAULTSPEC_*`
- Add deprecation warnings when `VS_*` variables are used
- Document migration path for users
- Remove `VS_*` support in next major version (or 6 months)

#### Implementation

```python

# In config.py:
def _load_legacy_vs_var(var_name: str):
    """Load legacy VS_* variable with deprecation warning."""
    legacy_name = f"VS_{var_name[len('VAULTSPEC_'):]}"



    value = os.environ.get(legacy_nam****
    if value:


        logger.warning(


            f"Using legacy {legacy_name}. Please use {var_name} instead. "
            "Legacy variables will be removed in vaultspec 2.0"
        )





    return value
```

---

## Migration Strategy by Category

### Category 1: Agent Configuration (7 variables)

| Variable | Files | Current Pattern | Proposed Change | Risk | Rollback |

|---|---|---|---|---|---|
| `VAULTSPEC_AGENT_MODE` | claude_bridge.py | `os.environ.get()` with default | Read from config | LOW | Revert to direct env read |

| `VAULTSPEC_MAX_TURNS` | claude_bridge.py | `os.environ[]` with try/except | Read from config | LOW | Revert to direct env read |

| `VAULTSPEC_BUDGET_USD` | claude_bridge.py | `os.environ[]` with try/except | Read from config | LOW | Revert to direct env read |
| `VAULTSPEC_ALLOWED_TOOLS` | claude_bridge.py | `.split(",")` | Use config parser | MEDIUM | Revert to direct parsing |

| `VAULTSPEC_DISALLOWED_TOOLS` | claude_bridge.py | `.split(",")` | Use config parser | MEDIUM | Revert to direct parsing |

| `VAULTSPEC_EFFORT` | claude_bridge.py | `os.environ.get()` | Read from config | LOW | Revert to direct env read |
| `VAULTSPEC_SYSTEM_PROMPT` | claude_bridge.py, tests | `os.environ.get()` | Read from config | LOW | Revert to direct env read |

**Migration Steps:**

1. Update `claude_bridge.py` to use `get_config()` instead of `os.environ` reads
2. Verify all parameter precedence still works (param > env > default)

3. Update tests to verify defaults work
4. Run test suite

**Affected Files:**

- `.vaultspec/lib/src/protocol/acp/claude_bridge.py`
- `.vaultspec/lib/src/protocol/tests/test_providers.py`

---

### Category 2: MCP Server (4 variables)

| Variable | Files | Current Pattern | Proposed Change | Risk | Rollback |
|---|---|---|---|---|---|
| `VAULTSPEC_MCP_ROOT_DIR` | server.py | `os.environ.get()` required | Already env-configurable | NONE | No change needed |

| `VAULTSPEC_MCP_PORT` | subagent.py | Hardcoded 10010 | Add env var fallback | MEDIUM | Hardcode default |

| `VAULTSPEC_MCP_HOST` | subagent.py | Hardcoded "0.0.0.0" | Add env var fallback | LOW | Hardcode default |
| `VAULTSPEC_MCP_TTL_SECONDS` | server.py | Already env-configurable | Already env-configurable | NONE | No change needed |

**Migration Steps:**

1. Add `mcp_port` and `mcp_host` to c**fig.** registry
2. Update `subagent.py` to read from config

3. Verify argparse still overrides config

4. Update tests

**Affected Files:**

- `.vaultspec/scripts/subagent.py`
- `.vaultspec/lib/src/subagent_server/server.py`

---

### Category 3: Storage & Directory Paths (9 variables)

| Variable | Files | Current Pattern | Proposed Change | Risk | Rollback |

|---|---|---|---|---|---|
| `VAULTSPEC_DOCS_DIR` | 15 files | Hardcoded ".vault" | Use config property | HIGH | Search/replace back |

| `VAULTSPEC_FRAMEWORK_DIR` | cli.py | Hardcoded ".vaultspec" | Use config property | MEDIUM | Search/replace back |
| `VAULTSPEC_LANCE_DIR` | store.py | Hardcoded ".lance" | Use config property | MEDIUM | Search/replace back |

| `VAULTSPEC_CLAUDE_DIR` | cli.py | Hardcoded ".claude" | Use config property | LOW | Search/replace back |

| `VAULTSPEC_GEMINI_DIR` | cli.py, discovery.py | Hardcoded ".gemini" | Use config property | LOW | Search/replace back |
| `VAULTSPEC_ANTIGRAVITY_DIR` | cli.py | Hardcoded ".antigravity" | Use config property | LOW | Search/replace back |

| `VAULTSPEC_INDEX_METADATA_FILE` | indexer.py | Hardcoded filename | Use config property | LOW | Hardcode back |

**Migration Steps:**

1. Add all directory variables to config registry
2. Update path construction throughout codebase
3. Verify multi-project layouts work
4. Test with different `VAULTSPEC_LANCE_DIR` values
5. Run full test suite

**Affected Files:**

- `.vaultspec/lib/src/rag/store.py`
- `.vaultspec/lib/src/rag/indexer.py`
- `.vaultspec/lib/src/vault/models.py`
- `.vaultspec/scripts/cli.py`
- `.vaultspec/lib/src/protocol/a2a/discovery.py`
- 10+ other files with path references

---

### Category 4: RAG/Embeddings (3 variables)

| Variable | Files | Current Pattern | Proposed Change | Risk | Rollback |
|---|---|---|---|---|---|

| `VAULTSPEC_EMBEDDING_BATCH_SIZE` | embeddings.py | Hardcoded 64 | Add env var fallback | MEDIUM | Hardcode back |

| `VAULTSPEC_MAX_EMBED_CHARS` | embeddings.py | Hardcoded 8000 | Add env var fallback | MEDIUM | Hardcode back |
| `VAULTSPEC_GRAPH_TTL_SECONDS` | search.py | Hardcoded 300.0 | Add env var fallback | LOW | Hardcode back |

**Migration Steps:**

1. Add getter functions in embeddings.py
2. Add env var fallback in search.py **init**
3. Test with different batch sizes (8, 16, 32, 64, 128)

4. Verify performance on different GPUs

5. Run full embedding test suite

**Affected Files:**

- `.vaultspec/lib/src/rag/embeddings.py`

- `.vaultspec/lib/src/rag/search.py`
- `.vaultspec/lib/src/rag/tests/conftest.py`

---

### Category 5: I/O & Buffers (2 variables)

| Variable | Files | Current Pattern | Proposed Change | Risk | Rollback |

|---|---|---|---|---|---|
| `VAULTSPEC_IO_BUFFER_SIZE` | client.py | Hardcoded 8192 | Add env var fallback | LOW | Hardcode back |

| `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` | client.py | Hardcoded 1_000_000 | Add env var fallback | LOW | Hardcode back |

**Migration Steps:**

1. Add env var reads to ACP client
2. Test with different buffer sizes

3. Test high-throughput scenarios

4. Run integration tests

**Affected Files:**

- `.vaultspec/lib/src/protocol/acp/client.py`

---

### Category 6: Port Numbers & Network (4 variables)

| Variable | Files | Current Pattern | Proposed Change | Risk | Rollback |
|---|---|---|---|---|---|
| `VAULTSPEC_A2A_DEFAULT_PORT` | agent_card.py | Function default 10010 | Add env var fallback | MEDIUM | Revert to default |
| `VAULTSPEC_A2A_HOST` | discovery.py | Function default "localhost" | Add env var fallback | MEDIUM | Revert to default |
| `VAULTSPEC_MCP_PORT` | subagent.py | Hardcoded 10010 | Add env var fallback | MEDIUM | Hardcode back |
| `VAULTSPEC_MCP_HOST` | subagent.py | Hardcoded "0.0.0.0" | Add env var fallback | LOW | Hardcode back |

**Migration Steps:**

1. Update function signatures to use config defaults
2. Test port conflict detection
3. Test with external host addresses
4. Verify discovery endpoint generation

5. Run full A2A test suite

**Affected Files:**

- `.vaultspec/lib/src/protocol/a2a/agent_card.py`

- `.vaultspec/lib/src/protocol/a2a/discovery.py`
- `.vaultspec/scripts/subagent.py`

---

## Naming Convention Standards

### Prefix Requirements

- **Primary**: `VAULTSPEC_` (all new variables)

- **Legacy**: `VS_*` (existing, for backward compatibility during transition)
- **Standard Library**: `EDITOR`, `PYTHONPATH`, etc. (use as-is)
- **Third-party**: Tool-specific (e.g., `GEMINI_SYSTEM_MD`)

### Grouping Hierarchy

```
VAULTSPEC_{CATEGORY}_{ITEM}

Examples:

- VAULTSPEC_AGENT_MODE (category: Agent, item: Mode)
- VAULTSPEC_MCP_PORT (category: MCP, item: Port)

- VAULTSPEC_EMBEDDING_BATCH_SIZE (category: Embedding, item: Batch Size)
```

### Format Conventions

| Type | Convention | Example |
|------|-----------|---------|

| **Boolean** | `_ENABLED`, `_DISABLED` | `VAULTSPEC_DEBUG_ENABLED=true` |
| **Numeric** | Bare number | `VAULTSPEC_MCP_PORT=10010` |
| **Decimal** | Decimal notation | `VAULTSPEC_TIMEOUT_SECONDS=30.5` |
| **Path** | Absolute or relative | `VAULTSPEC_LANCE_DIR=.lance` |

| **List** | Comma-separated | `VAULTSPEC_ALLOWED_TOOLS=tool1,tool2,tool3` |

| **Enum** | Lowercase option | `VAULTSPEC_AGENT_MODE=read-write` |
| **String** | Any value | `VAULTSPEC_SYSTEM_PROMPT=...` |

### Category Names

```
Agent       - Agent behavior and constraints
MCP         - MCP server configuration
A2A         - Agent-to-Agent protocol
Storage     - Database and file storage paths



Tools       - Tool-specific directories
Orchestration - Task engine and workflow
RAG         - Retrieval-Augmented Generation
I/O         - Input/Output buffers and limits
Test        - Test-specific configuration
Reference   - Reference values (read-only)
Debug       - Debugging and logging
```

### Reserved Names

```
VAULTSPEC_DEBUG_*       - Debug/logging features
VAULTSPEC_TEST_*        - Test-only configuration
VAULTSPEC_INTERNAL_*    - Internal-only variables


VAULTSPEC_DEPRECATED_*  - Deprecated variables (for transition)
```

---

## Backwards Compatibility & Deprecation

### Transition Strategy

**Phase 1 (Weeks 1-2)**:

- Introduce new `VAULTSPEC_*` variables in parallel with `VS_*`
- Both work; no warnings
- Config system reads both

**Phase 2 (Weeks 3-4)**:

- Add deprecation warnings when `VS_*` variables are used
- Log: `"Variable VS_VAR is deprecated. Use VAULTSPEC_VAR instead."`
- Documentation guides users to migrate

**Phase 3 (Next major version or 6 months)**:

- Remove `VS_*` support
- Only `VAULTSPEC_*` variables work
- Clear error message if `VS_*` is used

### Migration Path for Users

**For local development:**

```bash
# Old approach (still works):




export VS_ROOT_DIR=/my/project
export VS_AGENT_MODE=read-write

# New approach (recommended):
export VAULTSPEC_ROOT_DIR=/my/project

export VAULTSPEC_AGENT_MODE=read-write
```

**For Docker deployments:**

```dockerfile

# Old approach:
ENV VS_ROOT_DIR=/app
ENV VS_AGENT_MODE=read-write

# New approach:
ENV VAULTSPEC_ROOT_DIR=/app
ENV VAULTSPEC_AGENT_MODE=read-write
```

**For CI/CD:**

```yaml
# Old approach:
env:
  VS_ROOT_DIR: ${{ github.workspace }}
  VS_AGENT_MODE: read-write

# New approach:
env:
  VAULTSPEC_ROOT_DIR: ${{ github.workspace }}
  VAULTSPEC_AGENT_MODE: read-write

```

### Documentation of Deprecation

In `.vault/reference/environment-variables.md`:

```markdown
## Deprecated Variables

The following `VS_*` variables are deprecated and will be removed in vaultspec 2.0.
Please migrate to the new `VAULTSPEC_*` names:


| Old Name | New Name | Migration |
|----------|----------|-----------|
| VS_ROOT_DIR | VAULTSPEC_ROOT_DIR | Same value |
| VS_AGENT_MODE | VAULTSPEC_AGENT_MODE | Same value |
| ... | ... | ... |

**Timeline:**
- v1.5+: Both work, warnings logged

- v2.0: Only VAULTSPEC_* supported
```

---

## Testing & Validation Strategy

### Test Coverage Matrix

| Test Type | Scope | Approach | Files |
|-----------|-------|----------|-------|
| **Unit Tests** | Config parsing | Test each parser function | `tests/test_config.py` |
| **Integration Tests** | Config loading | Test CONFIG_REGISTRY loads | `tests/test_config_integration.py` |
| **E2E Tests** | Config in use | Verify behavior changes with config | Existing test suite |

| **Deployment Tests** | CI/CD | Test env vars in GitHub Actions | `.github/workflows/test.yml` |

### Validation Patterns

#### 1. Type Safety Tests

```python
def test_config_int_parsing():
    """Verify integer config values parse correctly."""
    os.environ["VAULTSPEC_MCP_PORT"] = "10010"
    config = VaultSpecConfig.from_environment()

    assert config.mcp_port == 10010
    assert isinstance(config.mcp_port, int)

def test_config_float_parsing():
    """Verify float config values parse correctly."""
    os.environ["VAULTSPEC_MCP_TTL_SECONDS"] = "3600.5"

    config = VaultSpecConfig.from_environment()
    assert config.mcp_ttl_seconds == 3600.5

def test_config_path_parsing():
    """Verify Path config values resolve correctly."""
    os.environ["VAULTSPEC_LANCE_DIR"] = ".lance"
    config = VaultSpecConfig.from_environment()
    assert isinstance(config.lance_dir, Path)
```

#### 2. Validation Tests

```python
def test_config_validates_port_range():
    """Verify port validation bounds."""
    os.environ["VAULTSPEC_MCP_PORT"] = "999"  # Below 1024
    with pytest.raises(ValueError):
        VaultSpecConfig.from_environment()

def test_config_validates_enum_values():
    """Verify enum validation."""
    os.environ["VAULTSPEC_AGENT_MODE"] = "invalid-mode"

    with pytest.raises(ValueError):
        VaultSpecConfig.from_environment()
```

#### 3. Backward Compatibility Tests

```python
def test_legacy_vs_variables_still_work():
    """Verify VS_* variables still load (with deprecation)."""
    os.environ["VS_AGENT_MODE"] = "read-only"
    # Should still work during transition
    config = VaultSpecConfig.from_environment()

    assert config.agent_mode == "read-only"

def test_new_vaultspec_variables_take_precedence():
    """Verify VAULTSPEC_* takes precedence over VS_*."""
    os.environ["VS_AGENT_MODE"] = "read-only"
    os.environ["VAULTSPEC_AGENT_MODE"] = "read-write"
    config = VaultSpecConfig.from_environment()
    assert config.agent_mode == "read-write"
```

#### 4. Integration Tests

```python
def test_config_disables_hardcoded_paths():
    """Verify config overrides hardcoded paths."""
    os.environ["VAULTSPEC_LANCE_DIR"] = "/custom/lance"
    config = get_config()
    # Create store with config
    store = VaultStore(root_dir=Path("."), config=config)

    assert store.db_path == Path("/custom/lance").resolve()

def test_config_enables_port_override():
    """Verify port configuration affects server."""
    os.environ["VAULTSPEC_MCP_PORT"] = "9999"

    config = get_config()
    # Verify server would bind to new port
    assert config.mcp_port == 9999
```

#### 5. Test Isolation

```python
@pytest.fixture
def clean_config():
    """Ensure config is reset between tests."""
    reset_config()

    yield
    reset_config()

def test_config_isolation_1(clean_config):
    os.environ["VAULTSPEC_MCP_PORT"] = "10010"
    config1 = get_config()

    assert config1.mcp_port == 10010

def test_config_isolation_2(clean_config):
    # Port should be default, not 10010 from previous test
    config2 = get_config()
    assert config2.mcp_port == 10010  # Default value
```

### Regression Test Checklist

- [ ] All existing tests pass with new config system
- [ ] Performance baselines unchanged (embedding time, search latency)
- [ ] Memory usage unchanged
- [ ] No new circular dependencies
- [ ] Test suite runs in same time or faster
- [ ] CI/CD pipeline passes all checks
- [ ] Deployment scripts work with new env vars

---

## Success Criteria & Metrics

### Primary Success Criteria

1. **All Configuration Centralized**
   - [x] All 33 env vars in CONFIG_REGISTRY
   - [x] All 38+ hardcoded constants mapped to env vars
   - [x] No scattered os.environ calls outside config.py

2. **Type Safety Enforced**
   - [x] All values validated at load time
   - [x] Invalid values produce clear error messages
   - [x] Type conversions handle edge cases

3. **Testing Infrastructure Unified**
   - [x] All test constants in tests/constants.py
   - [x] No duplication across conftest files
   - [x] Config override fixtures work consistently

4. **Documentation Complete**
   - [x] .env.example documents all Tier 1-2 variables
   - [x] README has configuration section
   - [x] Deployment guide covers common scenarios

### Metrics to Track

| Metric | Current | Target | Phase |
|--------|---------|--------|-------|
| Config variables centralized | 0% | 100% | 1 |
| Hardcoded constants eliminated | 0% | 100% | 2 |
| Test constants deduplicated | 0% | 100% | 3 |
| Documentation completeness | 0% | 100% | 4 |
| Circular dependencies | 0 | 0 | All |

| Test suite pass rate | ~95% | 100% | All |

### Quality Assurance Checkpoints

**After Phase 1:**

- ✓ config.py loads all 33 variables
- ✓ Defaults match current hardcoded values
- ✓ Type conversion works for all types
- ✓ No regressions in existing code

**After Phase 2:**

- ✓ All hardcoded constants replaced
- ✓ No behavioral changes (test suite passes)
- ✓ Env vars are optional with sensible defaults
- ✓ Logging shows config loading process

**After Phase 3:**

- ✓ Test constants consolidated
- ✓ Config override fixtures working
- ✓ All conftest files use unified constants
- ✓ Test suite isolation improved

**After Phase 4:**

- ✓ Documentation is complete and accurate
- ✓ Examples are tested and working
- ✓ Deployment guide used in practice
- ✓ Team feedback incorporated

---

## Implementation Checklist

### Phase 1: Foundation

- [ ] Create `.vaultspec/lib/src/core/config.py` with VaultSpecConfig
- [ ] Create `.vaultspec/lib/src/core/__init__.py`
- [ ] Create `.vaultspec/tests/constants.py` with consolidated test constants
- [ ] Create `.env.example` with all Tier 1-2 variables
- [ ] Create ADR document (this file)
- [ ] Update conftest.py files to import from constants
- [ ] Test config loading with all 33 variables
- [ ] Test type conversions work correctly
- [ ] Test validation catches invalid values
- [ ] Commit Phase 1 changes with clear message

### Phase 2: Migration

- [ ] Create migration script to find all hardcoded constants
- [ ] Update claude_bridge.py to use config (7 agent vars)
- [ ] Update server.py and subagent.py (4 MCP vars)
- [ ] Update store.py, indexer.py, models.py (9 directory vars)
- [ ] Update embeddings.py, search.py (3 RAG vars)
- [ ] Update client.py (2 I/O vars)
- [ ] Update agent_card.py, discovery.py (4 network vars)
- [ ] Verify all tests pass
- [ ] Check performance baselines unchanged
- [ ] Commit Phase 2 changes with clear message

### Phase 3: Test Infrastructure

- [ ] Create pytest fixtures for config override
- [ ] Create pytest.ini with timeout configuration
- [ ] Update all conftest.py files
- [ ] Test config override fixtures
- [ ] Verify test isolation working
- [ ] Run full test suite
- [ ] Commit Phase 3 changes

### Phase 4: Documentation

- [ ] Update README.md with configuration section
- [ ] Create environment-variables.md reference
- [ ] Create deployment guide
- [ ] Create validation checklist
- [ ] Test all examples work
- [ ] Get team review/feedback
- [ ] Commit Phase 4 changes
- [ ] Update CHANGELOG.md with migration notes

### Optional Phase 5: Deprecation

- [ ] Add deprecation warnings for VS_* variables
- [ ] Update documentation with migration timeline
- [ ] Plan removal of VS_* for next major version
- [ ] Communicate timeline to users

---

## Conclusion

This standardization blueprint provides a comprehensive path to unified environment variable management in vaultspec. The phased approach allows incremental implementation without disrupting existing functionality, while the centralized config module, test infrastructure consolidation, and complete documentation ensure long-term maintainability and developer experience.

**Expected Impact:**

- **Improved discoverability**: Developers can find all configurations in one place
- **Better type safety**: Validation prevents configuration errors early
- **Simplified testing**: Override fixtures eliminate os.environ manipulation
- **Enhanced operations**: Clear .env.example and deployment documentation
- **Future extensibility**: New configurations can follow established patterns
- **Reduced maintenance**: No more scattered os.environ reads or duplicate constants

**Timeline:** 4 weeks (concurrent development possible)

**Team Effort:** 40-50 hours total (flexible across team members)

---
