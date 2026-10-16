# StockScope v0.4 — Daily market snapshot edition

## What it does
- Merges the v0.3 research view, watchlist, triple-MA screen, 20-session backtest and daily support/resistance levels.
- Fetches historical daily OHLC through the unofficial `yfinance` Yahoo Finance client, then writes a source-labelled `market-data.json` snapshot.
- Browser loads the snapshot on each visit. **No claim of live intraday pricing.** Without snapshot, the app clearly remains in simulation mode.

## Deploy to GitHub Pages
1. Create a new public GitHub repository; upload the **contents** of this directory at its root (including `.github/workflows/daily.yml`).
2. In repository Settings → Actions → General, allow workflows. Set Workflow permissions to **Read and write permissions** (needed for commit).
3. In Actions, manually run **Daily stock data refresh** once; confirm `market-data.json` appears in the repository.
4. In Settings → Pages, choose Deploy from a branch, `main` / root. Open the published Pages URL after deployment.
5. The two scheduled runs refresh Taiwan and US market snapshots on weekdays, subject to GitHub Actions scheduling delays and source availability. Check the generated time and latest session displayed by the app.

## Local test
`python -m pip install -r requirements.txt` then `python fetch_market.py`, followed by `python -m http.server 8000`. Open `http://localhost:8000/`. Internet access is required for fetching.

## Caveats
- Yahoo Finance/yfinance is unofficial, subject to throttling, outages, coverage gaps and licensing. Check provider terms before public/commercial redistribution.
- `symbols.txt` is a starter watch universe, **not all listed stocks**. Extend with .TW or .TWO for Taiwan, and US tickers for US. Large universes require rate limits, retry logic and preferably a licensed feed.
- `auto_adjust=True` yields adjusted historical OHLC. Research levels use adjusted price scale and may differ from tradable raw exchange prices after splits/dividends. Production should maintain separate adjusted backtest and unadjusted live price datasets.
- Signals are confirmed after the close; next session open entry avoids look-ahead. No guarantee of fills at limit-up/down, liquidity, taxes, slippage or market impact. Ranking reflects historical outcomes, not forecast win probability.
- Backtest is in-browser and scans only the tickers included in the snapshot. Max drawdown is per-trade, not portfolio-level. Avoid overfitting; use out-of-sample tests.
- This repository has **not been deployed or live-data-verified** in this environment.
