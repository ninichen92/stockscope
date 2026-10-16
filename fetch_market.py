#!/usr/bin/env python3
"""Download verifiable source-attributed delayed daily OHLC; fail closed on errors."""
import json, os, datetime, sys
from pathlib import Path
import yfinance as yf
import pandas as pd
ROOT=Path(__file__).resolve().parent
symbols=[s.strip() for s in (ROOT/'symbols.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
rows=[];errors=[];success=[]
for ticker in symbols:
    try:
        frame=yf.Ticker(ticker).history(period='6y',interval='1d',auto_adjust=True,actions=False,timeout=25)
        if frame is None or len(frame)<100:raise ValueError('fewer than 100 trading days')
        symbol=ticker.split('.')[0].upper(); market='TW' if ticker.endswith(('.TW','.TWO')) else 'US'
        for dt,r in frame.iterrows():
            vals=[float(r[k]) for k in ['Open','High','Low','Close']]
            if not all(pd.notna(x) and x>0 for x in vals):continue
            if vals[1]<max(vals[0],vals[3]) or vals[2]>min(vals[0],vals[3]):continue
            rows.append({'date':dt.strftime('%Y-%m-%d'),'symbol':symbol,'market':market,'open':round(vals[0],5),'high':round(vals[1],5),'low':round(vals[2],5),'close':round(vals[3],5),'volume':int(r['Volume']) if pd.notna(r['Volume']) else 0})
        success.append(ticker)
    except Exception as e:errors.append({'ticker':ticker,'error':str(e)[:180]})
if not success or len(rows)<100:sys.exit('No usable data; refusing to overwrite existing snapshot')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
output={'schema':1,'generated_at':now,'provider':'Yahoo Finance via yfinance (unofficial; delayed historical data)','price_basis':'auto_adjust=True (adjusted OHLC); historical corporate action adjustments can change','symbols_requested':len(symbols),'symbols_success':success,'errors':errors,'rows':rows}
target=ROOT/'market-data.json';temp=ROOT/'market-data.json.tmp';temp.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')));os.replace(temp,target)
print(f'Updated {len(success)} symbols and {len(rows)} bars; {len(errors)} failures')
