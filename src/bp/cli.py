from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .core import (
    add_months,
    calculate,
    financial_month_start,
    load_config,
    load_entries,
)
from .init import run_init
from .output import print_output

_SUBCOMMANDS = {"init", "import", "show"}


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    # Default to "show" when the first arg is not a known subcommand
    # and not a help flag.  This lets `bp .` and `bp -v .` work
    # without typing `bp show .`.
    if argv and argv[0] not in _SUBCOMMANDS and argv[0] not in ("-h", "--help"):
        argv = ["show"] + list(argv)

    parser = argparse.ArgumentParser(
        prog="bp",
        description="Budget planner \u2013 project your bank balance from YAML config.",
        epilog=(
            "examples:\n"
            "  bp                        show current financial month\n"
            "  bp /path/to/budget        show budget from a directory\n"
            "  bp -m 3 -v                show 3 months, verbose\n"
            "  bp init .                 create starter config\n"
            "  bp import klarna K.html klarna.yaml\n"
            "  bp import poste  P.xlsx  poste.yaml\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    # --- import (with sub-subcommands) ---
    import_p = sub.add_parser(
        "import", help="Import payment data from external sources",
    )
    import_sub = import_p.add_subparsers(dest="import_source")

    klarna_p = import_sub.add_parser(
        "klarna", help="Import from a Klarna HTML page",
    )
    klarna_p.add_argument("input", help="Path to saved Klarna HTML file")
    klarna_p.add_argument("output", help="Output YAML file path")

    poste_p = import_sub.add_parser(
        "poste", help="Import from a Poste Italiane XLSX file",
    )
    poste_p.add_argument("input", help="Path to Poste XLSX file")
    poste_p.add_argument("output", help="Output YAML file path")

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
        if args.import_source == "klarna":
            from .import_klarna import run_import
            run_import(Path(args.input), Path(args.output))
        elif args.import_source == "poste":
            from .import_poste import run_import
            run_import(Path(args.input), Path(args.output))
        else:
            import_p.print_help()
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

    print_output(opening, events, today, fm_start, fm_end,
                 fmt=args.format, verbose=args.verbose)
