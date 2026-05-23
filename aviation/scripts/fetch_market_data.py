#!/usr/bin/env python3
# coding: utf-8
"""
航空業界関連マーケットデータを収集し market_data.json に書き出す
- リース会社株・主要航空株・製造会社株: yfinance
- SOFR: NY Fed 公開 API
- 米10年国債利回り: yfinance (^TNX)
- Brent / WTI 原油先物: yfinance
"""

import json
import os
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

LESSOR_STOCKS = [
    {"symbol": "AER",     "name": "AerCap",      "currency": "USD"},
    {"symbol": "AL",      "name": "Air Lease",   "currency": "USD"},
    {"symbol": "2588.HK", "name": "BOC Aviation","currency": "HKD"},
]

AIRLINE_STOCKS = [
    {"symbol": "UAL",    "name": "United",   "currency": "USD"},
    {"symbol": "DAL",    "name": "Delta",    "currency": "USD"},
    {"symbol": "AAL",    "name": "American", "currency": "USD"},
    {"symbol": "RYAAY",  "name": "Ryanair",  "currency": "USD"},
    {"symbol": "9202.T", "name": "ANA",      "currency": "JPY"},
    {"symbol": "9201.T", "name": "JAL",      "currency": "JPY"},
]

MFR_STOCKS = [
    {"symbol": "BA",     "name": "Boeing",  "currency": "USD"},
    {"symbol": "AIR.PA", "name": "Airbus",  "currency": "EUR"},
]

COMMODITY_TICKERS = [
    {"symbol": "BZ=F", "name": "Brent原油", "unit": "USD/bbl"},
    {"symbol": "CL=F", "name": "WTI原油",   "unit": "USD/bbl"},
]


def fetch_stock(info):
    try:
        hist = yf.Ticker(info["symbol"]).history(period="5d")
        if hist.empty or len(hist) < 1:
            return None
        price_now  = float(hist.iloc[-1]["Close"])
        price_prev = float(hist.iloc[-2]["Close"]) if len(hist) >= 2 else None
        change     = round(price_now - price_prev, 2)        if price_prev else None
        change_pct = round(change / price_prev * 100, 2)     if price_prev else None
        return {
            "symbol":     info["symbol"],
            "name":       info["name"],
            "currency":   info["currency"],
            "price":      round(price_now, 2),
            "change":     change,
            "change_pct": change_pct,
            "date":       hist.index[-1].strftime("%Y-%m-%d"),
        }
    except Exception as e:
        print(f"  [SKIP stock] {info['symbol']}: {e}")
        return None


def fetch_commodity(info):
    try:
        hist = yf.Ticker(info["symbol"]).history(period="5d")
        if hist.empty or len(hist) < 1:
            return None
        price_now  = float(hist.iloc[-1]["Close"])
        price_prev = float(hist.iloc[-2]["Close"]) if len(hist) >= 2 else None
        change_pct = round((price_now - price_prev) / price_prev * 100, 2) if price_prev else None
        return {
            "name":       info["name"],
            "unit":       info["unit"],
            "price":      round(price_now, 2),
            "change_pct": change_pct,
            "date":       hist.index[-1].strftime("%Y-%m-%d"),
        }
    except Exception as e:
        print(f"  [SKIP commodity] {info['symbol']}: {e}")
        return None


def fetch_sofr():
    try:
        url  = "https://markets.newyorkfed.org/api/rates/sofr/last/1.json"
        data = requests.get(url, timeout=10).json()
        rate = data["refRates"][0]
        return {
            "name":  "SOFR",
            "value": round(float(rate["percentRate"]), 2),
            "unit":  "%",
            "date":  rate["effectiveDate"],
        }
    except Exception as e:
        print(f"  [SKIP] SOFR: {e}")
        return None


def fetch_yield(symbol, name):
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist.empty:
            return None
        value_now  = float(hist.iloc[-1]["Close"])
        value_prev = float(hist.iloc[-2]["Close"]) if len(hist) >= 2 else None
        change     = round(value_now - value_prev, 3) if value_prev else None
        return {
            "name":   name,
            "value":  round(value_now, 3),
            "unit":   "%",
            "change": change,
            "date":   hist.index[-1].strftime("%Y-%m-%d"),
        }
    except Exception as e:
        print(f"  [SKIP yield] {symbol}: {e}")
        return None


def main():
    print("マーケットデータ取得中...")

    lessor_stocks  = [r for t in LESSOR_STOCKS  for r in [fetch_stock(t)]    if r]
    airline_stocks = [r for t in AIRLINE_STOCKS for r in [fetch_stock(t)]    if r]
    mfr_stocks     = [r for t in MFR_STOCKS     for r in [fetch_stock(t)]    if r]
    commodities    = [r for t in COMMODITY_TICKERS for r in [fetch_commodity(t)] if r]

    rates = []
    for fn in [fetch_sofr,
               lambda: fetch_yield("^TNX", "米10年債"),
               lambda: fetch_yield("^IRX", "米3ヶ月債")]:
        r = fn()
        if r:
            rates.append(r)

    now    = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    output = {
        "updated_at_jst": now,
        "lessor_stocks":  lessor_stocks,
        "airline_stocks": airline_stocks,
        "mfr_stocks":     mfr_stocks,
        "commodities":    commodities,
        "rates":          rates,
    }

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(os.path.dirname(script_dir), "market_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = len(lessor_stocks) + len(airline_stocks) + len(mfr_stocks) + len(commodities) + len(rates)
    print(f"Done. {total} items saved → {output_path}")


if __name__ == "__main__":
    main()
