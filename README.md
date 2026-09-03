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

- **Four sub-scores** (0–100 each), computed from your columns:
  - **Momentum** — average of Health Score, LT Score, normalized 63D
    Alpha vs Benchmark, normalized 12-1 Relative Momentum
  - **Quality Composite** — average of Quality Score and Conviction Score
  - **Valuation** — a base score from Valuation Status (Value Zone=100
    down to Tactical Valuation Halt=10) minus Expectations Burden
    (capped at 30 points of penalty)
  - **Crisis Resilience** — average of normalized Crisis Alpha, Crisis
    Alpha (LT), and Drawdown Efficiency
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
