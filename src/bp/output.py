from __future__ import annotations

import json
import os
import sys
from datetime import date

import yaml

from .core import Event

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"

_color = True


def _init_color() -> None:
    global _color
    _color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if _color else text


def _fmt_money(amount: float, width: int = 12) -> str:
    sign = "+" if amount >= 0 else ""
    raw = f"{sign}{amount:,.2f}"
    padded = raw.rjust(width)
    return _c(padded, GREEN if amount >= 0 else RED)


def _fmt_bal(amount: float, width: int = 12) -> str:
    raw = f"{amount:,.2f}"
    padded = raw.rjust(width)
    return _c(padded, GREEN if amount >= 0 else RED)


# ---------------------------------------------------------------------------
# CLI output
# ---------------------------------------------------------------------------

def _print_cli(opening: float, events: list[Event],
               start: date, end: date, verbose: bool) -> None:
    print(_c(f"Today: {start.strftime('%A, %b %d, %Y')}", CYAN))
    print(_c(f"Showing until: {end.strftime('%b %d, %Y')}", BOLD))
    print(f"Balance now: {_fmt_bal(opening)}")
    print()

    if events:
        if verbose:
            hdr = (f"  {'Date':<12}{'Category':<16}"
                   f"{'Amount':>12}  {'Note':<26}{'Balance':>12}")
        else:
            hdr = (f"  {'Date':<12}{'Amount':>12}  "
                   f"{'Note':<26}{'Balance':>12}")
        print(hdr)
        width = 68 if verbose else 64
        print(f"  {'\u2500' * width}")

        prev_month: tuple[int, int] | None = None
        for e in events:
            cur_month = (e.date.year, e.date.month)
            if prev_month and cur_month != prev_month:
                print()  # visual separator between calendar months
            prev_month = cur_month

            ds = e.date.strftime("%b %d")
            amt = _fmt_money(e.amount)
            bal = _fmt_bal(e.running_balance)
            note = e.note[:26]
            if verbose:
                cat = e.category[:16]
                print(f"  {ds:<12}{_c(cat, DIM):<{16 + (len(DIM) + len(RESET) if _color else 0)}}"
                      f"{amt}  {note:<26}{bal}")
            else:
                print(f"  {ds:<12}{amt}  {note:<26}{bal}")

        print(f"  {'\u2500' * width}")

    # Summary
    total_in = sum(e.amount for e in events if e.amount > 0)
    total_out = sum(e.amount for e in events if e.amount < 0)
    net = total_in + total_out
    closing = opening + net

    print()
    print(f"  Income:   {_fmt_money(total_in)}")
    print(f"  Expenses: {_fmt_money(total_out)}")
    print(f"  Net:      {_fmt_money(net)}")
    print()
    print(f"Closing Balance: {_fmt_bal(closing)}")

    # Warn if balance ever goes negative
    low = min((e.running_balance for e in events), default=opening)
    if low < 0:
        print()
        print(_c(f"  WARNING: Balance drops to {low:,.2f}!", YELLOW))

    if verbose and events:
        _print_category_breakdown(events)


def _print_category_breakdown(events: list[Event]) -> None:
    cats: dict[str, float] = {}
    for e in events:
        cats[e.category] = cats.get(e.category, 0.0) + e.amount
    print()
    print(_c("Breakdown by category:", BOLD))
    for cat, total in sorted(cats.items()):
        print(f"  {cat:<20}{_fmt_money(total)}")


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _print_md(opening: float, events: list[Event],
              start: date, end: date, verbose: bool) -> None:
    sign = lambda a: f"+{a:,.2f}" if a >= 0 else f"{a:,.2f}"

    print(f"**Today:** {start.isoformat()}")
    print()
    print(f"**Showing until:** {end.strftime('%b %d, %Y')}")
    print()
    print(f"**Balance now:** {opening:,.2f}")
    print()

    if verbose:
        print("| Date | Category | Amount | Note | Balance |")
        print("|------|----------|-------:|------|--------:|")
        for e in events:
            print(f"| {e.date.isoformat()} | {e.category} "
                  f"| {sign(e.amount)} | {e.note} "
                  f"| {e.running_balance:,.2f} |")
    else:
        print("| Date | Amount | Note | Balance |")
        print("|------|-------:|------|--------:|")
        for e in events:
            print(f"| {e.date.isoformat()} | {sign(e.amount)} "
                  f"| {e.note} | {e.running_balance:,.2f} |")

    total_in = sum(e.amount for e in events if e.amount > 0)
    total_out = sum(e.amount for e in events if e.amount < 0)
    net = total_in + total_out
    closing = opening + net

    print()
    print(f"| | **Income** | {sign(total_in)} | |")
    print(f"| | **Expenses** | {sign(total_out)} | |")
    print(f"| | **Net** | {sign(net)} | |")
    print()
    print(f"**Closing Balance:** {closing:,.2f}")


# ---------------------------------------------------------------------------
# JSON / YAML output
# ---------------------------------------------------------------------------

def _to_dict(opening: float, events: list[Event],
             start: date, end: date) -> dict:
    total_in = sum(e.amount for e in events if e.amount > 0)
    total_out = sum(e.amount for e in events if e.amount < 0)
    return {
        "today": start.isoformat(),
        "period_end": end.isoformat(),
        "balance_now": opening,
        "events": [
            {"date": e.date.isoformat(), "amount": e.amount,
             "note": e.note, "category": e.category,
             "balance": round(e.running_balance, 2)}
            for e in events
        ],
        "summary": {
            "income": round(total_in, 2),
            "expenses": round(total_out, 2),
            "net": round(total_in + total_out, 2),
        },
        "closing_balance": round(opening + total_in + total_out, 2),
    }


def _print_json(opening: float, events: list[Event],
                start: date, end: date) -> None:
    print(json.dumps(_to_dict(opening, events, start, end), indent=2))


def _print_yaml(opening: float, events: list[Event],
                start: date, end: date) -> None:
    print(yaml.dump(_to_dict(opening, events, start, end),
                    default_flow_style=False, sort_keys=False))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def print_output(opening: float, events: list[Event],
                 start: date, end: date,
                 fmt: str = "cli", verbose: bool = False) -> None:
    _init_color()

    if fmt == "md":
        _print_md(opening, events, start, end, verbose)
    elif fmt == "json":
        _print_json(opening, events, start, end)
    elif fmt == "yaml":
        _print_yaml(opening, events, start, end)
    else:
        _print_cli(opening, events, start, end, verbose)
