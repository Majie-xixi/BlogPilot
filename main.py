"""VS Code-friendly launcher for the desktop application."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from blogpost.ui.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
