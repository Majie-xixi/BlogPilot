from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from blogpost import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blogpost-publisher")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="open the desktop application")
    sub.add_parser("run-daily", help="run the scheduled daily pipeline")
    run_now = sub.add_parser("run-now", help="run the pipeline immediately")
    run_now.add_argument("--allow-same-day", action="store_true")
    run_now.add_argument("--account", action="append", dest="accounts")
    sub.add_parser("login", help="open the 51CTO login browser")
    schedule = sub.add_parser("schedule", help="manage Windows scheduling")
    schedule_sub = schedule.add_subparsers(dest="schedule_command")
    schedule_sub.add_parser("install")
    schedule_sub.add_parser("status")
    schedule_sub.add_parser("remove")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "gui":
        from blogpost.ui.app import main as gui_main

        return gui_main()
    from blogpost.application import build_context
    from blogpost.domain import RunStatus, Trigger
    from blogpost.logging_setup import configure_logging
    from blogpost.paths import log_path

    configure_logging(log_path())
    context = build_context()
    if args.command == "login":
        context.publisher.open_login()
        return 0
    if args.command == "schedule":
        if args.schedule_command == "install":
            accounts = context.accounts(enabled_only=True)
            context.scheduler.install([account.schedule_time for account in accounts])
            print("已安装：" + "、".join(f"{a.display_name} {a.schedule_time:%H:%M}" for a in accounts))
            return 0
        if args.schedule_command == "remove":
            context.scheduler.remove()
            print("已移除")
            return 0
        if args.schedule_command == "status":
            print(context.scheduler.status())
            return 0
        parser.error("schedule requires install, status or remove")
    try:
        trigger = Trigger.SCHEDULED if args.command == "run-daily" else Trigger.MANUAL
        results = context.run_accounts(
            getattr(args, "accounts", None),
            trigger,
            allow_same_day=bool(getattr(args, "allow_same_day", False)),
            due_only=trigger == Trigger.SCHEDULED,
            progress=lambda account, status, message: print(
                f"[{account.display_name}][{status.value}] {message}"
            ),
        )
        for _account, result in results:
            if result.url:
                print(result.url)
        return 0 if results and all(
            result.status in {RunStatus.PUBLISHED, RunStatus.SKIPPED}
            for _account, result in results
        ) else 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
