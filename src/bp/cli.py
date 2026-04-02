from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .core import (
    add_months,
    calculate,
    filter_past,
    financial_month_start,
    load_config,
    load_entries,
)
from .init import run_init
from .output import print_output

_SUBCOMMANDS = {"init", "import"}


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    # Default to "show" when the first arg is not a known subcommand.
    # This lets `bp .` and `bp -v .` work without typing `bp show .`.
    if not argv or argv[0] not in _SUBCOMMANDS:
        argv = ["show"] + list(argv)

    parser = argparse.ArgumentParser(
        prog="bp",
        description="Budget planner - project your bank balance from YAML config.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- init ---
    init_p = sub.add_parser(
        "init", help="Create starter conf.yaml and example entries",
    )
    init_p.add_argument(
        "directory", nargs="?", default=".",
        help="Directory to initialise (default: .)",
    )

    # --- import ---
    import_p = sub.add_parser(
        "import", help="Import payments from a Klarna HTML page",
    )
    import_p.add_argument(
        "html_file", help="Path to saved Klarna HTML file",
    )
    import_p.add_argument(
        "output", help="Output YAML file path (e.g. klarna.yaml)",
    )

    # --- show (implicit default) ---
    show_p = sub.add_parser(
        "show",
        help="Display budget (default when no command is given)",
        epilog="Tip: run 'bp init .' to create a starter budget.",
    )
    show_p.add_argument(
        "directory", nargs="?", default=".",
        help="Path to directory containing conf.yaml (default: .)",
    )
    show_p.add_argument(
        "-m", "--months", type=int, default=1, metavar="N",
        help="Number of financial months to display (default: 1)",
    )
    show_p.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed output with categories and breakdowns",
    )
    show_p.add_argument(
        "-f", "--format",
        choices=["cli", "md", "json", "yaml"], default="cli",
        help="Output format (default: cli)",
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        run_init(Path(args.directory))
        return

    if args.command == "import":
        from .import_klarna import run_import
        run_import(Path(args.html_file), Path(args.output))
        return

    # show
    directory = Path(args.directory)
    if not directory.is_dir():
        raise SystemExit(f"Error: {directory} is not a directory")

    config = load_config(directory)
    entries = load_entries(directory)

    today = date.today()
    fm_start = financial_month_start(today, config.paycheck_day)
    fm_end = add_months(fm_start, args.months) - timedelta(days=1)

    opening, events = calculate(config, entries, fm_start, fm_end)

    # Drop past events and today's already-paid entries
    skipped, events = filter_past(events, today)
    opening += skipped
    # Fix running balances relative to adjusted opening
    balance = opening
    for event in events:
        balance += event.amount
        event.running_balance = balance

    print_output(opening, events, today, fm_end,
                 fmt=args.format, verbose=args.verbose)
