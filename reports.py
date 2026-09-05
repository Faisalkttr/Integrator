"""PDF investment-committee report builder."""

import io

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

TECH_KEY = "Asset"


def _table_from_df(df: pd.DataFrame, cols, col_widths=None):
    cols = [c for c in cols if c in df.columns]
    data = [cols] + df[cols].astype(str).values.tolist()
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def build_pdf_report(
    scored: pd.DataFrame,
    tripwires: pd.DataFrame,
    rebalance_df: pd.DataFrame,
    total_capital: float,
    date_str: str,
    regime: str = "Neutral (no adjustment)",
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6)
    body = styles["BodyText"]

    story = []
    story.append(Paragraph("Monthly Investment Committee Report", h1))
    story.append(Paragraph(
        f"Generated {date_str} \u00b7 Total portfolio capital: ${total_capital:,.0f} "
        f"\u00b7 Macro regime overlay: {regime}", body,
    ))
    story.append(Spacer(1, 10))

    # Executive summary
    n = len(scored)
    euphoria = int(scored["Euphoria Veto"].sum())
    traps = int(scored["Liquidity Trap"].sum())
    quadrant_counts = scored["Quadrant"].value_counts()
    total_alloc = scored["Computed Allocation ($)"].sum()

    quadrant_summary = ", ".join(
        f"{name}: {int(quadrant_counts.get(name, 0))}"
        for name in [
            "Q1A: Institutional Sweet Spot", "Q1: Macro Anchor", "Q1B: Momentum Building",
            "Q1C: Building Conviction", "Q2: Tripwire Watchlist", "Q3: Rented Momentum",
            "Watch: Neutral Zone", "Q4B: Fundamentals Fading", "Q4C: Technical Breakdown",
            "Q4: Broken",
        ]
    )

    story.append(Paragraph("Executive Summary", h2))
    story.append(Paragraph(
        f"{n} assets scored across both engines this cycle. Breakdown by quadrant \u2014 "
        f"{quadrant_summary}. {euphoria} euphoria-veto flags and {traps} liquidity-trap flags "
        f"were triggered; scores for those names were discounted (\u00d70.60 and \u00d70.70 "
        f"respectively) and new deployment was zeroed out. Quadrant-gated sizing (Q1A/Q1/Q1B/"
        f"Q1C: 100%, Q2/Q3: 35%, Watch/Q4B/Q4C/Q4: 0% of the raw formula) is reflected in the "
        f"figures below. Total suggested new deployment across non-vetoed names: "
        f"${total_alloc:,.0f} ({total_alloc / total_capital * 100:.0f}% of stated capital "
        f"${total_capital:,.0f}).", body,
    ))

    # Top buys
    story.append(Paragraph("Top Buys (highest Simon Score, not vetoed)", h2))
    top_buys = scored[~(scored["Euphoria Veto"] | scored["Liquidity Trap"])].sort_values(
        "Simon Score", ascending=False
    ).head(10)
    cols = [TECH_KEY, "Simon Score", "Momentum Score", "Valuation Score", "Quadrant", "Computed Allocation ($)"]
    story.append(_table_from_df(top_buys, cols))

    # Sub-score breakdown for anchor / building names
    story.append(Paragraph("Sub-Score Breakdown \u2014 Anchors & Building Names", h2))
    anchors = scored[scored["Quadrant"].isin([
        "Q1A: Institutional Sweet Spot", "Q1: Macro Anchor",
        "Q1B: Momentum Building", "Q1C: Building Conviction",
    ])].sort_values("Simon Score", ascending=False)
    anchor_cols = [TECH_KEY, "Quadrant", "Momentum Score", "Quality Composite",
                   "Valuation Score", "Crisis Resilience Score", "Simon Score"]
    if anchors.empty:
        story.append(Paragraph("No names currently qualify.", body))
    else:
        story.append(_table_from_df(anchors, anchor_cols))

    # Tripwires
    story.append(Paragraph("New Tripwires vs. Last Month", h2))
    if tripwires is None or tripwires.empty:
        story.append(Paragraph("No previous-month file supplied, or no threshold crossings detected.", body))
    else:
        story.append(_table_from_df(tripwires, ["Ticker", "Signal", "Prev", "Now", "Direction", "Confirmed"]))

    # Euphoria & liquidity trap risks
    story.append(Paragraph("New Euphoria Risks", h2))
    eup = scored[scored["Euphoria Veto"]][[TECH_KEY, "Health Score", "Valuation Status", "Expectations Burden"]]
    if eup.empty:
        story.append(Paragraph("None flagged this cycle.", body))
    else:
        story.append(_table_from_df(eup, list(eup.columns)))

    story.append(Paragraph("Liquidity Traps", h2))
    traps_df = scored[scored["Liquidity Trap"]][[TECH_KEY, "Health Score", "Conviction Score", "Quality Score"]]
    if traps_df.empty:
        story.append(Paragraph("None flagged this cycle.", body))
    else:
        story.append(_table_from_df(traps_df, list(traps_df.columns)))

    # Portfolio rebalancing
    story.append(PageBreak())
    story.append(Paragraph("Portfolio Changes \u2014 Rebalancing Recommendations", h2))
    if rebalance_df is None or rebalance_df.empty:
        story.append(Paragraph("No current-portfolio file supplied this cycle.", body))
    else:
        held = rebalance_df[rebalance_df.get("Held", False) == True]  # noqa: E712
        rebal_cols = [TECH_KEY, "Current Weight (%)", "Target Weight (%)", "Quadrant", "Recommendation"]
        if held.empty:
            story.append(Paragraph("No holdings matched this month's dual-engine universe.", body))
        else:
            story.append(_table_from_df(held.sort_values("Current Weight (%)", ascending=False), rebal_cols))

    # Suggested allocation table
    story.append(PageBreak())
    story.append(Paragraph("Suggested Allocation \u2014 Full Book", h2))
    alloc_cols = [TECH_KEY, "Quadrant", "Simon Score", "Technical Multiplier",
                  "Conviction Multiplier", "Quadrant Sizing Gate", "Computed Allocation ($)"]
    story.append(_table_from_df(
        scored.sort_values("Computed Allocation ($)", ascending=False), alloc_cols
    ))

    doc.build(story)
    return buf.getvalue()
