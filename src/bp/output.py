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


def _fmt_money_raw(amount: float, width: int = 12) -> str:
    sign = "+" if amount >= 0 else ""
    return f"{sign}{amount:,.2f}".rjust(width)


def _fmt_bal(amount: float, width: int = 12) -> str:
    raw = f"{amount:,.2f}"
    padded = raw.rjust(width)
    return _c(padded, GREEN if amount >= 0 else RED)


def _fmt_bal_raw(amount: float, width: int = 12) -> str:
    return f"{amount:,.2f}".rjust(width)


# ---------------------------------------------------------------------------
# CLI output
# ---------------------------------------------------------------------------

def _print_cli(opening: float, events: list[Event],
               today: date, fm_start: date, fm_end: date,
               verbose: bool) -> None:
    print(_c(f"Today: {today.strftime('%A, %b %d, %Y')}", CYAN))
    print(_c(f"Showing: {fm_start.strftime('%b %d')} \u2013 "
             f"{fm_end.strftime('%b %d, %Y')}", BOLD))
    print(f"Opening: {_fmt_bal(opening)}")
    print()

    if events:
        if verbose:
            hdr = (f"  {'Date':<10}{'Cat':<12}"
                   f"{'Amount':>12}  {'Note':<20}"
                   f"{'Source':<10}{'M':>1} {'Balance':>12}")
            width = 80
        else:
            hdr = (f"  {'Date':<10}"
                   f"{'Amount':>12}  {'Note':<20}"
                   f"{'Source':<10}{'M':>1} {'Balance':>12}")
            width = 68
        print(hdr)
        print(f"  {'\u2500' * width}")

        today_sep_shown = False
        had_past = False
        prev_month: tuple[int, int] | None = None

        for e in events:
            is_past = e.date < today

            # Insert "today" separator when transitioning to today or future
            if not today_sep_shown and not is_past:
                if had_past:
                    label = "\u2500\u2500\u2500 today "
                    print(f"  {label}{'\u2500' * (width - len(label))}")
                today_sep_shown = True

            # Month separator (only between events on the same side of today)
            cur_month = (e.date.year, e.date.month)
            if prev_month and cur_month != prev_month:
                print()
            prev_month = cur_month

            if is_past:
                had_past = True

            ds = e.date.strftime("%b %d")
            note = e.note[:20]
            source = e.extra.get("_file", "")[:10]
            merged = "\u2713" if e.extra.get("merged") else " "

            if is_past:
                # Dim entire line for past entries
                amt = _fmt_money_raw(e.amount)
                bal = _fmt_bal_raw(e.running_balance)
                if verbose:
                    cat = e.category[:12]
                    line = (f"  {ds:<10}{cat:<12}"
                            f"{amt}  {note:<20}"
                            f"{source:<10}{merged:>1} {bal}")
                else:
                    line = (f"  {ds:<10}"
                            f"{amt}  {note:<20}"
                            f"{source:<10}{merged:>1} {bal}")
                print(_c(line, DIM))
            else:
                amt = _fmt_money(e.amount)
                bal = _fmt_bal(e.running_balance)
                if verbose:
                    cat = e.category[:12]
                    cat_w = 12 + (len(DIM) + len(RESET) if _color else 0)
                    print(f"  {ds:<10}{_c(cat, DIM):<{cat_w}}"
                          f"{amt}  {note:<20}"
                          f"{source:<10}{merged:>1} {bal}")
                else:
                    print(f"  {ds:<10}"
                          f"{amt}  {note:<20}"
                          f"{source:<10}{merged:>1} {bal}")

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
              today: date, fm_start: date, fm_end: date,
              verbose: bool) -> None:
    sign = lambda a: f"+{a:,.2f}" if a >= 0 else f"{a:,.2f}"

    print(f"**Today:** {today.isoformat()}")
    print()
    print(f"**Showing:** {fm_start.isoformat()} \u2013 {fm_end.isoformat()}")
    print()
    print(f"**Opening:** {opening:,.2f}")
    print()

    if verbose:
        print("| Date | Category | Amount | Note | Source | M | Balance |")
        print("|------|----------|-------:|------|--------|---|--------:|")
        for e in events:
            src = e.extra.get("_file", "")
            mrg = "\u2713" if e.extra.get("merged") else ""
            print(f"| {e.date.isoformat()} | {e.category} "
                  f"| {sign(e.amount)} | {e.note} "
                  f"| {src} | {mrg} "
                  f"| {e.running_balance:,.2f} |")
    else:
        print("| Date | Amount | Note | Source | M | Balance |")
        print("|------|-------:|------|--------|---|--------:|")
        for e in events:
            src = e.extra.get("_file", "")
            mrg = "\u2713" if e.extra.get("merged") else ""
            print(f"| {e.date.isoformat()} | {sign(e.amount)} "
                  f"| {e.note} | {src} | {mrg} "
                  f"| {e.running_balance:,.2f} |")

    total_in = sum(e.amount for e in events if e.amount > 0)
    total_out = sum(e.amount for e in events if e.amount < 0)
    net = total_in + total_out
    closing = opening + net

    print()
    print(f"| | **Income** | {sign(total_in)} | | | |")
    print(f"| | **Expenses** | {sign(total_out)} | | | |")
    print(f"| | **Net** | {sign(net)} | | | |")
    print()
    print(f"**Closing Balance:** {closing:,.2f}")


# ---------------------------------------------------------------------------
# JSON / YAML output
# ---------------------------------------------------------------------------

def _to_dict(opening: float, events: list[Event],
             today: date, fm_start: date, fm_end: date) -> dict:
    total_in = sum(e.amount for e in events if e.amount > 0)
    total_out = sum(e.amount for e in events if e.amount < 0)
    return {
        "today": today.isoformat(),
        "period_start": fm_start.isoformat(),
        "period_end": fm_end.isoformat(),
        "opening_balance": opening,
        "events": [
            {"date": e.date.isoformat(), "amount": e.amount,
             "note": e.note, "category": e.category,
             "source": e.extra.get("_file", ""),
             "merged": e.extra.get("merged", False),
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
                today: date, fm_start: date, fm_end: date) -> None:
    print(json.dumps(_to_dict(opening, events, today, fm_start, fm_end),
                     indent=2))


def _print_yaml(opening: float, events: list[Event],
                today: date, fm_start: date, fm_end: date) -> None:
    print(yaml.dump(_to_dict(opening, events, today, fm_start, fm_end),
                    default_flow_style=False, sort_keys=False))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def print_output(opening: float, events: list[Event],
                 today: date, fm_start: date, fm_end: date,
                 fmt: str = "cli", verbose: bool = False) -> None:
    _init_color()

    if fmt == "md":
        _print_md(opening, events, today, fm_start, fm_end, verbose)
    elif fmt == "json":
        _print_json(opening, events, today, fm_start, fm_end)
    elif fmt == "yaml":
        _print_yaml(opening, events, today, fm_start, fm_end)
    else:
        _print_cli(opening, events, today, fm_start, fm_end, verbose)
