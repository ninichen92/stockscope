#!/usr/bin/env python3
"""Build StockScope searchable stock catalog (not price data).

Official TWSE JSON for listed stocks; TPEx JSON with official MOPS CSV fallback
for OTC stocks. An incomplete response never replaces an existing catalog.
"""
import csv
import datetime as dt
import io
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TWSE_URL = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
TPEX_URL = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O'
OTC_CSV_URL = 'https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv'


def download(url, attempts=3):
    last = None
    for n in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (StockScope/0.5; stock catalog)',
                'Accept': 'application/json,text/csv,*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'close',
            })
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()
            if len(data) < 500:
                raise ValueError(f'Suspiciously short response: {len(data)} bytes')
            return data
        except Exception as exc:
            last = exc
            print(f'{url} attempt {n}/{attempts}: {type(exc).__name__}: {exc}', flush=True)
            if n < attempts:
                time.sleep(min(8, 2 ** n) + random.uniform(0, 0.5))
    raise RuntimeError(f'{url}: {last}')


def decode_bytes(data):
    for enc in ('utf-8-sig', 'cp950'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    raise ValueError('Neither UTF-8 nor Big5/CP950 could decode response')


def read_json(url):
    obj = json.loads(decode_bytes(download(url)))
    if not isinstance(obj, list):
        raise ValueError('Expected JSON array')
    return obj


def read_csv(url):
    text = decode_bytes(download(url))
    return list(csv.DictReader(io.StringIO(text)))


def parse(records, exchange, suffix):
    found = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        code = str(rec.get('公司代號') or rec.get('SecuritiesCompanyCode') or '').strip()
        name = str(rec.get('公司簡稱') or rec.get('公司名稱') or rec.get('CompanyAbbreviation') or rec.get('CompanyName') or '').strip()
        if re.fullmatch(r'\d{4}', code) and name:
            ticker = code + suffix
            found[ticker] = {'symbol': code, 'ticker': ticker, 'name': name, 'market': 'TW', 'exchange': exchange}
    if len(found) < 500:
        raise ValueError(f'{exchange}: only {len(found)} valid four-digit stocks; refusing partial catalog')
    return list(found.values())


def otc_stocks():
    errors = []
    for label, loader, url in (
        ('TPEx OpenAPI', read_json, TPEX_URL),
        ('MOPS official CSV fallback', read_csv, OTC_CSV_URL),
    ):
        try:
            result = parse(loader(url), 'TPEx', '.TWO')
            print(f'TPEx: {len(result)} stocks from {label}', flush=True)
            return result, label
        except Exception as exc:
            errors.append(f'{label}: {exc}')
            print(f'{label} unavailable: {exc}', flush=True)
    raise RuntimeError('Both OTC sources failed: ' + '; '.join(errors))


def build():
    listed = parse(read_json(TWSE_URL), 'TWSE', '.TW')
    print(f'TWSE: {len(listed)} stocks', flush=True)
    otc, otc_source = otc_stocks()
    items = listed + otc
    symbols_file = ROOT / 'symbols.txt'
    if symbols_file.exists():
        for raw in symbols_file.read_text(encoding='utf-8').splitlines():
            ticker = raw.strip().upper()
            if ticker and not ticker.startswith('#') and not ticker.endswith(('.TW', '.TWO')):
                if re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,12}', ticker):
                    items.append({'symbol': ticker, 'ticker': ticker, 'name': ticker,
                                  'market': 'US', 'exchange': 'US (existing list)'})
    unique = {x['ticker']: x for x in items}
    if len(unique) < 1500:
        raise RuntimeError(f'Suspiciously small catalog: {len(unique)}')
    output = {
        'schema': 1,
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'description': 'Searchable ticker catalog, not price data',
        'us_coverage': 'existing symbols.txt only',
        'sources': {'TWSE': TWSE_URL, 'TPEx': otc_source},
        'stocks': sorted(unique.values(), key=lambda x: (x['market'], x['symbol'], x['exchange'])),
    }
    target = ROOT / 'symbol-catalog.json'
    temp = ROOT / 'symbol-catalog.json.tmp'
    temp.write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(target)
    print(f'Created {target.name}: {len(unique)} symbols', flush=True)


if __name__ == '__main__':
    try:
        build()
    except Exception as exc:
        sys.exit(str(exc))
