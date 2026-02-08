import pathlib
import sys

# Add lib/src to path
SCRIPTS_DIR = pathlib.Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent.parent
sys.path.insert(0, str(ROOT_DIR / ".rules" / "lib" / "src"))

from orchestration.types import DocType, VaultConstants  # noqa: E402
from orchestration.utils import parse_vault_metadata, safe_read_text  # noqa: E402


def check_vault():
    docs_dir = ROOT_DIR / ".docs"
    if not docs_dir.exists():
        print("Error: .docs directory not found.")
        return 1

    errors = []

    #  Validate Structure
    errors.extend(VaultConstants.validate_vault_structure(ROOT_DIR))

    #  Validate Files
    for path in docs_dir.rglob("*.md"):
        # Skip internal config
        if ".obsidian" in path.parts:
            continue

        rel_path = path.relative_to(docs_dir)
        if len(rel_path.parts) < 2:
            # File in .docs root is already handled by validate_vault_structure
            continue

        dir_name = rel_path.parts[0]
        try:
            doc_type = DocType(dir_name)
        except ValueError:
            # Unsupported directory, already handled by validate_vault_structure
            continue

        filename = path.name

        # Validate Filename
        file_errors = VaultConstants.validate_filename(filename, doc_type)
        for err in file_errors:
            errors.append(f"{path}: {err}")

        # Validate Content (Frontmatter)
        try:
            content = safe_read_text(path, ROOT_DIR)
            metadata, _ = parse_vault_metadata(content)
            content_errors = metadata.validate()

            # Additional check: Directory Tag must match actual directory
            dir_tag = doc_type.tag
            if dir_tag not in metadata.tags:
                msg = (
                    f"Vault violation: Missing mandatory directory tag '{dir_tag}' "
                    f"for file in {dir_name}/ directory."
                )
                content_errors.append(msg)

            for err in content_errors:
                errors.append(f"{path}: {err}")
        except Exception as e:
            errors.append(f"{path}: Error reading/parsing: {e}")

    if errors:
        print(f"Vault validation failed with {len(errors)} errors:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Vault validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(check_vault())
