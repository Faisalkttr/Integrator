"""Compares current holdings (uploaded) against the model's target allocation
and issues Buy More / Hold / Trim / Exit / New Buy recommendations.

Expected current-portfolio CSV columns (case-insensitive match on Ticker):
    Ticker, Shares, Cost Basis (optional), Current Value (or Current Price + Shares)
"""

import numpy as np
import pandas as pd

SWEET_SPOT_QUADRANTS = {"Q1A: Institutional Sweet Spot", "Q1: Macro Anchor"}


def load_portfolio(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = [c.strip() for c in df.columns]
    ticker_col = next((c for c in df.columns if c.lower() == "ticker"), df.columns[0])
    df = df.rename(columns={ticker_col: "Ticker"})
    df["Ticker"] = df["Ticker"].astype(str).str.strip()
    if "Current Value" not in df.columns and {"Current Price", "Shares"}.issubset(df.columns):
        df["Current Value"] = pd.to_numeric(df["Current Price"], errors="coerce") * pd.to_numeric(
            df["Shares"], errors="coerce"
        )
    if "Current Value" in df.columns:
        df["Current Value"] = pd.to_numeric(df["Current Value"], errors="coerce")
    return df


def _recommend(row) -> str:
    held = bool(row.get("Held"))
    veto = bool(row.get("Euphoria Veto")) or bool(row.get("Liquidity Trap"))
    quadrant = row.get("Quadrant", "")
    cw, tw = row.get("Current Weight (%)"), row.get("Target Weight (%)")

    if held and (veto or quadrant == "Q4: Broken"):
        return "\U0001F534 Exit"
    if held and pd.notna(cw) and pd.notna(tw):
        if tw == 0 and cw > 0:
            return "\U0001F534 Exit"
        if cw > tw * 1.25:
            return "\U0001F7E1 Trim"
        if cw < tw * 0.75 and not veto:
            return "\U0001F7E2 Buy More"
        return "\u26aa Hold"
    if not held and not veto and quadrant in SWEET_SPOT_QUADRANTS and row.get("Computed Allocation ($)", 0) > 0:
        return "\U0001F195 New Buy"
    if held:
        return "\u26aa Hold"
    return "\u2014 No Action"


def compute_rebalance(scored: pd.DataFrame, portfolio_df: pd.DataFrame, total_capital: float) -> pd.DataFrame:
    total_current_value = portfolio_df["Current Value"].sum() if "Current Value" in portfolio_df else np.nan

    merged = scored.merge(
        portfolio_df, left_on="Asset", right_on="Ticker", how="left", suffixes=("", "_pos")
    )
    merged["Held"] = merged["Ticker_pos" if "Ticker_pos" in merged.columns else "Ticker"].notna()
    if "Current Value" not in merged.columns:
        merged["Current Value"] = np.nan

    if pd.notna(total_current_value) and total_current_value > 0:
        merged["Current Weight (%)"] = (merged["Current Value"] / total_current_value * 100).round(2)
    else:
        merged["Current Weight (%)"] = np.nan

    merged["Target Weight (%)"] = (
        merged["Computed Allocation ($)"] / total_capital * 100 if total_capital else np.nan
    ).round(2)

    merged["Recommendation"] = merged.apply(_recommend, axis=1)

    # Also surface holdings that don't appear in the scored dual-engine universe at all
    unmatched = portfolio_df[~portfolio_df["Ticker"].isin(scored["Asset"])]

    return merged, unmatched
