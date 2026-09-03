"""Sub-score computation, penalty-adjusted Simon Score, and veto rules."""

import numpy as np
import pandas as pd


def normalize_0_100(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(50.0, index=series.index)
    return (series - lo) / (hi - lo) * 100.0


def is_valuation_halt(status) -> bool:
    return isinstance(status, str) and "Halt" in status


# Ordered so more specific / worse phrases aren't shadowed by substrings of better ones.
_VALUATION_STATUS_SCORE = [
    ("Tactical Valuation Halt", 10),
    ("Tactical Premium Zone", 45),
    ("Core Premium Accumulation", 50),
    ("Core Scarcity Premium", 65),
    ("Normal Range", 80),
    ("Value Zone", 100),
]


def valuation_status_base(status) -> float:
    if not isinstance(status, str):
        return 50.0
    for phrase, value in _VALUATION_STATUS_SCORE:
        if phrase in status:
            return float(value)
    return 50.0


def euphoria_veto(row) -> bool:
    """Health looks strong but valuation is halted or expectations are overextended."""
    burden = row.get("Expectations Burden")
    burden_flag = pd.notna(burden) and burden > 15
    return bool(
        row.get("Health Score", 0) > 70
        and (is_valuation_halt(row.get("Valuation Status")) or burden_flag)
    )


def liquidity_trap_veto(row) -> bool:
    """Fundamentals are excellent but price action hasn't confirmed - capital sits idle."""
    good_fundamentals = (
        pd.notna(row.get("Conviction Score"))
        and row.get("Conviction Score", 0) > 70
        and pd.notna(row.get("Quality Score"))
        and row.get("Quality Score", 0) > 80
    )
    poor_technical = pd.notna(row.get("Health Score")) and row.get("Health Score", 100) < 40
    return bool(good_fundamentals and poor_technical)


def technical_multiplier(health) -> float:
    if pd.isna(health):
        return 0.0
    if health > 70:
        return 1.2
    if health >= 50:
        return 1.0
    if health >= 40:
        return 0.7
    return 0.0


def compute_sub_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Momentum / Quality / Valuation / Crisis Resilience, each 0-100."""
    df = df.copy()

    mom_parts = {}
    if "Health Score" in df:
        mom_parts["health"] = df["Health Score"]
    if "LT Score" in df:
        mom_parts["lt"] = df["LT Score"]
    if "63D Alpha vs BM" in df:
        mom_parts["alpha63"] = normalize_0_100(df["63D Alpha vs BM"])
    if "12-1 Rel Mom" in df:
        mom_parts["relmom"] = normalize_0_100(df["12-1 Rel Mom"])
    df["Momentum Score"] = pd.DataFrame(mom_parts).mean(axis=1, skipna=True).round(1)

    qual_cols = [c for c in ["Quality Score", "Conviction Score"] if c in df]
    df["Quality Composite"] = df[qual_cols].mean(axis=1, skipna=True).round(1)

    base = df["Valuation Status"].apply(valuation_status_base)
    burden_penalty = df.get("Expectations Burden", pd.Series(0, index=df.index)).fillna(0).clip(upper=30)
    df["Valuation Score"] = (base - burden_penalty).clip(lower=0, upper=100).round(1)

    crisis_parts = {}
    if "Crisis Alpha" in df:
        crisis_parts["ca"] = normalize_0_100(df["Crisis Alpha"])
    if "Crisis Alpha (LT)" in df:
        crisis_parts["ca_lt"] = normalize_0_100(df["Crisis Alpha (LT)"])
    if "Drawdown Efficiency" in df:
        crisis_parts["dd"] = normalize_0_100(df["Drawdown Efficiency"])
    df["Crisis Resilience Score"] = pd.DataFrame(crisis_parts).mean(axis=1, skipna=True).round(1)

    return df


def compute_composite_score(df: pd.DataFrame, weights: dict) -> pd.Series:
    return (
        df["Momentum Score"].fillna(50) * weights["momentum"]
        + df["Quality Composite"].fillna(50) * weights["quality"]
        + df["Valuation Score"].fillna(50) * weights["valuation"]
        + df["Crisis Resilience Score"].fillna(50) * weights["crisis"]
    )


def apply_veto_penalties(score: pd.Series, euphoria: pd.Series, trap: pd.Series) -> pd.Series:
    """Euphoria and liquidity-trap flags directly discount the score instead of
    being cosmetic labels next to an unchanged number."""
    s = score.astype(float).copy()
    s = s.where(~euphoria, s * 0.60)
    s = s.where(~trap, s * 0.70)
    return s.round(1)
