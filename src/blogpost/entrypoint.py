from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) == 1:
        from blogpost.ui.app import main as gui_main

        return gui_main()
    from blogpost.cli import main as cli_main

    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
