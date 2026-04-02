from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import yaml

MONTH_MAP: dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    "January": 1, "February": 2, "March": 3, "April": 4, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10,
    "November": 11, "December": 12,
}
# "May" already covered by the short form

_AMOUNT_RE = re.compile(r"^([\d.]+,\d{2})\s*€$")
_PAID_RE = re.compile(r"^Paid (\d+) (\w+)$")
_SECTION_PAID_RE = re.compile(r"^Paid in (\w+)(?:\s+(\d{4}))?$")
_SECTION_DUE_RE = re.compile(r"^Due in (\w+)$")
_INSTALLMENT_RE = re.compile(r"^\d+(?:-\d+)? of \d+")


# ------------------------------------------------------------------
# HTML text extraction
# ------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []

    def handle_data(self, data: str) -> None:
        d = data.strip()
        if d:
            self.texts.append(d)


def _extract_texts(path: Path) -> list[str]:
    parser = _TextExtractor()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.texts


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _is_amount(text: str) -> bool:
    return bool(_AMOUNT_RE.match(text))


def _parse_amount(text: str) -> float:
    m = _AMOUNT_RE.match(text)
    if not m:
        raise ValueError(f"Not an amount: {text!r}")
    raw = m.group(1)
    # European format: 1.234,56 -> 1234.56
    return float(raw.replace(".", "").replace(",", "."))


def _find_start(texts: list[str]) -> int:
    for i, t in enumerate(texts):
        if (t == "Due within 7 days"
                or _SECTION_DUE_RE.match(t)
                or t == "Completed"
                or _SECTION_PAID_RE.match(t)):
            return i
    return len(texts)


# ------------------------------------------------------------------
# Parser
# ------------------------------------------------------------------

def parse_klarna(path: Path) -> list[dict]:
    texts = _extract_texts(path)
    entries: list[dict] = []

    start = _find_start(texts)
    end = len(texts)
    current_year = date.today().year
    section_year = current_year
    i = start

    while i < end:
        t = texts[i]

        # ---- section headers ----

        if t in ("Due within 7 days", "Completed"):
            section_year = current_year
            i += 1
            if i < end and _is_amount(texts[i]):
                i += 1  # skip section total
            continue

        dm = _SECTION_DUE_RE.match(t)
        if dm:
            section_year = current_year
            i += 1
            if i < end and _is_amount(texts[i]):
                i += 1
            continue

        sm = _SECTION_PAID_RE.match(t)
        if sm:
            if sm.group(2):
                section_year = int(sm.group(2))
            i += 1
            if i < end and texts[i] == "\u00b7":   # middle dot separator
                i += 1
            if i < end and _is_amount(texts[i]):
                i += 1
            continue

        # ---- upcoming entry: Month  Day  Merchant  ...  Amount ----

        if t in MONTH_MAP and i + 2 < end and texts[i + 1].isdigit():
            month = MONTH_MAP[t]
            day = int(texts[i + 1])
            merchant = texts[i + 2]
            year = current_year
            j = i + 3
            installment = None
            while j < min(i + 12, end):
                if _INSTALLMENT_RE.match(texts[j]):
                    installment = texts[j]
                if _is_amount(texts[j]):
                    entries.append(_make_entry(
                        year, month, day, merchant,
                        _parse_amount(texts[j]),
                        "scheduled", installment,
                    ))
                    i = j + 1
                    break
                j += 1
            else:
                i += 1
            continue

        # ---- completed entry: Merchant  "Paid DD Mon"  ...  Amount ----

        if i + 1 < end:
            pm = _PAID_RE.match(texts[i + 1])
            if pm and pm.group(2) in MONTH_MAP:
                merchant = t
                day = int(pm.group(1))
                month = MONTH_MAP[pm.group(2)]
                j = i + 2
                installment = None
                while j < min(i + 10, end):
                    if _INSTALLMENT_RE.match(texts[j]):
                        installment = texts[j]
                    if _is_amount(texts[j]):
                        entries.append(_make_entry(
                            section_year, month, day, merchant,
                            _parse_amount(texts[j]),
                            "paid", installment,
                        ))
                        i = j + 1
                        break
                    j += 1
                else:
                    i += 1
                continue

        i += 1

    return entries


def _make_entry(year: int, month: int, day: int, merchant: str,
                amount: float, status: str,
                installment: str | None) -> dict:
    entry: dict = {
        "date": date(year, month, day),
        "amount": -amount,
        "note": merchant,
    }
    if installment:
        entry["installment"] = installment
    entry["status"] = status
    entry["source"] = "klarna"
    return entry


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def run_import(html_path: Path, output_path: Path) -> None:
    if not html_path.exists():
        raise SystemExit(f"Error: {html_path} not found")

    entries = parse_klarna(html_path)

    if not entries:
        raise SystemExit("Error: no payment entries found in the HTML file")

    entries.sort(key=lambda e: e["date"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(f"# Imported from Klarna on {date.today().isoformat()}\n")
        f.write(f"# Source: {html_path.name}\n\n")
        yaml.dump(entries, f,
                  default_flow_style=False, sort_keys=False, allow_unicode=True)

    paid = sum(1 for e in entries if e.get("status") == "paid")
    scheduled = sum(1 for e in entries if e.get("status") == "scheduled")
    total = sum(e["amount"] for e in entries)

    print(f"Imported {len(entries)} entries to {output_path}")
    print(f"  {paid} paid, {scheduled} scheduled")
    print(f"  Total: {total:,.2f}")
