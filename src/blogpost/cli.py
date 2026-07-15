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
            context.scheduler.install(context.config.schedule_time)
            print(f"已安装：每天 {context.config.schedule_time:%H:%M}")
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
        pipeline = context.build_pipeline()
        trigger = Trigger.SCHEDULED if args.command == "run-daily" else Trigger.MANUAL
        result = pipeline.run(
            trigger,
            allow_same_day=bool(getattr(args, "allow_same_day", False)),
            progress=lambda status, message: print(f"[{status.value}] {message}"),
        )
        if result.url:
            print(result.url)
        return 0 if result.status in {RunStatus.PUBLISHED, RunStatus.SKIPPED} else 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
