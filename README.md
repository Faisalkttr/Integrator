# Dual Engine Portfolio Synchronizer (v2)

A Streamlit app that merges your monthly **Technical Engine** export and
**Fundamental Engine** export, scores every asset on four sub-scores
(Momentum / Quality / Valuation / Crisis Resilience) blended into a
penalty-adjusted **Simon Score**, classifies each into a quadrant
(including **Q1A Institutional Sweet Spot**), applies a manual macro
regime overlay, flags euphoria/liquidity-trap risk, sizes positions,
detects **confirmed** month-over-month tripwires, compares against your
current holdings for rebalancing, and produces a downloadable
investment-committee PDF.

## Files

```
app.py                Streamlit UI + orchestration
scoring_engine.py      Sub-scores, penalty-adjusted Simon Score, veto rules
quadrant_engine.py     Q1A/Q1/Q2/Q3/Q4 classification
regime_engine.py       Manual macro regime overlay (Crisis/Expansion/etc.)
tripwire_engine.py     Month-over-month threshold crossings with confirmation
rebalance_engine.py    Current holdings vs. target allocation
reports.py             PDF report builder (reportlab)
requirements.txt       Python dependencies
```

## Expected CSV columns

**Fundamental CSV** (key column: `Ticker`)
`Ticker, Section, Layer, Structural Weight, Core, Valuation Status,
Expectations Status, Quality Status, Valuation Multiplier,
Expectations Burden, Quality Score, Conviction Score,
Suggested $ Deployment, Notes`

**Technical CSV** (key column: `Asset`)
`Section, Layer, Asset, Benchmark, Status, Health Score, LT Score,
LT Score Basis, Regime, Sector Rank, Sector Percentile, 1M Return,
3M Return, 63D Alpha vs BM, Vol-Adjusted RS, Trend R², RS Acceleration,
200D Trend Slope, 252D Slope, 12-1 Rel Mom, Drawdown Efficiency,
Max Drawdown, Up Capture, Down Capture, Up Capture (LT),
Down Capture (LT), Crisis Alpha, Crisis Alpha (LT), Real Days,
Data Fill %, FX Mismatch`

These match your `TECHNICAL_..._export.csv` and `..._export.csv`
exporter output exactly, so no reformatting is needed before upload.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on GitHub + Streamlit Community Cloud (free)

1. Create a new GitHub repo, e.g. `dual-engine-portfolio`.
2. Add `app.py`, `reports.py`, and `requirements.txt` to the repo root
   and push:
   ```bash
   git init
   git add .
   git commit -m "Dual Engine Portfolio Synchronizer"
   git branch -M main
   git remote add origin https://github.com/<you>/dual-engine-portfolio.git
   git push -u origin main
   ```
3. Go to **share.streamlit.io**, sign in with GitHub, click **New app**,
   pick the repo/branch and set the main file to `app.py`. Deploy.
4. Every month: open the app, upload that month's Technical + Fundamental
   CSVs in the sidebar, and (optionally) upload **last month's downloaded
   "scored export" CSV** to unlock tripwire detection — the app treats
   its own previous output as the historical baseline, so no database is
   required.

## How scoring works

- **Four sub-scores** (0–100 each), computed from your columns. Note:
  quadrant membership and the euphoria/liquidity-trap vetoes deliberately
  stay on **Health Score (63-day)** throughout this app — that's an
  explicit choice (see "Technical Score Basis" below), not an oversight.
  Momentum and Crisis Resilience below are display/ranking metrics only
  (nothing vetoes or classifies off them), so they're built to honestly
  reflect a long horizon instead:
  - **Momentum** — weighted blend of LT Score (45%), 12-1 Rel Mom (30%),
    252D Slope (15%) — all genuinely 252-day/skip-month signals — plus
    a small 63D Alpha weight (10%) as a "is the market starting to
    confirm right now" tiebreaker. Health Score is deliberately excluded
    here since it already drives quadrants/vetoes separately.
  - **Quality Composite** — raw Quality Score from your Fundamental
    Engine. This is deliberately *not* averaged with Conviction Score:
    on real data, Conviction Score correlates ~0.65 with Valuation Score
    (it already bakes in the Valuation Multiplier upstream), while raw
    Quality Score correlates only ~0.08. Averaging them in would quietly
    double-count valuation inside the leg that's supposed to sit
    independently next to Valuation Score below. Conviction Score is
    still used elsewhere (Conviction Multiplier in position sizing, and
    the liquidity-trap check) - just not folded into this metric.
  - **Valuation** — a base score from Valuation Status (Value Zone=100
    down to Tactical Valuation Halt=10) minus Expectations Burden
    (capped at 30 points of penalty)
  - **Crisis Resilience** — weighted blend of Crisis Alpha (LT) (45%),
    inverted Down Capture (LT) (30%), Up Capture (LT) (10%), and
    full-period Max Drawdown (15%) — all 252-day-window metrics. The
    63-day Crisis Alpha and Drawdown Efficiency are deliberately excluded:
    per the Technical Engine's own source, Drawdown Efficiency divides a
    63-day alpha by a 63-day drawdown, so both are quarterly signals
    that don't belong in a score meant to describe year-long resilience.

  \u26a0\ufe0f **Batch-relative normalization caveat**: every `normalize_0_100`
  call above (Alpha, Rel-Mom, 252D Slope, Crisis Alpha (LT), capture
  ratios, Max Drawdown) is min-max rescaled to the *current upload's*
  range (see `normalize_0_100`'s docstring in `scoring_engine.py`). LT
  Score and Health Score are absolute-scale and mean the same thing
  every month; the normalized inputs don't. This is fine for ranking
  names within a single month's file, but means the same ticker's
  Momentum/Crisis Resilience score isn't a fixed yardstick across
  different months if the uploaded universe's spread changes.

- **Technical Score Basis**: quadrant membership (Technical Green/
  Neutral/Red bands) and both vetoes use **Health Score**, which is your
  Technical Engine's 63-day trading-window score, NOT its 252-day LT
  Score - these are genuinely different numbers computed in the same
  engine (`app__plotv2_.py`'s `generate_automated_scoring`, mode=
  "trading" vs mode="longterm"; on real data Health Score and LT Score
  correlate only ~0.12). This means quadrants and vetoes react to
  quarterly price action, not year-long trend - a deliberate choice, not
  a bug: it keeps the euphoria/liquidity-trap vetoes fast-reacting to
  acute risk, at the cost of possibly classifying a name like VRSN
  (Health 2.6, LT Score 91.7) as Technical Red / $0 allocation during a
  rough quarter despite a strong 12-month trend. If you'd rather
  quadrants/vetoes react to the 252-day LT Score instead, that's a
  `quadrant_engine.py` / `scoring_engine.py` change - ask for it
  explicitly, since it changes which names qualify for new capital.
- **Simon Score** = weighted blend of the four sub-scores (defaults:
  35% Momentum / 25% Quality / 25% Valuation / 15% Crisis — adjustable
  in the sidebar), then:
  - **×0.60** if Euphoria Veto is triggered
  - **×0.70** if Liquidity Trap is triggered
  - **+ Regime Adjustment** from the macro overlay (see below), clipped to 0–100
- **Quadrants**: every asset is placed on a 3x3 grid — Technical status
  (Green: Health ≥ 60, Neutral: 40–60, Red: < 40) crossed with
  Fundamental status (Green: Conviction ≥ 65, Neutral: 50–65, Red: < 50)
  — so nothing falls through into an undefined middle zone the way the
  original four-quadrant spec did:
  - **Q1A: Institutional Sweet Spot** — Tech Green, Fund Green, no
    halt/euphoria, Expectations Burden < 15
  - **Q1: Macro Anchor** — same as Q1A but Burden ≥ 15
  - **Q1B: Momentum Building** — Tech Green, Fund Neutral, confirmed
    (technicals already strong, fundamentals catching up)
  - **Q1C: Building Conviction** — Tech Neutral, Fund Green
    (fundamentals strong, technicals catching up)
  - **Q2: Tripwire Watchlist** — Tech Red, Fund Green
  - **Q3: Rented Momentum** — Tech Green AND (Fund Red OR a valuation
    halt/euphoria flag) — a halt/euphoria flag excludes a name from
    Q1/Q1A/Q1B even if Health looks strong, so fundamentals veto
    technicals rather than being a cosmetic label next to an unchanged score
  - **Watch: Neutral Zone** — Tech Neutral, Fund Neutral
  - **Q4B: Fundamentals Fading** — Tech Neutral, Fund Red
  - **Q4C: Technical Breakdown** — Tech Red, Fund Neutral
  - **Q4: Broken** — Tech Red, Fund Red
  - **Unclassified (missing data)** — only when Health or Conviction is
    genuinely missing from the source CSV
- **Euphoria veto**: Health > 70 AND (Valuation Status contains "Halt"
  OR Expectations Burden > 15) → new deployment forced to $0, score ×0.60.
- **Liquidity trap veto**: Conviction > 70 AND Quality > 80 AND Health
  < 40 → new deployment forced to $0, score ×0.70.
- **Position sizing**: `Total Capital × Structural Weight% ×
  (Conviction/100) × Technical Multiplier`, where the technical
  multiplier is 1.2 (Health > 70), 1.0 (50–70), 0.7 (40–50), or 0
  (< 40).
- **Macro regime overlay** (sidebar dropdown: Neutral / Crisis /
  Expansion / Inflation / Deflation / Stagflation): a rules-based
  overlay — not a live data feed — that tags each name's sector/layer
  (e.g. "Monetary Royalties" → crisis hedge, "AI/SEMIS" → high-beta
  growth) and nudges the score up or down accordingly. In Crisis mode,
  for example, royalty names like FNV/WPM get +15 while AI/SEMIS names
  get −10. See `regime_engine.py` to adjust the category rules or point
  size of the nudges.
- **Tripwires**: compares this month's Health/Conviction scores per
  ticker against last month's uploaded scored export and flags any
  crossing of the 40/50/70 (Health) or 65/70 (Conviction) thresholds.
  Upward Health crossings are marked **Confirmed** only when 63D Alpha
  vs Benchmark is positive and Regime isn't Bear — this filters out
  false bottoms (a name technically crossing 40 on a dead-cat bounce
  inside a broader downtrend still shows up, but flagged Unconfirmed).
- **Portfolio rebalancing**: upload a CSV with `Ticker, Shares, Current
  Value` (or `Ticker, Shares, Current Price`) and every held name gets
  a recommendation:
  - **Exit** — vetoed or in Q4: Broken
  - **Trim** — current weight > 1.25× target weight
  - **Buy More** — current weight < 0.75× target weight and not vetoed
  - **Hold** — otherwise
  - **New Buy** — not currently held, in Q1/Q1A, and has a nonzero target allocation
- **Quadrant-gated sizing** (sidebar toggle, on by default): the raw
  sizing formula only zeroes out Health < 40 names, so without this
  gate, **Watch: Neutral Zone** and **Q4B: Fundamentals Fading** names
  (Health is moderate, not low) can still receive full-size dollar
  allocations despite having no confirmed edge. The gate keeps 100% of
  the raw formula for Q1A/Q1/Q1B/Q1C, cuts Q2/Q3 to 35%, and zeroes
  Watch/Q4B/Q4C/Q4. Both the pre-gate and post-gate dollar figures are
  shown side by side in the quadrant tables so you can see exactly what
  got cut and why. Turn it off to see the original ungated formula.
  Adjust the percentages in `quadrant_engine.QUADRANT_SIZING_GATE`.
- **Duplicate ticker detection**: if the same ticker appears more than
  once in either uploaded CSV (e.g. two exchange listings sharing a
  symbol, or a stale exporter row), the app warns you by name and keeps
  only the first occurrence so the merge doesn't silently double-count
  that name's allocation. Check your exporter if this fires.
- **Capital utilization check**: the dashboard shows total suggested
  new deployment as a % of your stated capital, with a warning if the
  book still adds up to more than 100% — each name is sized
  independently from its own structural weight, so this can happen
  even with the sizing gate on. Treat the ranking as a priority order
  for a limited contribution, not a set of amounts to deploy all at once.

## Notes on your specific files

Only tickers present in **both** files are scored (dual-engine
requirement). Tickers found in only one file are still shown in
"Fundamental-only" / "Technical-only" expanders so nothing silently
disappears — useful for spotting exporter coverage gaps between the two
tools.

## Extending

- **Live macro regime data**: the current regime overlay is a manual
  dropdown using sector/layer tags, not live Treasury/gold/BTC/DXY/PMI
  data. Wiring in a real feed (e.g. FRED API for yields, a crypto/metals
  price API) would let the app auto-select the regime instead of asking
  you to pick it — a natural v3 addition inside `regime_engine.py`.
- **Persistent historical database**: Streamlit Cloud's filesystem is
  ephemeral, so this app uses "upload last month's export" instead of
  SQLite. If you deploy somewhere with persistent disk (e.g. a small
  VM), you can swap in `sqlite3` to store `historical.sqlite`
  automatically instead of requiring a manual upload each month.
