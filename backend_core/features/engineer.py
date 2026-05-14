"""
features/engineer.py — Compute 20+ financial health indicators from raw data
Compatible with both yfinance AND SEC EDGAR fetched data.

Run: .venv\Scripts\python.exe src/features/engineer.py --test
     .venv\Scripts\python.exe src/features/engineer.py
"""

import os
import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

# Path fix for root imports
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

warnings.filterwarnings("ignore")

from backend_core.config import (ALL_TICKERS, COMPANY_UNIVERSE, DISTRESS_EVENTS,
                    RAW_DIR, FEATURE_MATRIX_PATH, LOGS_DIR)
from backend_core.utils.logger import get_logger

logger = get_logger("engineer", LOGS_DIR / "engineer.log")


def safe_div(a, b):
    try:
        if b == 0 or pd.isna(b) or pd.isna(a):
            return np.nan
        return float(a) / float(b)
    except:
        return np.nan


def load_statements(ticker):
    statements = {}
    for name in ["income", "balance", "cashflow"]:
        path = os.path.join(RAW_DIR, f"{ticker}_{name}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path, index_col=0)
            try:
                idx = pd.to_numeric(df.index, errors="coerce")
                if idx.notna().all() and (idx >= 1990).all() and (idx <= 2030).all():
                    df.index = idx.astype(int)
                else:
                    df.index = pd.to_datetime(df.index, errors="coerce").year
                    df.index = pd.to_numeric(df.index, errors="coerce")
            except:
                pass
            df = df[df.index.notna()].sort_index(ascending=False)   
            df = df.drop(columns=["ticker"], errors="ignore")
            df = df.apply(pd.to_numeric, errors="coerce")
            statements[name] = df
        else:
            statements[name] = pd.DataFrame()
    return statements


def get_val(df, candidates, year_idx=0):
    if df is None or df.empty:
        return np.nan
    for col in candidates:
        for c in df.columns:
            if col.lower().replace(" ", "") in c.lower().replace(" ", ""):
                try:
                    vals = pd.to_numeric(df[c], errors="coerce").dropna()
                    if len(vals) > year_idx:
                        return float(vals.iloc[year_idx])
                except:
                    continue
    return np.nan


def get_series(df, candidates):
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for col in candidates:
        for c in df.columns:
            if col.lower().replace(" ", "") in c.lower().replace(" ", ""):
                s = pd.to_numeric(df[c], errors="coerce").dropna()
                if not s.empty:
                    return s
    return pd.Series(dtype=float)


COLS = {
    "revenue":     ["Revenue", "Total Revenue", "Revenues", "SalesRevenueNet"],
    "cogs":        ["CostOfRevenue", "Cost Of Revenue", "Cost Of Goods Sold"],
    "gross_profit":["GrossProfit", "Gross Profit"],
    "op_income":   ["OperatingIncome", "EBIT", "Operating Income", "Operating Profit"],
    "ebitda":      ["EBITDA", "Normalized EBITDA"],
    "interest_exp":["InterestExpense", "Interest Expense", "Interest And Debt Expense"],
    "net_income":  ["NetIncome", "Net Income", "Net Income Common Stockholders"],
    "da":          ["DepreciationAmortization", "Depreciation And Amortization",
                    "Reconciled Depreciation"],
    "total_assets":["TotalAssets", "Total Assets", "Assets"],
    "total_liab":  ["TotalLiabilities", "Total Liabilities",
                    "Total Liabilities Net Minority Interest"],
    "curr_assets": ["CurrentAssets", "Current Assets", "Total Current Assets"],
    "curr_liab":   ["CurrentLiabilities", "Current Liabilities",
                    "Total Current Liabilities",
                    "Current Liabilities Net Minority Interest"],
    "cash":        ["Cash", "Cash And Cash Equivalents",
                    "Cash Cash Equivalents And Short Term Investments"],
    "inventory":   ["Inventory", "Inventories", "InventoryNet"],
    "total_debt":  ["TotalDebt", "Total Debt",
                    "Long Term Debt And Capital Lease Obligation"],
    "ltd":         ["LongTermDebt", "Long Term Debt"],
    "equity":      ["StockholdersEquity", "Stockholders Equity",
                    "Total Equity", "Common Stock Equity"],
    "retained":    ["RetainedEarnings", "Retained Earnings",
                    "Retained Earnings Accumulated Deficit"],
    "shares":      ["SharesOutstanding", "Common Stock", "Share Issued",
                    "Common Stock Shares Outstanding"],
    "ocf":         ["OperatingCashFlow", "Operating Cash Flow",
                    "Net Cash Provided By Used In Operating Activities",
                    "Cash Flow From Continuing Operating Activities"],
}


def debt_to_equity(balance, i=0):
    return safe_div(get_val(balance, COLS["total_debt"], i),
                    get_val(balance, COLS["equity"], i))

def interest_coverage(income, i=0):
    ebit = get_val(income, COLS["op_income"], i)
    interest = get_val(income, COLS["interest_exp"], i)
    if interest and interest < 0:
        interest = abs(interest)
    return safe_div(ebit, interest)

def debt_to_ebitda(income, balance, i=0):
    debt = get_val(balance, COLS["total_debt"], i)
    ebitda = get_val(income, COLS["ebitda"], i)
    if not ebitda or ebitda <= 0:
        op = get_val(income, COLS["op_income"], i)
        da = get_val(income, COLS["da"], i)
        if op and da:
            ebitda = op + abs(da)
    return safe_div(debt, ebitda)

def ltd_slope(balance):
    s = get_series(balance, COLS["ltd"])
    if len(s) < 2:
        return np.nan
    s = s.sort_index().tail(3)
    return float(np.polyfit(np.arange(len(s)), s.values, 1)[0])

def current_ratio(balance, i=0):
    return safe_div(get_val(balance, COLS["curr_assets"], i),
                    get_val(balance, COLS["curr_liab"], i))

def quick_ratio(balance, i=0):
    ca  = get_val(balance, COLS["curr_assets"], i) or 0
    inv = get_val(balance, COLS["inventory"], i)   or 0
    cl  = get_val(balance, COLS["curr_liab"], i)
    return safe_div(ca - inv, cl)

def cash_ratio(balance, i=0):
    return safe_div(get_val(balance, COLS["cash"], i),
                    get_val(balance, COLS["curr_liab"], i))

def days_cash_on_hand(balance, income, i=0):
    cash = get_val(balance, COLS["cash"], i)
    rev  = get_val(income,  COLS["revenue"], i)
    cogs = get_val(income,  COLS["cogs"], i) or 0
    sga  = get_val(income,  ["SellingGeneralAdmin", "Selling General And Administration",
                              "Operating Expense"], i) or 0
    opex = cogs + sga
    if opex <= 0 and rev:
        opex = rev * 0.8
    return safe_div(cash, safe_div(opex, 365))

def cash_burn(cashflow, i=0):
    return get_val(cashflow, COLS["ocf"], i)

def gross_margin(income, i=0):
    rev  = get_val(income, COLS["revenue"], i)
    cogs = get_val(income, COLS["cogs"], i)
    if rev and cogs:
        return safe_div(rev - cogs, rev)
    return safe_div(get_val(income, COLS["gross_profit"], i), rev)

def net_margin(income, i=0):
    return safe_div(get_val(income, COLS["net_income"], i),
                    get_val(income, COLS["revenue"], i))

def ebitda_margin(income, i=0):
    return safe_div(get_val(income, COLS["ebitda"], i),
                    get_val(income, COLS["revenue"], i))

def roe(income, balance, i=0):
    return safe_div(get_val(income,  COLS["net_income"], i),
                    get_val(balance, COLS["equity"], i))

def roa(income, balance, i=0):
    return safe_div(get_val(income,  COLS["net_income"], i),
                    get_val(balance, COLS["total_assets"], i))

def margin_trend(income, fn, n=4):
    vals = []
    for i in range(min(n, len(income))):
        v = fn(income, i)
        if v is not None and not np.isnan(v):
            vals.append(v)
    if len(vals) < 2:
        return np.nan
    vals.reverse()
    return float(np.polyfit(np.arange(len(vals)), vals, 1)[0])

def altman_z(income, balance, cashflow, market_cap=None, i=0):
    assets = get_val(balance, COLS["total_assets"], i)
    if not assets or assets == 0:
        return np.nan
    ca   = get_val(balance, COLS["curr_assets"], i) or 0
    cl   = get_val(balance, COLS["curr_liab"], i)   or 0
    re   = get_val(balance, COLS["retained"], i)
    ebit = get_val(income,  COLS["op_income"], i)
    liab = get_val(balance, COLS["total_liab"], i)
    rev  = get_val(income,  COLS["revenue"], i)
    eq   = get_val(balance, COLS["equity"], i)
    x1 = safe_div(ca - cl, assets)
    x2 = safe_div(re,      assets)
    x3 = safe_div(ebit,    assets)
    x4 = safe_div(market_cap or eq, liab)
    x5 = safe_div(rev,     assets)
    valid = sum(1 for x in [x1,x2,x3,x4,x5]
                if x is not None and not np.isnan(x))
    if valid < 3:
        return np.nan
    def v(x): return x if (x is not None and not np.isnan(x)) else 0
    return float(1.2*v(x1) + 1.4*v(x2) + 3.3*v(x3) + 0.6*v(x4) + 1.0*v(x5))

def piotroski_f(income, balance, cashflow, i=0):
    score = 0
    roa_c = roa(income, balance, i)
    roa_p = roa(income, balance, i+1)
    ocf   = get_val(cashflow, COLS["ocf"], i)
    ni    = get_val(income,   COLS["net_income"], i)
    assets= get_val(balance,  COLS["total_assets"], i)
    if roa_c and not np.isnan(roa_c) and roa_c > 0:           score += 1
    if ocf and not np.isnan(ocf) and ocf > 0:                 score += 1
    if (roa_c and roa_p and not np.isnan(roa_c)
            and not np.isnan(roa_p) and roa_c > roa_p):       score += 1
    if ocf and ni and assets and assets != 0:
        if safe_div(ocf, assets) > safe_div(ni, assets):      score += 1
    ltd_c = get_val(balance, COLS["ltd"], i)
    ltd_p = get_val(balance, COLS["ltd"], i+1)
    ast_p = get_val(balance, COLS["total_assets"], i+1)
    cr_c  = current_ratio(balance, i)
    cr_p  = current_ratio(balance, i+1)
    sh_c  = get_val(balance, COLS["shares"], i)
    sh_p  = get_val(balance, COLS["shares"], i+1)
    ldr_c = safe_div(ltd_c, assets)
    ldr_p = safe_div(ltd_p, ast_p)
    if (ldr_c and ldr_p and not np.isnan(ldr_c)
            and not np.isnan(ldr_p) and ldr_c < ldr_p):       score += 1
    if (cr_c and cr_p and not np.isnan(cr_c)
            and not np.isnan(cr_p) and cr_c > cr_p):          score += 1
    if (sh_c and sh_p and not np.isnan(sh_c)
            and not np.isnan(sh_p) and sh_c <= sh_p * 1.02):  score += 1
    gm_c  = gross_margin(income, i)
    gm_p  = gross_margin(income, i+1)
    rev_c = get_val(income, COLS["revenue"], i)
    rev_p = get_val(income, COLS["revenue"], i+1)
    at_c  = safe_div(rev_c, assets)
    at_p  = safe_div(rev_p, ast_p)
    if (gm_c and gm_p and not np.isnan(gm_c)
            and not np.isnan(gm_p) and gm_c > gm_p):          score += 1
    if (at_c and at_p and not np.isnan(at_c)
            and not np.isnan(at_p) and at_c > at_p):          score += 1
    return score

def cf_divergence(income, cashflow, i=0):
    ocf = get_val(cashflow, COLS["ocf"], i)
    ni  = get_val(income,   COLS["net_income"], i)
    rev = get_val(income,   COLS["revenue"], i)
    if not rev or rev == 0:
        return np.nan
    return safe_div((ocf or 0) - (ni or 0), abs(rev))

def rev_vs_debt_growth(income, balance, n=4):
    revs  = [get_val(income,  COLS["revenue"],    i) for i in range(n)]
    debts = [get_val(balance, COLS["total_debt"],  i) for i in range(n)]
    revs  = [r for r in revs  if r and not np.isnan(r)]
    debts = [d for d in debts if d and not np.isnan(d)]
    if len(revs) < 2 or len(debts) < 2:
        return np.nan
    revs.reverse(); debts.reverse()
    def cagr(v):
        if v[0] <= 0: return np.nan
        return (v[-1]/v[0]) ** (1/(len(v)-1)) - 1
    rc = cagr(revs); dc = cagr(debts)
    if np.isnan(rc) or np.isnan(dc): return np.nan
    return rc - dc


def compute_features(ticker):
    stmts    = load_statements(ticker)
    income   = stmts["income"]
    balance  = stmts["balance"]
    cashflow = stmts["cashflow"]
    if income.empty and balance.empty:
        logger.warning(f"{ticker}: no data")
        return pd.DataFrame()
    n = min(max(len(income), len(balance)), 12)
    rows = []
    for i in range(n):
        try:
            if not income.empty and i < len(income):
                yr = income.index[i]
                year = yr.year if hasattr(yr, 'year') else int(str(yr)[:4])
            elif not balance.empty and i < len(balance):
                yr = balance.index[i]
                year = yr.year if hasattr(yr, 'year') else int(str(yr)[:4])
            else:
                year = 2024 - i
        except:
            year = 2024 - i
        row = {
            "ticker": ticker, "year": year,
            "debt_to_equity":     debt_to_equity(balance, i),
            "interest_coverage":  interest_coverage(income, i),
            "debt_to_ebitda":     debt_to_ebitda(income, balance, i),
            "ltd_trend":          ltd_slope(balance) if i == 0 else np.nan,
            "current_ratio":      current_ratio(balance, i),
            "quick_ratio":        quick_ratio(balance, i),
            "cash_ratio":         cash_ratio(balance, i),
            "days_cash":          days_cash_on_hand(balance, income, i),
            "cash_burn":          cash_burn(cashflow, i),
            "gross_margin":       gross_margin(income, i),
            "net_margin":         net_margin(income, i),
            "ebitda_margin":      ebitda_margin(income, i),
            "roe":                roe(income, balance, i),
            "roa":                roa(income, balance, i),
            "gross_margin_trend": margin_trend(income, gross_margin) if i == 0 else np.nan,
            "net_margin_trend":   margin_trend(income, net_margin)   if i == 0 else np.nan,
            "altman_z":           altman_z(income, balance, cashflow, i=i),
            "piotroski_f":        piotroski_f(income, balance, cashflow, i),
            "cf_divergence":      cf_divergence(income, cashflow, i),
            "rev_vs_debt":        rev_vs_debt_growth(income, balance) if i == 0 else np.nan,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def attach_labels(df):
    df["distress_label"] = 0
    df["distress_event"] = ""
    for ticker, ev in DISTRESS_EVENTS.items():
        event_year = pd.to_datetime(ev["date"]).year
        mask = (
            (df["ticker"] == ticker) &
            (df["year"] >= event_year - 3) &
            (df["year"] <  event_year)
        )
        df.loc[mask, "distress_label"] = 1
        df.loc[mask, "distress_event"] = ev["event"]
    return df


def attach_sector(df):
    t2s = {t: s for s, ts in COMPANY_UNIVERSE.items() for t in ts}
    df["sector"] = df["ticker"].map(t2s).fillna("Unknown")
    return df


def run(tickers=None):
    tickers = tickers or ALL_TICKERS
    all_rows, failed = [], []
    logger.info(f"Engineering features for {len(tickers)} tickers...")
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{len(tickers)}] {ticker}")
        try:
            df = compute_features(ticker)
            if not df.empty:
                all_rows.append(df)
        except Exception as e:
            logger.warning(f"{ticker} failed: {e}")
            failed.append(ticker)
    if not all_rows:
        logger.error("No features computed. Run fetch_edgar.py first.")
        return
    master = pd.concat(all_rows, ignore_index=True)
    master = attach_labels(master)
    master = attach_sector(master)
    master = master.sort_values(["ticker", "year"], ascending=[True, False])
    master = master.drop_duplicates(subset=["ticker", "year"])
    out = FEATURE_MATRIX_PATH
    master.to_csv(out, index=False)
    logger.info(f"Saved: {out} | Shape: {master.shape}")
    logger.info(f"Tickers: {master['ticker'].nunique()} | Years: {master['year'].min()}-{master['year'].max()}")
    logger.info(f"Distressed rows: {master['distress_label'].sum()} ({master['distress_label'].mean()*100:.1f}%)")
    logger.info(f"Failed: {failed}")
    print("\n--- Feature Matrix Preview ---")
    cols = ["ticker","year","altman_z","piotroski_f","current_ratio","net_margin","distress_label","sector"]
    print(master[cols].head(20).to_string(index=False))
    return master


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        run(["AAPL", "MSFT", "BBBY", "SIVB", "CHESQ", "LEHMQ", "JCP", "WLL"])
    else:
        run(args.tickers)
