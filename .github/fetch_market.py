#!/usr/bin/env python3
"""Incrementally update StockScope historical prices from the symbol catalog.

The catalog is a search index, not a guarantee of Yahoo Finance price coverage.
Keep previously downloaded bars if individual requests fail.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "symbol-catalog.json"
TARGET = ROOT / "market-data.json"
NEW_PER_RUN = 12
REFRESH_PER_RUN = 6
NEW_HISTORY = "2y"
REFRESH_HISTORY = "3mo"


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def ticker_key(ticker):
    ticker = ticker.upper().strip()
    symbol = ticker.split(".")[0]
    market = "TW" if ticker.endswith((".TW", ".TWO")) else "US"
    return (market, symbol)


def download(ticker, period):
    frame = yf.Ticker(ticker).history(
        period=period, interval="1d", auto_adjust=True,
        actions=False, timeout=25
    )
    if frame is None or frame.empty:
        raise ValueError("no daily prices returned")
    market, symbol = ticker_key(ticker)
    bars = []
    for day, row in frame.iterrows():
        vals = [float(row[k]) for k in ("Open", "High", "Low", "Close")]
        if not all(pd.notna(x) and x > 0 for x in vals):
            continue
        if vals[1] < max(vals[0], vals[3]) or vals[2] > min(vals[0], vals[3]):
            continue
        volume = row.get("Volume", 0)
        bars.append({
            "date": day.strftime("%Y-%m-%d"),
            "symbol": symbol, "market": market,
            "open": round(vals[0], 5), "high": round(vals[1], 5),
            "low": round(vals[2], 5), "close": round(vals[3], 5),
            "volume": int(volume) if pd.notna(volume) else 0,
        })
    if len(bars) < 10:
        raise ValueError("fewer than 10 valid trading days")
    return bars


def main():
    if not CATALOG.exists():
        sys.exit("symbol-catalog.json missing: run catalog workflow first")

    catalog = load_json(CATALOG, {})
    if not isinstance(catalog.get("stocks"), list):
        sys.exit("Invalid symbol catalog: missing stocks list")

    favorites = []
    symbols_file = ROOT / "symbols.txt"
    if symbols_file.exists():
        favorites = [
            line.strip().upper() for line in
            symbols_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    catalog_tickers = [
        str(item.get("ticker", "")).strip().upper()
        for item in catalog["stocks"] if isinstance(item, dict)
    ]
    # Existing watchlist first; the remainder are listed and OTC stocks.
    tickers = list(dict.fromkeys(t for t in favorites + catalog_tickers if t))
    if not tickers:
        sys.exit("No tickers in catalog")

    old = load_json(TARGET, {})
    if old and old.get("schema") != 1:
        sys.exit("Existing market-data.json has an unsupported schema")

    old_rows = old.get("rows", [])
    if not isinstance(old_rows, list):
        sys.exit("Existing market-data.json has invalid rows")
    bars_by_key = {}
    for bar in old_rows:
        if not isinstance(bar, dict):
            continue
        key = (bar.get("market"), bar.get("symbol"))
        bars_by_key.setdefault(key, {})[bar.get("date")] = bar

    known = {ticker_key(t) for t in tickers if ticker_key(t) in bars_by_key}
    # Persist a cursor so failed symbols do not block the queue forever.
    cursor = int(old.get("catalog_cursor", 0)) % len(tickers)
    new_candidates = []
    checked = 0
    while checked < len(tickers) and len(new_candidates) < NEW_PER_RUN:
        ticker = tickers[(cursor + checked) % len(tickers)]
        if ticker_key(ticker) not in known:
            new_candidates.append(ticker)
        checked += 1
    next_cursor = (cursor + checked) % len(tickers)

    existing_tickers = [t for t in tickers if ticker_key(t) in known]
    refresh_cursor = int(old.get("refresh_cursor", 0))
    refresh = []
    if existing_tickers:
        for n in range(min(REFRESH_PER_RUN, len(existing_tickers))):
            refresh.append(existing_tickers[(refresh_cursor + n) % len(existing_tickers)])
    next_refresh = (refresh_cursor + len(refresh)) % max(1, len(existing_tickers))

    attempted = [(t, NEW_HISTORY) for t in new_candidates]
    attempted += [(t, REFRESH_HISTORY) for t in refresh if t not in new_candidates]
    errors = []
    success = []
    for ticker, period in attempted:
        try:
            downloaded = download(ticker, period)
            key = ticker_key(ticker)
            existing = bars_by_key.setdefault(key, {})
            for bar in downloaded:
                existing[bar["date"]] = bar
            success.append(ticker)
            print(f"OK {ticker}: {len(downloaded)} bars")
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)[:180]})
            print(f"SKIP {ticker}: {exc}", file=sys.stderr)

    if not bars_by_key:
        sys.exit("No usable historical data; refusing to overwrite snapshot")

    rows = [
        bar for daily in bars_by_key.values() for bar in daily.values()
        if isinstance(bar, dict) and bar.get("date")
    ]
    rows.sort(key=lambda r: (str(r["market"]), str(r["symbol"]), str(r["date"])))
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    output = {
        "schema": 1,
        "generated_at": now,
        "provider": "Yahoo Finance via yfinance (unofficial; delayed historical data)",
        "price_basis": "auto_adjust=True (adjusted OHLC); historical corporate action adjustments can change",
        "symbols_requested": len(tickers),
        "symbols_success": sorted(
            {t for t in tickers if ticker_key(t) in bars_by_key}
        ),
        "errors": errors,
        "catalog_cursor": next_cursor,
        "refresh_cursor": next_refresh,
        "rows": rows,
    }
    temp = ROOT / "market-data.json.tmp"
    temp.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, TARGET)
    print(
        f"Saved {len(rows)} bars for {len(bars_by_key)} symbols; "
        f"{len(success)} updated, {len(errors)} failed. "
        "Catalog-only symbols may still lack price data."
    )


if __name__ == "__main__":
    main()
