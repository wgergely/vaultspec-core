import pathlib
import re
import sys

# Patterns
# Standard: yyyy-mm-dd-<feature>-<type>.md
# Exec:     yyyy-mm-dd-<feature>-<phase>-<step>.md
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}"
VALID_NAME = re.compile(rf"{DATE_PATTERN}-([a-z0-9]+-?)+\.md$")


def check_docs_naming():
    docs_dir = pathlib.Path(".docs")
    if not docs_dir.exists():
        return 0

    errors = 0
    # Search all .md files in .docs/ (recursive)
    for path in docs_dir.rglob("*.md"):
        # Skip .obsidian folder
        if ".obsidian" in path.parts:
            continue

        filename = path.name

        # Check pattern
        if not VALID_NAME.match(filename):
            print(f"Error: Invalid filename '{path}'")
            print("  Expected pattern: yyyy-mm-dd-<feature>-<type>.md")
            errors += 1

    return errors


if __name__ == "__main__":
    sys.exit(check_docs_naming())
