#!/usr/bin/env python3
"""Build a searchable Taiwan listed/OTC stock catalog, plus existing US tickers.

Does not fetch prices or modify market-data.json.
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ("TWSE", ".TW", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
    ("TPEx", ".TWO", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"),
]


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "StockScope/0.5 (stock catalog)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def build():
    items = []
    errors = []
    for exchange, suffix, url in SOURCES:
        try:
            records = fetch_json(url)
            if not isinstance(records, list):
                raise ValueError("Unexpected API response: expected array")
            added = 0
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                code = str(rec.get("公司代號", "")).strip()
                name = str(rec.get("公司名稱", "") or rec.get("公司簡稱", "")).strip()
                if not re.fullmatch(r"\d{4,6}", code) or not name:
                    continue
                items.append({"symbol": code, "ticker": code + suffix, "name": name, "market": "TW", "exchange": exchange})
                added += 1
            if added < 100:
                raise ValueError(f"Too few stocks parsed from {exchange}: {added}")
        except Exception as exc:
            errors.append(f"{exchange}: {exc}")
    # Existing US watchlist only; complete US listings will be added separately.
    symbols_file = ROOT / "symbols.txt"
    if symbols_file.exists():
        for raw in symbols_file.read_text(encoding="utf-8").splitlines():
            ticker = raw.strip().upper()
            if ticker and not ticker.startswith("#") and not ticker.endswith((".TW", ".TWO")):
                if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,12}", ticker):
                    items.append({"symbol": ticker, "ticker": ticker, "name": ticker, "market": "US", "exchange": "US (existing list)"})
    if errors:
        # Fail closed: never overwrite a valid catalog with a partial catalog.
        raise RuntimeError("Stock catalog generation incomplete: " + "; ".join(errors))
    unique = {x["ticker"]: x for x in items}
    if len(unique) < 200:
        raise RuntimeError(f"Suspiciously small catalog: {len(unique)}")
    output = {"schema": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "description": "Searchable ticker catalog, not price data", "us_coverage": "existing symbols.txt only", "stocks": sorted(unique.values(), key=lambda x: (x["market"], x["symbol"], x["exchange"]))}
    target = ROOT / "symbol-catalog.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(target)
    print(f"Created {target.name}: {len(unique)} symbols")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        sys.exit(str(exc))
