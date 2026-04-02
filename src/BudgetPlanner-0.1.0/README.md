# bp - Budget Planner CLI

A command-line budget planner that projects your bank balance forward from
YAML configuration files. You define your paycheck, subscriptions, and bank
balance in `conf.yaml`, log one-off expenses and income in additional YAML
files, and `bp` shows you what your account will look like day by day.

All amounts follow one simple rule: **positive = money in, negative = money
out**. This applies everywhere - config files, entry files, and output.

## Install

Requires Python 3.10+.

```
pip install -e .
```

This gives you the `bp` command.

## Quick start

```
bp init my-budget
cd my-budget
# Edit conf.yaml with your real numbers
bp .
```

## How it works

`bp` reads a directory containing:

1. **`conf.yaml`** (required) - your paycheck schedule, known bank balance,
   and recurring subscriptions.
2. **Any other `*.yaml` / `*.yml` files** - one-off expenses and income
   entries (name the files however you want, e.g. `2026-04.yaml`,
   `groceries.yaml`).

It generates all recurring events (paycheck + subscriptions) alongside your
manual entries, then calculates a running balance starting from your known
bank balance anchor.

Only today and future events are shown. Past events are already reflected in
your balance. If an entry has `status: paid` (e.g. from a Klarna import), it
is also excluded from today's output since it already went through.

### conf.yaml

```yaml
paycheck:
  day: 25          # day of month you get paid
  amount: 3000     # monthly paycheck (positive)
  overrides:       # optional: override specific months
    "2026-06": 3500

balance:
  date: 2026-04-01 # when you last checked your bank account
  amount: 5200     # how much was in it

subscriptions:
  - name: Netflix
    day: 5
    amount: -15.99

  - name: Spotify
    day: 1
    amount: -9.99
```

The `paycheck` and `balance` sections are required. `subscriptions` is
optional.

### Entry files

Any YAML file in the directory (except `conf.yaml`) is treated as an entry
file. Each is a list of transactions:

```yaml
- date: 2026-04-03
  amount: -85.00
  note: Groceries

- date: 2026-04-14
  amount: 150.00
  note: Freelance payment
```

Every entry needs `date`, `amount`, and `note`. You can add any extra
columns you want (like `category`, `tags`, etc.) - they are preserved but
don't affect calculations.

A top-level list (as above) or an `entries:` key both work:

```yaml
entries:
  - date: 2026-04-03
    amount: -85.00
    note: Groceries
```

## Commands

### `bp [directory]` - show your budget

The main command. Reads `conf.yaml` and all entry files from the given
directory (defaults to `.`), then prints a day-by-day projection of your
balance.

```
bp .
bp path/to/budget
```

```
Today: Thursday, Apr 02, 2026
Showing until: Apr 24, 2026
Balance now:     5,190.01

  Date              Amount  Note                           Balance
  ────────────────────────────────────────────────────────────────
  Apr 03            -85.00  Groceries                     5,105.01
  Apr 05            -15.99  Netflix                       5,089.02
  Apr 07            -42.50  Dinner out                    5,046.52
  Apr 10            -45.00  Gym                           5,001.52
  Apr 12            -35.00  Gas                           4,966.52
  Apr 14           +150.00  Freelance payment             5,116.52
  Apr 15             -2.99  Cloud Storage                 5,113.53
  Apr 18           -120.00  Electric bill                 4,993.53
  Apr 20            -55.00  Phone Plan                    4,938.53
  Apr 22            -60.00  Groceries                     4,878.53
  ────────────────────────────────────────────────────────────────

  Income:        +150.00
  Expenses:      -461.48
  Net:           -311.48

Closing Balance:     4,878.53
```

**Options:**

| Flag | Description |
|------|-------------|
| `-m N`, `--months N` | Show N financial months instead of 1. A financial month starts on your paycheck day. |
| `-v`, `--verbose` | Show category column and per-category breakdown. |
| `-f FORMAT`, `--format FORMAT` | Output format: `cli` (default, colored table), `md` (markdown), `json`, `yaml`. |

**Examples:**

```bash
bp .                    # current financial month
bp -m 3 .              # next 3 financial months
bp -v .                # verbose with categories
bp -f md .             # markdown table (good for piping)
bp -f json . | jq      # structured JSON output
```

### `bp init [directory]` - scaffold a new budget

Creates a starter `conf.yaml` and a `YYYY-MM.yaml` entry file with example
entries. Refuses to overwrite if `conf.yaml` already exists.

```
bp init .
bp init ~/my-budget
```

After running `init`, edit `conf.yaml` to fill in your real paycheck
day/amount and current bank balance.

### `bp import <html_file> <output.yaml>` - import from Klarna

Parses a saved Klarna "Manage Payments" HTML page and extracts all payment
entries into a YAML file compatible with `bp`.

```
bp import ~/Downloads/Klarna.html klarna.yaml
```

Save the page from https://app.klarna.com/manage-payments as a complete
HTML file, then point `bp import` at it.

Each imported entry includes:

| Field | Description |
|-------|-------------|
| `date` | Payment date |
| `amount` | Amount (negative, since these are payments) |
| `note` | Merchant name |
| `installment` | e.g. "2 of 3 (64 EUR)" (if applicable) |
| `status` | `paid` or `scheduled` |
| `source` | `klarna` |

Paid entries from the past are automatically excluded when you run `bp`,
since they are already reflected in your bank balance. Scheduled (upcoming)
entries are shown as future expenses.

## Financial month

A "financial month" starts on your paycheck day and ends the day before the
next paycheck. For example, if you get paid on the 25th, the current
financial month runs from the 25th of last month to the 24th of this month.

The `-m` flag controls how many financial months to project forward. `bp .`
defaults to 1.

## Tips

- Keep `conf.yaml` balance up to date - the accuracy of projections depends
  on it.
- Name entry files however you like: by month (`2026-04.yaml`), by category
  (`groceries.yaml`), or by source (`klarna.yaml`). `bp` reads all of them.
- Pipe to other tools: `bp -f json . | jq '.events[] | select(.amount < -100)'`
  to find large expenses.
- Colors are automatic when outputting to a terminal. Set `NO_COLOR=1` to
  disable, or use `-f md` / `-f json` for plain output.
