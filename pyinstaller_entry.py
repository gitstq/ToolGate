"""PyInstaller entry point.

Kept at the repository root level so the frozen executable imports ToolGate
as a proper installed package (relative imports work correctly).
"""
from __future__ import annotations

import sys

from toolgate.cli import main

if __name__ == "__main__":
    sys.exit(main())
