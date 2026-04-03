from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


def _clean_note(desc: str) -> str:
    """Strip common Poste transaction-type prefixes."""
    for prefix in ("PAGAMENTO POS ", "PAGAMENTO E-COMMERCE "):
        if desc.startswith(prefix):
            return desc[len(prefix):]
    return desc


def _is_klarna(desc: str) -> bool:
    return "klarna" in desc.lower()


def _to_date(val) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


_DEFAULT_MERGE_TOLERANCE_DAYS = 2


def _load_import_settings(directory: Path) -> dict:
    """Load the 'import' section from conf.yaml, falling back to defaults."""
    conf = directory / "conf.yaml"
    if not conf.exists():
        return {}
    with open(conf) as f:
        raw = yaml.safe_load(f)
    return (raw or {}).get("import", {}) or {}


def _read_header(path: Path) -> str:
    """Read leading comment and blank lines from a YAML file."""
    lines: list[str] = []
    with open(path) as f:
        for line in f:
            if line.startswith("#") or line.strip() == "":
                lines.append(line)
            else:
                break
    return "".join(lines)


def _load_klarna_files(directory: Path) -> dict[Path, tuple[str, Any]]:
    """Load YAML files containing klarna entries.

    Returns ``{path: (header_text, parsed_data)}``.
    """
    files: dict[Path, tuple[str, Any]] = {}
    for ext in ("*.yaml", "*.yml"):
        for path in sorted(directory.glob(ext)):
            if path.name.startswith("conf."):
                continue
            header = _read_header(path)
            with open(path) as f:
                raw = yaml.safe_load(f)
            if raw is None:
                continue

            file_source = None
            if isinstance(raw, dict):
                file_source = raw.get("source")
                items = raw.get("entries", [])
            else:
                items = raw or []

            has_klarna = any(
                file_source == "klarna" or item.get("source") == "klarna"
                for item in items
            )
            if has_klarna:
                files[path] = (header, raw)
    return files


# ------------------------------------------------------------------
# XLSX parser
# ------------------------------------------------------------------

def parse_poste(xlsx_path: Path) -> list[dict]:
    """Parse a Poste Italiane movements XLSX into entry dicts.

    Uses *Data Valuta* as the entry date and *Importo* as the amount.
    """
    try:
        import openpyxl
    except ImportError:
        raise SystemExit(
            "Error: openpyxl is required for XLSX import.\n"
            "Install it with: pip install openpyxl")

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active

    entries: list[dict] = []
    header_found = False

    for row in ws.iter_rows(values_only=True):
        if not header_found:
            if row and row[0] == "Data Contabile":
                header_found = True
            continue

        if len(row) < 4:
            continue
        data_contabile, data_valuta, importo, descrizione = row[:4]
        if data_valuta is None or importo is None:
            continue

        dv = _to_date(data_valuta)
        dc = _to_date(data_contabile) if data_contabile else dv
        raw_desc = str(descrizione or "").strip()

        entries.append({
            "date": dv,
            "amount": round(float(importo), 2),
            "note": _clean_note(raw_desc),
            "data_contabile": dc,
            "status": "paid",
            "source": "poste",
        })

    wb.close()
    return entries


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def run_import(xlsx_path: Path, output_path: Path) -> None:
    if not xlsx_path.exists():
        raise SystemExit(f"Error: {xlsx_path} not found")

    all_entries = parse_poste(xlsx_path)
    if not all_entries:
        raise SystemExit("Error: no entries found in the XLSX file")

    # Load import settings from conf.yaml
    out_dir = output_path.parent
    import_settings = _load_import_settings(out_dir)
    tolerance = int(import_settings.get(
        "merge_tolerance_days", _DEFAULT_MERGE_TOLERANCE_DAYS))

    # Load klarna files (with headers for later write-back)
    klarna_files = _load_klarna_files(out_dir) if out_dir.exists() else {}

    # Build a consumable pool with references to the actual entry dicts
    klarna_pool: list[tuple[date, float, dict, Path]] = []
    for path, (_hdr, raw) in klarna_files.items():
        file_source = raw.get("source") if isinstance(raw, dict) else None
        items = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
        for item in items:
            if file_source == "klarna" or item.get("source") == "klarna":
                kd = _to_date(item["date"])
                ka = round(float(item["amount"]), 2)
                klarna_pool.append((kd, ka, item, path))

    modified_paths: set[Path] = set()
    matched: list[dict] = []
    output_entries: list[dict] = []

    for entry in all_entries:
        if _is_klarna(entry["note"]):
            # Try to match against a klarna entry (same amount, date ±tolerance)
            amt = entry["amount"]
            dv = entry["date"]
            found = False
            for i, (kd, ka, kentry, kpath) in enumerate(klarna_pool):
                if ka == amt and abs((dv - kd).days) <= tolerance:
                    klarna_pool.pop(i)
                    kentry["merged"] = True
                    modified_paths.add(kpath)
                    matched.append(entry)
                    found = True
                    break
            if not found:
                # Unmatched (e.g. refunds) — keep in output
                output_entries.append(entry)
        else:
            output_entries.append(entry)

    # Write back klarna files that had entries marked as merged
    for path in modified_paths:
        header, raw = klarna_files[path]
        with open(path, "w") as f:
            if header:
                f.write(header)
            yaml.dump(raw, f,
                      default_flow_style=False, sort_keys=False,
                      allow_unicode=True)

    output_entries.sort(key=lambda e: e["date"])

    # Write poste YAML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = {"source": "poste", "entries": output_entries}

    with open(output_path, "w") as f:
        f.write(f"# Imported from Poste Italiane on {date.today().isoformat()}\n")
        f.write(f"# Source: {xlsx_path.name}\n\n")
        yaml.dump(output, f,
                  default_flow_style=False, sort_keys=False, allow_unicode=True)

    total = sum(e["amount"] for e in output_entries)
    klarna_total = sum(e["amount"] for e in matched)

    print(f"Imported {len(output_entries)} entries to {output_path}")
    print(f"  Marked {len(matched)} klarna entries as merged"
          f" (total: {klarna_total:,.2f})")
    print(f"  Total: {total:,.2f}")
