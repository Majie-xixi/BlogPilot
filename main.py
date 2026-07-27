"""VS Code-friendly launcher for the desktop application."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from blogpost.cli import main as cli_main  # noqa: E402

        raise SystemExit(cli_main())

    from blogpost.ui.app import main as gui_main  # noqa: E402

    raise SystemExit(gui_main())
