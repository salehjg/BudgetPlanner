from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Subscription:
    name: str
    day: int
    amount: float  # negative = expense


@dataclass
class Config:
    paycheck_day: int
    paycheck_amount: float  # positive
    paycheck_overrides: dict[str, float]  # "YYYY-MM" -> amount
    balance_date: date
    balance_amount: float
    subscriptions: list[Subscription] = field(default_factory=list)


@dataclass
class Entry:
    date: date
    amount: float
    note: str
    extra: dict = field(default_factory=dict)


@dataclass
class Event:
    date: date
    amount: float
    note: str
    category: str  # "paycheck", "subscription", "entry"
    extra: dict = field(default_factory=dict)
    running_balance: float = 0.0


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_date(val) -> date:
    """Accept datetime.date or ISO string."""
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


def add_months(d: date, n: int) -> date:
    """Add *n* months to *d*, clamping day to the month's last day."""
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def clamp_day(year: int, month: int, day: int) -> date:
    actual = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, actual)


def financial_month_start(today: date, paycheck_day: int) -> date:
    """Return the start of the financial month that *today* falls in."""
    this_month = clamp_day(today.year, today.month, paycheck_day)
    if this_month <= today:
        return this_month
    return add_months(this_month, -1)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_config(directory: Path) -> Config:
    path = directory / "conf.yaml"
    if not path.exists():
        raise SystemExit(f"Error: conf.yaml not found in {directory.resolve()}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw or "paycheck" not in raw:
        raise SystemExit("Error: 'paycheck' section missing in conf.yaml")
    if "balance" not in raw:
        raise SystemExit("Error: 'balance' section missing in conf.yaml")

    pc = raw["paycheck"]
    bal = raw["balance"]

    overrides: dict[str, float] = {}
    for k, v in pc.get("overrides", {}).items():
        overrides[str(k)] = float(v)

    subs: list[Subscription] = []
    for s in raw.get("subscriptions", []):
        subs.append(Subscription(name=s["name"], day=int(s["day"]),
                                 amount=float(s["amount"])))

    return Config(
        paycheck_day=int(pc["day"]),
        paycheck_amount=float(pc["amount"]),
        paycheck_overrides=overrides,
        balance_date=_parse_date(bal["date"]),
        balance_amount=float(bal["amount"]),
        subscriptions=subs,
    )


def load_entries(directory: Path) -> list[Entry]:
    entries: list[Entry] = []
    for ext in ("*.yaml", "*.yml"):
        for path in sorted(directory.glob(ext)):
            if path.name.startswith("conf."):
                continue
            with open(path) as f:
                raw = yaml.safe_load(f)
            if raw is None:
                continue
            items = raw if isinstance(raw, list) else raw.get("entries", [])
            if not items:
                continue
            for item in items:
                known = {"date", "amount", "note"}
                extra = {k: v for k, v in item.items() if k not in known}
                entries.append(Entry(
                    date=_parse_date(item["date"]),
                    amount=float(item["amount"]),
                    note=item.get("note", ""),
                    extra=extra,
                ))
    return entries


# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------

def _monthly_dates(day: int, start: date, end: date) -> list[date]:
    """Generate clamped monthly dates for *day* within [start, end]."""
    dates: list[date] = []
    y, m = start.year, start.month
    while True:
        d = clamp_day(y, m, day)
        if d > end:
            break
        if d >= start:
            dates.append(d)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return dates


def build_events(config: Config, entries: list[Entry],
                 start: date, end: date) -> list[Event]:
    events: list[Event] = []

    # Paychecks
    for d in _monthly_dates(config.paycheck_day, start, end):
        key = d.strftime("%Y-%m")
        amount = config.paycheck_overrides.get(key, config.paycheck_amount)
        events.append(Event(date=d, amount=amount,
                            note="Paycheck", category="paycheck"))

    # Subscriptions
    for sub in config.subscriptions:
        for d in _monthly_dates(sub.day, start, end):
            events.append(Event(date=d, amount=sub.amount,
                                note=sub.name, category="subscription"))

    # Manual entries
    for entry in entries:
        if start <= entry.date <= end:
            events.append(Event(date=entry.date, amount=entry.amount,
                                note=entry.note, category="entry",
                                extra=entry.extra))

    # Sort: date -> income before expenses -> alphabetical note
    events.sort(key=lambda e: (e.date, 0 if e.amount >= 0 else 1, e.note))
    return events


# ---------------------------------------------------------------------------
# Balance calculation
# ---------------------------------------------------------------------------

def calculate(config: Config, entries: list[Entry],
              display_start: date, display_end: date,
              ) -> tuple[float, list[Event]]:
    """Return (opening_balance, events_with_running_balance)."""
    anchor = config.balance_date
    anchor_amount = config.balance_amount

    if anchor <= display_start:
        if anchor < display_start:
            pre = build_events(config, entries,
                               anchor, display_start - timedelta(days=1))
            opening = anchor_amount + sum(e.amount for e in pre)
        else:
            opening = anchor_amount
    else:
        # Anchor is after display_start — reverse-calculate
        between = build_events(config, entries,
                               display_start, anchor - timedelta(days=1))
        opening = anchor_amount - sum(e.amount for e in between)

    events = build_events(config, entries, display_start, display_end)

    balance = opening
    for event in events:
        balance += event.amount
        event.running_balance = balance

    return opening, events


def filter_past(events: list[Event], today: date,
                ) -> tuple[float, list[Event]]:
    """Drop events before *today* and today's already-paid entries.

    Returns (skipped_total, kept_events).  Add *skipped_total* to the
    opening balance to get the effective "as-of-today" balance.
    """
    skipped = 0.0
    kept: list[Event] = []
    for e in events:
        if e.date < today or (
            e.date == today and e.extra.get("status") == "paid"
        ):
            skipped += e.amount
        else:
            kept.append(e)

    # Recalculate running balances for kept events
    balance = 0.0  # caller will add adjusted opening
    for e in kept:
        balance += e.amount
        e.running_balance = balance

    return skipped, kept
