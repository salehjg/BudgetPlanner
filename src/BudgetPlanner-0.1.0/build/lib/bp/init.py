from __future__ import annotations

from datetime import date
from pathlib import Path

CONF_TEMPLATE = """\
# Budget planner configuration
# All amounts: positive = income, negative = expense

paycheck:
  day: 1             # day of month you get paid
  amount: 0          # monthly paycheck amount
  # overrides:       # uncomment to override specific months
  #   "{year}-12": 0 # e.g. holiday bonus

balance:
  date: {today}      # date you last checked your bank account
  amount: 0          # how much was in your account on that date

subscriptions: []
  # - name: Netflix
  #   day: 5
  #   amount: -15.99
  #
  # - name: Spotify
  #   day: 1
  #   amount: -9.99
"""

ENTRIES_TEMPLATE = """\
# {month_name} {year} expenses and income
# Each entry needs: date, amount (+/-), note
# You can add any extra columns you want (category, tags, etc.)

- date: {today}
  amount: -0
  note: Example expense

# - date: {today}
#   amount: 0
#   note: Example income
"""


def run_init(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)

    conf_path = directory / "conf.yaml"
    if conf_path.exists():
        raise SystemExit(
            f"Error: {conf_path} already exists. "
            "Remove it first if you want to re-initialise."
        )

    today = date.today()
    month_name = today.strftime("%B")
    year = today.year
    entry_filename = f"{today.strftime('%Y-%m')}.yaml"

    conf_path.write_text(
        CONF_TEMPLATE.format(today=today.isoformat(), year=year)
    )

    entry_path = directory / entry_filename
    if not entry_path.exists():
        entry_path.write_text(
            ENTRIES_TEMPLATE.format(
                today=today.isoformat(),
                month_name=month_name,
                year=year,
            )
        )

    print(f"Initialised budget in {directory.resolve()}")
    print(f"  created {conf_path.name}")
    print(f"  created {entry_filename}")
    print()
    print("Next steps:")
    print("  1. Edit conf.yaml - set your paycheck day/amount and bank balance")
    print("  2. Add subscriptions to conf.yaml")
    print(f"  3. Log expenses in {entry_filename}")
    print(f"  4. Run: bp {directory}")
