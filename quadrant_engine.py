"""Quadrant classification.

Every asset is placed on a 3x3 grid (Technical status x Fundamental
status), so nothing falls through into an undefined middle zone. A
valuation halt or euphoria flag still excludes a name from Q1/Q1A/Q1B
even if Health looks strong - fundamentals veto technicals, not the
other way around.

Technical status:   Green (Health >= 60), Neutral (40-60), Red (< 40)
Fundamental status:  Green (Conviction >= 65), Neutral (50-65), Red (< 50)
"""

import pandas as pd

from scoring_engine import is_valuation_halt

QUADRANT_ORDER = [
    "Q1A: Institutional Sweet Spot",
    "Q1: Macro Anchor",
    "Q1B: Momentum Building",
    "Q1C: Building Conviction",
    "Q2: Tripwire Watchlist",
    "Q3: Rented Momentum",
    "Watch: Neutral Zone",
    "Q4B: Fundamentals Fading",
    "Q4C: Technical Breakdown",
    "Q4: Broken",
    "Unclassified (missing data)",
]

QUADRANT_COLORS = {
    "Q1A: Institutional Sweet Spot": "#0b6e2f",
    "Q1: Macro Anchor": "#2ca02c",
    "Q1B: Momentum Building": "#66c2a5",
    "Q1C: Building Conviction": "#1f78b4",
    "Q2: Tripwire Watchlist": "#ff7f0e",
    "Q3: Rented Momentum": "#d62728",
    "Watch: Neutral Zone": "#bdbdbd",
    "Q4B: Fundamentals Fading": "#e0a458",
    "Q4C: Technical Breakdown": "#c98bb9",
    "Q4: Broken": "#7f7f7f",
    "Unclassified (missing data)": "#e5e5e5",
}

# How much of the raw position-sizing formula each quadrant is allowed to
# keep, for NEW deployment. The formula (capital x structural weight x
# conviction x technical multiplier) already zeroes out Q2/Q4C/Q4 via the
# technical multiplier (Health < 40 -> multiplier 0), but it does NOT
# discount Q3 (Health is green there) or the Neutral-status quadrants -
# so without this gate, "Watch: Neutral Zone" and "Q4B: Fundamentals
# Fading" names were receiving full-size dollar allocations despite
# having no confirmed edge. This gate applies on top of the euphoria/
# liquidity-trap veto, which still forces $0 regardless of quadrant.
QUADRANT_SIZING_GATE = {
    "Q1A: Institutional Sweet Spot": 1.00,
    "Q1: Macro Anchor": 1.00,
    "Q1B: Momentum Building": 1.00,
    "Q1C: Building Conviction": 1.00,
    "Q2: Tripwire Watchlist": 0.35,
    "Q3: Rented Momentum": 0.35,
    "Watch: Neutral Zone": 0.00,
    "Q4B: Fundamentals Fading": 0.00,
    "Q4C: Technical Breakdown": 0.00,
    "Q4: Broken": 0.00,
    "Unclassified (missing data)": 0.00,
}


def _tech_status(health) -> str:
    if pd.isna(health):
        return None
    if health >= 60:
        return "Green"
    if health >= 40:
        return "Neutral"
    return "Red"


def _fund_status(conviction) -> str:
    if pd.isna(conviction):
        return None
    if conviction >= 65:
        return "Green"
    if conviction >= 50:
        return "Neutral"
    return "Red"


def classify_quadrant(row) -> str:
    health = row.get("Health Score")
    conviction = row.get("Conviction Score")
    t = _tech_status(health)
    f = _fund_status(conviction)
    if t is None or f is None:
        return "Unclassified (missing data)"

    halt = is_valuation_halt(row.get("Valuation Status"))
    euphoria = bool(row.get("Euphoria Veto", False))
    burden = row.get("Expectations Burden")
    confirmed = not halt and not euphoria  # fundamentals didn't veto the technical strength

    if t == "Green" and f == "Green":
        if not confirmed:
            return "Q3: Rented Momentum"
        return "Q1A: Institutional Sweet Spot" if (pd.isna(burden) or burden < 15) else "Q1: Macro Anchor"

    if t == "Green" and f == "Neutral":
        return "Q1B: Momentum Building" if confirmed else "Q3: Rented Momentum"

    if t == "Green" and f == "Red":
        return "Q3: Rented Momentum"

    if t == "Neutral" and f == "Green":
        return "Q1C: Building Conviction"

    if t == "Red" and f == "Green":
        return "Q2: Tripwire Watchlist"

    if t == "Neutral" and f == "Neutral":
        return "Watch: Neutral Zone"

    if t == "Neutral" and f == "Red":
        return "Q4B: Fundamentals Fading"

    if t == "Red" and f == "Neutral":
        return "Q4C: Technical Breakdown"

    return "Q4: Broken"  # Red / Red
