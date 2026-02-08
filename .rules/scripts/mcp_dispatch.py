"""MCP Dispatch Server Entrypoint.

Delegates to the modular implementation in .rules/lib/src/dispatch_server/server.py
"""

import pathlib
import sys

# Add library logic to path
# Script is at .rules/scripts/mcp_dispatch.py
# Root is ../..
CURRENT_DIR = pathlib.Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
LIB_SRC_DIR = ROOT_DIR / ".rules" / "lib" / "src"

if str(LIB_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_SRC_DIR))

try:
    from dispatch_server.server import main
except ImportError as e:
    print(f"Failed to import dispatch server: {e}", file=sys.stderr)
    print(f"sys.path: {sys.path}", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main()