import importlib
import pathlib
import sys

# Add lib/src to path
SCRIPTS_DIR = pathlib.Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent.parent
sys.path.insert(0, str(ROOT_DIR / ".rules" / "lib" / "src"))

# Use importlib to avoid E402
verification_api = importlib.import_module("verification.api")


def check_vault():
    root_dir = ROOT_DIR
    errors = verification_api.get_malformed(root_dir)

    if errors:
        print(f"Vault validation failed with {len(errors)} errors:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Vault validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(check_vault())
