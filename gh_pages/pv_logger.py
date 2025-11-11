#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import time
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

JST = ZoneInfo("Asia/Tokyo")

@dataclass
class Cfg:
    login_url: str
    dashboard_url: str
    username: str
    password: str
    us: str; ps: str; sb: str
    time_sel: str
    sels: List[str]
    data_csv: Path

def load_cfg() -> Cfg:
    login = os.getenv("LOGIN_URL", "https://d1hcvh8gvguktg.cloudfront.net/login.html")
    dash  = os.getenv("DASHBOARD_URL", "https://d1hcvh8gvguktg.cloudfront.net/index.html")
    user  = os.getenv("USERNAME", os.getenv("PV_USERNAME", ""))
    pw    = os.getenv("PASSWORD", os.getenv("PV_PASSWORD", ""))
    if not user or not pw:
        raise SystemExit("PV_USERNAME/PV_PASSWORD 未設定")
    us = os.getenv("USERNAME_SELECTOR", "input[name='username']")
    ps = os.getenv("PASSWORD_SELECTOR", "input[name='password']")
    sb = os.getenv("SUBMIT_SELECTOR", ".login-btnArea button")
    time_sel = os.getenv("TIME_SELECTOR", ".measurementWidget .updateTime")
    sels = [s.strip() for s in os.getenv("METRIC_SELECTORS",
        "span.value.todaySellPower,span.value.todayBuyPower,span.value.todayConsPower,span.value.todaySelfConsPower,span.value.todayGeneratedPower"
    ).split(",")]
    if len(sels) < 5:
        raise SystemExit("METRIC_SELECTORS は5本必要です")
    data_csv = Path("gh_pages/data/pv_log.csv")
    data_csv.parent.mkdir(parents=True, exist_ok=True)
    return Cfg(login, dash, user, pw, us, ps, sb, time_sel, sels, data_csv)

def to_f(x: str):
    if not x: return None
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", x.replace(",", ""))
    return float(m.group(0)) if m else None

def parse_time(s: str):
    s = (s or "").replace("現在", "").strip()
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=JST)
        except:
            pass
    return None

def run_once():
    cfg = load_cfg()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(cfg.login_url, timeout=30000)
            page.fill(cfg.us, cfg.username)
            page.fill(cfg.ps, cfg.password)
            page.click(cfg.sb)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.goto(cfg.dashboard_url, timeout=20000)
            try:
                page.wait_for_selector(cfg.sels[-1], timeout=15000)
            except PWTimeout:
                pass
            time.sleep(5)
            data = {}
            el = page.query_selector(cfg.time_sel)
            data["page_time"] = el.inner_text().strip() if el else None
            for k, sel in zip(["sell", "buy", "cons", "self", "gen"], cfg.sels):
                el = page.query_selector(sel)
                data[k] = el.inner_text().strip() if el else None
        finally:
            context.close()
            browser.close()

    scrape = dt.datetime.now(tz=JST).replace(second=0, microsecond=0)
    page_t = parse_time(data.get("page_time") or "") or scrape
    row = {
        "page_time_jst": page_t.isoformat(timespec="minutes"),
        "scrape_time_jst": scrape.isoformat(timespec="minutes"),
        "sell_kwh": to_f(data.get("sell")),
        "buy_kwh": to_f(data.get("buy")),
        "cons_kwh": to_f(data.get("cons")),
        "self_kwh": to_f(data.get("self")),
        "gen_kwh": to_f(data.get("gen")),
    }
    if cfg.data_csv.exists():
        df = pd.read_csv(cfg.data_csv)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(cfg.data_csv, index=False)
    print("OK:", row)

if __name__ == "__main__":
    run_once()
