#!/usr/bin/env python3
"""Build a searchable TWSE/TPEx catalog and retain the existing US watchlist.

This script does not download prices or change market-data.json.
"""
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ("TWSE", ".TW", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
    ("TPEx", ".TWO", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"),
]


def fetch_json(url, attempts=5):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; StockScope/0.5; catalog fetch)",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()  # Raises IncompleteRead if server closes early.
                charset = response.headers.get_content_charset() or "utf-8"
            records = json.loads(raw.decode(charset))
            if not isinstance(records, list):
                raise ValueError("Unexpected API response: expected JSON array")
            return records
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"Fetch attempt {attempt}/{attempts} failed: {type(exc).__name__}: {exc}", flush=True)
            if attempt < attempts:
                time.sleep(min(20, 2 ** attempt) + random.uniform(0, 1))
    raise RuntimeError(f"Download failed after {attempts} attempts: {last_error}")


def build():
    items = []
    errors = []
    for exchange, suffix, url in SOURCES:
        try:
            records = fetch_json(url)
            exchange_items = []
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                code = str(rec.get("公司代號", "")).strip()
                name = str(rec.get("公司名稱", "") or rec.get("公司簡稱", "")).strip()
                if not re.fullmatch(r"\d{4,6}", code) or not name:
                    continue
                exchange_items.append({
                    "symbol": code, "ticker": code + suffix, "name": name,
                    "market": "TW", "exchange": exchange,
                })
            if len(exchange_items) < 100:
                raise ValueError(f"Too few stocks parsed from {exchange}: {len(exchange_items)}")
            items.extend(exchange_items)
            print(f"{exchange}: parsed {len(exchange_items)} symbols", flush=True)
        except Exception as exc:
            errors.append(f"{exchange}: {exc}")

    symbols_file = ROOT / "symbols.txt"
    if symbols_file.exists():
        for raw in symbols_file.read_text(encoding="utf-8").splitlines():
            ticker = raw.strip().upper()
            if ticker and not ticker.startswith("#") and not ticker.endswith((".TW", ".TWO")):
                if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,12}", ticker):
                    items.append({
                        "symbol": ticker, "ticker": ticker, "name": ticker,
                        "market": "US", "exchange": "US (existing list)",
                    })

    if errors:
        raise RuntimeError("Stock catalog generation incomplete: " + "; ".join(errors))

    unique = {item["ticker"]: item for item in items}
    if len(unique) < 200:
        raise RuntimeError(f"Suspiciously small catalog: {len(unique)}")

    output = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "description": "Searchable ticker catalog, not price data",
        "us_coverage": "existing symbols.txt only",
        "stocks": sorted(unique.values(), key=lambda x: (x["market"], x["symbol"], x["exchange"])),
    }
    target = ROOT / "symbol-catalog.json"
    temporary = ROOT / "symbol-catalog.json.tmp"
    temporary.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)
    print(f"Created {target.name}: {len(unique)} symbols", flush=True)


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        sys.exit(str(exc))
