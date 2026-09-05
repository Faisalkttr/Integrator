"""
Dual Engine Portfolio Synchronizer (v2)
-----------------------------------------
Merges a monthly TECHNICAL export CSV and a monthly FUNDAMENTAL export CSV,
computes four sub-scores (Momentum / Quality / Valuation / Crisis Resilience),
blends them into a penalty-adjusted Simon Score, classifies every asset into
a quadrant (including Q1A Institutional Sweet Spot), applies a manual macro
regime overlay, detects confirmed month-over-month tripwires, sizes
positions, compares against your current holdings for rebalancing, and
renders an investment-committee dashboard + PDF report.

Run locally:
    streamlit run app.py

Deploy: push this repo to GitHub and connect it at share.streamlit.io
"""

import io
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import scoring_engine as se
import quadrant_engine as qe
import regime_engine as re_
import tripwire_engine as tw
import rebalance_engine as rb
from reports import build_pdf_report

# --------------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Dual Engine Portfolio Synchronizer",
    page_icon="\U0001F4CA",
    layout="wide",
)

# --------------------------------------------------------------------------
# Column contracts (must match your exporter tools exactly)
# --------------------------------------------------------------------------
FUND_KEY = "Ticker"
TECH_KEY = "Asset"

FUND_REQUIRED = [
    "Ticker", "Section", "Layer", "Structural Weight", "Core",
    "Valuation Status", "Expectations Status", "Quality Status",
    "Valuation Multiplier", "Expectations Burden", "Quality Score",
    "Conviction Score", "Suggested $ Deployment", "Notes",
]

TECH_REQUIRED = [
    "Section", "Layer", "Asset", "Benchmark", "Status", "Health Score",
    "LT Score", "LT Score Basis", "Regime", "Sector Rank", "Sector Percentile",
    "1M Return", "3M Return", "63D Alpha vs BM", "Vol-Adjusted RS",
    "Trend R\u00b2", "RS Acceleration", "200D Trend Slope", "252D Slope",
    "12-1 Rel Mom", "Drawdown Efficiency", "Max Drawdown", "Up Capture",
    "Down Capture", "Up Capture (LT)", "Down Capture (LT)", "Crisis Alpha",
    "Crisis Alpha (LT)", "Real Days", "Data Fill %", "FX Mismatch",
]

_BLANK_TOKENS = {"nan", "", "-", "--", "n/a", "na", "none", "null"}


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------
def parse_percent(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace("%", "", regex=False).str.strip()
    cleaned = cleaned.where(~cleaned.str.lower().isin(_BLANK_TOKENS), np.nan)
    return pd.to_numeric(cleaned, errors="coerce")


def parse_money(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
    )
    cleaned = cleaned.where(~cleaned.str.lower().isin(_BLANK_TOKENS), np.nan)
    return pd.to_numeric(cleaned, errors="coerce")


def _warn_and_drop_duplicates(df: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
    dupes = df[df.duplicated(subset=[key], keep=False)][key].unique().tolist()
    if dupes:
        st.warning(
            f"\u26a0\ufe0f {label} CSV has duplicate {key} value(s): {dupes}. "
            "Keeping the first occurrence of each and dropping the rest so "
            "downstream numbers aren't double-counted \u2014 check your exporter "
            "for why the same ticker appears more than once."
        )
        df = df.drop_duplicates(subset=[key], keep="first")
    return df


def load_fundamental(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in FUND_REQUIRED if c not in df.columns]
    if missing:
        st.warning(f"Fundamental CSV is missing expected columns: {missing}")
    df["Structural Weight (%)"] = parse_percent(df["Structural Weight"])
    df["Suggested $ Deployment"] = parse_money(df["Suggested $ Deployment"])
    for col in ["Valuation Multiplier", "Expectations Burden", "Quality Score", "Conviction Score"]:
        if col in df.columns:
            df[col] = parse_money(df[col].astype(str).str.replace("x", "", regex=False))
    df["Ticker"] = df["Ticker"].astype(str).str.strip()
    df = _warn_and_drop_duplicates(df, "Ticker", "Fundamental")
    return df


def load_technical(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in TECH_REQUIRED if c not in df.columns]
    if missing:
        st.warning(f"Technical CSV is missing expected columns: {missing}")
    numeric_candidates = [
        "Health Score", "LT Score", "Sector Percentile", "1M Return", "3M Return",
        "63D Alpha vs BM", "Vol-Adjusted RS", "Trend R\u00b2", "RS Acceleration",
        "200D Trend Slope", "252D Slope", "12-1 Rel Mom", "Drawdown Efficiency",
        "Max Drawdown", "Up Capture", "Down Capture", "Up Capture (LT)",
        "Down Capture (LT)", "Crisis Alpha", "Crisis Alpha (LT)", "Real Days",
        "Data Fill %",
    ]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = parse_money(df[col])
    df["Asset"] = df["Asset"].astype(str).str.strip()
    df = _warn_and_drop_duplicates(df, "Asset", "Technical")
    return df


# --------------------------------------------------------------------------
# Full scoring pipeline
# --------------------------------------------------------------------------
def score_merged(
    merged: pd.DataFrame, weights: dict, total_capital: float, regime: str, apply_sizing_gate: bool
) -> pd.DataFrame:
    df = merged.copy()

    df = se.compute_sub_scores(df)
    df["Euphoria Veto"] = df.apply(se.euphoria_veto, axis=1)
    df["Liquidity Trap"] = df.apply(se.liquidity_trap_veto, axis=1)

    composite = se.compute_composite_score(df, weights)
    df["Simon Score (Pre-Penalty)"] = composite.round(1)
    df["Simon Score"] = se.apply_veto_penalties(composite, df["Euphoria Veto"], df["Liquidity Trap"])

    df["Quadrant"] = df.apply(qe.classify_quadrant, axis=1)

    layer_col = "Layer_fund" if "Layer_fund" in df.columns else "Layer"
    section_col = "Section_fund" if "Section_fund" in df.columns else "Section"
    df = re_.apply_regime_overlay(df, regime, layer_col, section_col)
    df["Simon Score"] = (df["Simon Score"] + df["Regime Adjustment"]).clip(0, 100).round(1)

    df["Technical Multiplier"] = df["Health Score"].apply(se.technical_multiplier)
    df["Conviction Multiplier"] = (df["Conviction Score"].fillna(0) / 100.0).round(3)
    df["Computed Allocation (Pre-Quadrant-Gate) ($)"] = (
        total_capital
        * (df["Structural Weight (%)"].fillna(0) / 100.0)
        * df["Conviction Multiplier"]
        * df["Technical Multiplier"]
    ).round(0)

    if apply_sizing_gate:
        df["Quadrant Sizing Gate"] = df["Quadrant"].map(qe.QUADRANT_SIZING_GATE).fillna(0.0)
    else:
        df["Quadrant Sizing Gate"] = 1.0

    df["Computed Allocation ($)"] = (
        df["Computed Allocation (Pre-Quadrant-Gate) ($)"] * df["Quadrant Sizing Gate"]
    ).round(0)
    df.loc[df["Euphoria Veto"] | df["Liquidity Trap"], "Computed Allocation ($)"] = 0

    return df


# --------------------------------------------------------------------------
# UI - Sidebar
# --------------------------------------------------------------------------
st.sidebar.title("\U0001F4C1 Monthly Upload")
technical_file = st.sidebar.file_uploader("Technical Engine CSV", type=["csv"], key="tech")
fundamental_file = st.sidebar.file_uploader("Fundamental Engine CSV", type=["csv"], key="fund")

st.sidebar.markdown("---")
st.sidebar.subheader("\u23F1\ufe0f Tripwire comparison (optional)")
prev_scored_file = st.sidebar.file_uploader(
    "Previous month's SCORED export (downloaded from this app last time)",
    type=["csv"], key="prev",
)

st.sidebar.markdown("---")
st.sidebar.subheader("\U0001F4BC Current holdings (optional)")
portfolio_file = st.sidebar.file_uploader(
    "Current portfolio CSV (Ticker, Shares, Current Value)", type=["csv"], key="portfolio",
)

st.sidebar.markdown("---")
st.sidebar.subheader("\U0001F30D Macro regime overlay")
regime = st.sidebar.selectbox("Current regime", re_.REGIME_OPTIONS, index=0)
st.sidebar.caption(
    "Manual, rules-based overlay using your Section/Layer tags "
    "(e.g. royalties get boosted in Crisis mode). Not a live data feed."
)

st.sidebar.markdown("---")
st.sidebar.subheader("\u2696\ufe0f Simon Score weights")
w_mom = st.sidebar.slider("Momentum weight", 0.0, 1.0, 0.35, 0.05)
w_qual = st.sidebar.slider("Quality weight", 0.0, 1.0, 0.25, 0.05)
w_val = st.sidebar.slider("Valuation weight", 0.0, 1.0, 0.25, 0.05)
w_crisis = st.sidebar.slider("Crisis Resilience weight", 0.0, 1.0, 0.15, 0.05)
weight_sum = w_mom + w_qual + w_val + w_crisis
if abs(weight_sum - 1.0) > 0.001:
    st.sidebar.caption(f"\u26a0\ufe0f Weights sum to {weight_sum:.2f}, not 1.00 (score still computes).")
st.sidebar.caption(
    "Euphoria-veto names are scored \u00d70.60, liquidity-trap names \u00d70.70, "
    "on top of these weights."
)

st.sidebar.markdown("---")
total_capital = st.sidebar.number_input(
    "Total portfolio capital ($)", min_value=0, value=250_000, step=5_000
)

st.sidebar.markdown("---")
st.sidebar.subheader("\U0001F6AA Quadrant-gated sizing")
apply_sizing_gate = st.sidebar.checkbox(
    "Discount new deployment by quadrant quality", value=True,
)
with st.sidebar.expander("What this does"):
    st.write(
        "The raw formula (capital \u00d7 structural weight \u00d7 conviction \u00d7 "
        "technical multiplier) already zeroes out Health < 40 names, but it doesn't "
        "discount **Q3: Rented Momentum** (Health is green there) or the Neutral-status "
        "quadrants \u2014 so without this gate, Watch/Q4B names can still receive "
        "full-size dollar allocations despite having no confirmed edge. This gate "
        "gives Q1A/Q1/Q1B/Q1C 100%, Q2/Q3 35%, and everything else (Watch, Q4B, Q4C, "
        "Q4) 0% of the raw formula, for NEW money only. Euphoria/liquidity-trap vetoes "
        "still force $0 regardless of this setting."
    )

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
st.title("\U0001F4CA Dual Engine Portfolio Synchronizer")
st.caption(
    "Monthly Conviction Allocation Machine \u2014 upload both engines to generate "
    "penalty-adjusted scores, quadrants, vetoes, confirmed tripwires, sizing, and rebalancing."
)

if not technical_file or not fundamental_file:
    st.info("Upload both the **Technical** and **Fundamental** CSVs in the sidebar to run the engine.")
    st.stop()

technical_df = load_technical(technical_file)
fundamental_df = load_fundamental(fundamental_file)

merged = pd.merge(
    technical_df, fundamental_df,
    left_on=TECH_KEY, right_on=FUND_KEY,
    how="inner", suffixes=("_tech", "_fund"),
)

fund_only = fundamental_df[~fundamental_df[FUND_KEY].isin(technical_df[TECH_KEY])]
tech_only = technical_df[~technical_df[TECH_KEY].isin(fundamental_df[FUND_KEY])]

weights = {"momentum": w_mom, "quality": w_qual, "valuation": w_val, "crisis": w_crisis}
scored = score_merged(merged, weights, total_capital, regime, apply_sizing_gate)

# ---- Top metrics ----------------------------------------------------------
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Dual-Engine Assets", len(scored))
c2.metric("Q1A Sweet Spot", int((scored["Quadrant"] == "Q1A: Institutional Sweet Spot").sum()))
c3.metric("Euphoria Alerts", int(scored["Euphoria Veto"].sum()))
c4.metric("Liquidity Traps", int(scored["Liquidity Trap"].sum()))
c5.metric("Fundamental-only", len(fund_only))
c6.metric("Technical-only", len(tech_only))

if regime != "Neutral (no adjustment)":
    st.caption(f"\U0001F30D Regime overlay active: **{regime}** \u2014 scores above already include the adjustment.")

total_suggested = scored["Computed Allocation ($)"].sum()
utilization = (total_suggested / total_capital * 100) if total_capital else 0
u1, u2 = st.columns(2)
u1.metric("Total Suggested New Deployment", f"${total_suggested:,.0f}")
u2.metric("Capital Utilization", f"{utilization:.0f}%", help="Suggested deployment as a % of total portfolio capital.")
if utilization > 100:
    st.warning(
        f"\u26a0\ufe0f Suggested new deployment (${total_suggested:,.0f}) exceeds your stated "
        f"capital (${total_capital:,.0f}). Each name is sized independently from your "
        "structural weight, so the book can still add up to more than 100% even with "
        "quadrant gating on \u2014 treat the ranking as a priority order for a limited "
        "monthly contribution, not a set of amounts to deploy all at once."
    )

st.markdown("---")

# ---- Tripwires --------------------------------------------------------
if prev_scored_file is not None:
    try:
        prev_scored = pd.read_csv(prev_scored_file)
        tripwires = tw.detect_tripwires(scored, prev_scored)
        st.subheader("\U0001F6A8 Tripwires this month")
        if tripwires.empty:
            st.write("No threshold crossings detected vs. previous upload.")
        else:
            st.dataframe(tripwires, width="stretch", hide_index=True)
            st.caption(
                "Upward Health crossings are marked Confirmed only when 63D Alpha vs "
                "Benchmark is positive and the current Regime isn't Bear."
            )
    except Exception as e:
        st.warning(f"Could not compare to previous export: {e}")
else:
    tripwires = pd.DataFrame()
    st.caption("Upload last month's scored export in the sidebar to enable tripwire detection.")

st.markdown("---")

# ---- Heatmap ----------------------------------------------------------
st.subheader("\U0001F5FA\ufe0f Health vs. Conviction Heat Map")
plot_df = scored.copy()
plot_df["Deployment Size"] = plot_df["Computed Allocation ($)"].clip(lower=100)
fig = px.scatter(
    plot_df,
    x="Health Score", y="Conviction Score",
    color="Quadrant", size="Deployment Size",
    hover_name=TECH_KEY,
    hover_data=["Simon Score", "Computed Allocation ($)", "Valuation Status"],
    color_discrete_map=qe.QUADRANT_COLORS,
    height=550,
)
fig.add_vline(x=60, line_dash="dot", line_color="gray")
fig.add_hline(y=65, line_dash="dot", line_color="gray")
st.plotly_chart(fig, width="stretch")

st.markdown("---")

# ---- Quadrant tabs ------------------------------------------------------
st.subheader("\U0001F4CB Quadrant breakdown")
display_cols = [
    TECH_KEY, "Section_tech", "Simon Score", "Momentum Score", "Quality Composite",
    "Valuation Score", "Crisis Resilience Score", "Health Score", "Conviction Score",
    "Valuation Status", "Expectations Burden", "Euphoria Veto", "Liquidity Trap",
    "Regime Adjustment", "Technical Multiplier", "Quadrant Sizing Gate",
    "Computed Allocation (Pre-Quadrant-Gate) ($)", "Computed Allocation ($)",
]
display_cols = [c for c in display_cols if c in scored.columns]

tabs = st.tabs([q for q in qe.QUADRANT_ORDER] + ["All assets"])
for tab, name in zip(tabs[:-1], qe.QUADRANT_ORDER):
    with tab:
        sub = scored[scored["Quadrant"] == name][display_cols].sort_values(
            "Simon Score", ascending=False
        )
        st.dataframe(sub, width="stretch", hide_index=True)

with tabs[-1]:
    st.dataframe(
        scored[display_cols].sort_values("Simon Score", ascending=False),
        width="stretch", hide_index=True,
    )

st.markdown("---")

# ---- Portfolio rebalancing ------------------------------------------------
st.subheader("\U0001F504 Portfolio Rebalancing")
if portfolio_file is not None:
    try:
        portfolio_df = rb.load_portfolio(portfolio_file)
        rebalance_df, unmatched_holdings = rb.compute_rebalance(scored, portfolio_df, total_capital)
        rebal_cols = [
            TECH_KEY, "Held", "Current Value", "Current Weight (%)", "Target Weight (%)",
            "Quadrant", "Euphoria Veto", "Liquidity Trap", "Recommendation",
        ]
        rebal_cols = [c for c in rebal_cols if c in rebalance_df.columns]
        st.dataframe(
            rebalance_df[rebal_cols].sort_values("Held", ascending=False),
            width="stretch", hide_index=True,
        )
        if not unmatched_holdings.empty:
            st.caption(
                f"\u26a0\ufe0f {len(unmatched_holdings)} held ticker(s) not found in this month's "
                "dual-engine universe (no technical and/or fundamental match): "
                + ", ".join(unmatched_holdings['Ticker'].tolist())
            )
    except Exception as e:
        st.warning(f"Could not process portfolio file: {e}")
        rebalance_df = pd.DataFrame()
else:
    rebalance_df = pd.DataFrame()
    st.caption(
        "Upload your current holdings CSV (columns: Ticker, Shares, Current Value) "
        "in the sidebar to get Buy More / Hold / Trim / Exit recommendations."
    )

st.markdown("---")

# ---- Coverage gaps ------------------------------------------------------
with st.expander(f"\U0001F50D Fundamental-only tickers ({len(fund_only)}) \u2014 no technical match"):
    st.dataframe(fund_only, width="stretch", hide_index=True)
with st.expander(f"\U0001F50D Technical-only tickers ({len(tech_only)}) \u2014 no fundamental match"):
    st.dataframe(tech_only, width="stretch", hide_index=True)

st.markdown("---")

# ---- Exports ------------------------------------------------------------
st.subheader("\U0001F4E4 Exports")
col_a, col_b = st.columns(2)

csv_buffer = io.StringIO()
scored.to_csv(csv_buffer, index=False)
today = datetime.now().strftime("%Y-%m-%d")

with col_a:
    st.download_button(
        "\u2b07\ufe0f Download scored CSV (use as next month's tripwire baseline)",
        data=csv_buffer.getvalue(),
        file_name=f"scored_export_{today}.csv",
        mime="text/csv",
    )

with col_b:
    pdf_bytes = build_pdf_report(scored, tripwires, rebalance_df, total_capital, today, regime)
    st.download_button(
        "\u2b07\ufe0f Download Investment Committee PDF",
        data=pdf_bytes,
        file_name=f"committee_report_{today}.pdf",
        mime="application/pdf",
    )
