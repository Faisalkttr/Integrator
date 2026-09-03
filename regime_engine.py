"""Macro regime overlay.

This is a rules-based overlay, not a live macro data feed. It tags each
asset's sector/layer into a broad category (crisis hedge, high-beta growth,
hard assets, etc.) using the Section/Layer text already in your Fundamental
CSV, then nudges the composite score up or down depending on which regime
you select. If you want this driven by actual Treasury/gold/BTC/DXY/PMI
data instead of a manual dropdown, that requires wiring in a live data feed
- flag it and it can be added as a v3 module.
"""

import pandas as pd

REGIME_OPTIONS = [
    "Neutral (no adjustment)",
    "Crisis",
    "Expansion",
    "Inflation",
    "Deflation",
    "Stagflation",
]

# tag -> keywords matched against "<Layer> <Section>" text (case-sensitive, substring match)
_CATEGORY_RULES = [
    ("crisis_hedge", ["Monetary Royalties"]),
    ("hard_assets", [
        "Water & Environmental", "Hard Assets & Global Freight",
        "Industrial & Critical Materials",
    ]),
    ("high_beta_growth", [
        "Architecture, Robotics, Edge & Memory", "AI/SEMIS", "AI / SEMIS",
    ]),
    ("cyber_growth", ["Cyber, Networking & Tech-Adjacent"]),
    ("software", ["Vertical Software & Data Monopolies"]),
    ("growth_apps", ["Velocity Applications"]),
    ("foundry_materials", ["Physical Monopolies, Foundry & Materials"]),
    ("utilities_energy", ["Electrification, Grid & Utilities", "Baseload & Nuclear Energy"]),
]

_REGIME_ADJUSTMENTS = {
    "Crisis": {
        "crisis_hedge": 15, "hard_assets": 8,
        "high_beta_growth": -10, "cyber_growth": -8, "software": -5, "growth_apps": -8,
    },
    "Expansion": {
        "high_beta_growth": 10, "cyber_growth": 8, "software": 6, "foundry_materials": 6,
        "crisis_hedge": -5,
    },
    "Inflation": {
        "hard_assets": 10, "crisis_hedge": 8, "utilities_energy": 6, "high_beta_growth": -6,
    },
    "Deflation": {
        "software": 8, "cyber_growth": 5, "crisis_hedge": 5, "hard_assets": -5,
    },
    "Stagflation": {
        "crisis_hedge": 10, "hard_assets": 8, "high_beta_growth": -8, "software": -6,
    },
}


def tag_sector(layer, section) -> str:
    text = f"{layer or ''} {section or ''}"
    for tag, keywords in _CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return tag
    return "uncategorized"


def apply_regime_overlay(df: pd.DataFrame, regime: str, layer_col: str, section_col: str) -> pd.DataFrame:
    df = df.copy()
    df["Sector Tag"] = df.apply(
        lambda r: tag_sector(r.get(layer_col), r.get(section_col)), axis=1
    )
    adjustments = _REGIME_ADJUSTMENTS.get(regime, {})
    df["Regime Adjustment"] = df["Sector Tag"].map(adjustments).fillna(0.0)
    return df
