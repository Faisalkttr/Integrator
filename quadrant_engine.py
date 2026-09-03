"""Quadrant classification. A valuation halt or euphoria flag now excludes a
name from Q1/Q1A even if Health looks strong - fundamentals veto technicals,
not the other way around."""

import pandas as pd

from scoring_engine import is_valuation_halt

QUADRANT_ORDER = [
    "Q1A: Institutional Sweet Spot",
    "Q1: Macro Anchor",
    "Q2: Tripwire Watchlist",
    "Q3: Rented Momentum",
    "Q4: Broken",
    "Unclassified",
]

QUADRANT_COLORS = {
    "Q1A: Institutional Sweet Spot": "#0b6e2f",
    "Q1: Macro Anchor": "#2ca02c",
    "Q2: Tripwire Watchlist": "#ff7f0e",
    "Q3: Rented Momentum": "#d62728",
    "Q4: Broken": "#7f7f7f",
    "Unclassified": "#c7c7c7",
}


def classify_quadrant(row) -> str:
    health = row.get("Health Score")
    conviction = row.get("Conviction Score")
    if pd.isna(health) or pd.isna(conviction):
        return "Unclassified"

    halt = is_valuation_halt(row.get("Valuation Status"))
    euphoria = bool(row.get("Euphoria Veto", False))
    burden = row.get("Expectations Burden")

    if conviction > 65 and health > 60 and not halt and not euphoria:
        if pd.isna(burden) or burden < 15:
            return "Q1A: Institutional Sweet Spot"
        return "Q1: Macro Anchor"

    if conviction > 70 and health < 40:
        return "Q2: Tripwire Watchlist"

    if health > 60 and (halt or euphoria):
        return "Q3: Rented Momentum"

    if health < 30 and conviction < 55:
        return "Q4: Broken"

    return "Unclassified"
