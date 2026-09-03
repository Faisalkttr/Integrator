"""Month-over-month tripwire detection.

Upward Health crossings are marked "Confirmed" only when 63D Alpha vs
Benchmark is positive and the current Regime isn't Bear - this filters out
false bottoms where a name technically crosses a threshold on a dead-cat
bounce inside a broader downtrend. Downward crossings and Conviction
crossings are always reported since those are risk-off signals that
shouldn't be gated on confirmation.
"""

import pandas as pd

HEALTH_THRESHOLDS = [40, 50, 70]
CONVICTION_THRESHOLDS = [65, 70]


def detect_tripwires(current: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    key = "Ticker" if "Ticker" in current.columns else "Asset"
    prev_key = "Ticker" if "Ticker" in previous.columns else "Asset"

    prev_cols = [c for c in [prev_key, "Health Score", "Conviction Score"] if c in previous.columns]
    merged = current.merge(
        previous[prev_cols], left_on=key, right_on=prev_key,
        suffixes=("", " (Prev)"), how="inner",
    )

    events = []
    for _, row in merged.iterrows():
        h_prev, h_now = row.get("Health Score (Prev)"), row.get("Health Score")
        c_prev, c_now = row.get("Conviction Score (Prev)"), row.get("Conviction Score")
        alpha63 = row.get("63D Alpha vs BM")
        regime = row.get("Regime")

        for t in HEALTH_THRESHOLDS:
            if pd.notna(h_prev) and pd.notna(h_now):
                if h_prev < t <= h_now:
                    confirmed = (pd.notna(alpha63) and alpha63 > 0) and (regime != "Bear")
                    events.append({
                        "Ticker": row[key], "Signal": f"Health crossed above {t}",
                        "Prev": round(h_prev, 1), "Now": round(h_now, 1),
                        "Direction": "\U0001F7E2 Improving",
                        "Confirmed": "\u2705 Confirmed" if confirmed else "\u26a0\ufe0f Unconfirmed",
                    })
                elif h_prev >= t > h_now:
                    events.append({
                        "Ticker": row[key], "Signal": f"Health crossed below {t}",
                        "Prev": round(h_prev, 1), "Now": round(h_now, 1),
                        "Direction": "\U0001F534 Deteriorating", "Confirmed": "\u2014",
                    })

        for t in CONVICTION_THRESHOLDS:
            if pd.notna(c_prev) and pd.notna(c_now):
                if c_prev < t <= c_now:
                    events.append({
                        "Ticker": row[key], "Signal": f"Conviction crossed above {t}",
                        "Prev": round(c_prev, 1), "Now": round(c_now, 1),
                        "Direction": "\U0001F7E2 Improving", "Confirmed": "\u2014",
                    })
                elif c_prev >= t > c_now:
                    events.append({
                        "Ticker": row[key], "Signal": f"Conviction crossed below {t}",
                        "Prev": round(c_prev, 1), "Now": round(c_now, 1),
                        "Direction": "\U0001F534 Deteriorating", "Confirmed": "\u2014",
                    })

    return pd.DataFrame(events)
