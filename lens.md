# Vector Lens — Engine Architecture & Quantitative Specification

This document is a deep, quantitative description of the Vector Lens engine: how it is structured, how data flows through it, every numerical threshold it uses, every priority it evaluates, every classification rule it applies, and the exact formulas that produce its outputs. It is the design-level companion to the code in `vector/lens/`.

The Lens engine is the analytic brain of Vector. It takes a list of user positions, looks at them through eight independent analyzers, blends those analyzer results into a prioritized list of Calls-To-Action (CTAs), composes a three-sentence English brief about the portfolio's state, computes a single 1–99 "caution score" summarising overall risk pressure, builds a projected portfolio that simulates the CTAs being applied, and writes a deduplicated snapshot of the result to a rolling history file. All of this is deterministic given identical inputs.

---

## Table of Contents

- [1. High-Level Topology](#1-high-level-topology)
- [2. Inputs, Contracts, and the Canonical Positions Summary](#2-inputs-contracts-and-the-canonical-positions-summary)
  - [2.1 Inputs](#21-inputs)
  - [2.2 The empty-portfolio short-circuit](#22-the-empty-portfolio-short-circuit)
  - [2.3 The analyzer interface contract](#23-the-analyzer-interface-contract)
  - [2.4 The canonical positions summary](#24-the-canonical-positions-summary)
- [3. Risk Profiles — How Tiers Bend Every Threshold](#3-risk-profiles--how-tiers-bend-every-threshold)
  - [3.1 The three tiers and their threshold tables](#31-the-three-tiers-and-their-threshold-tables)
  - [3.2 User overrides](#32-user-overrides)
  - [3.3 Conservative-tier extra gates in the CTA engine](#33-conservative-tier-extra-gates-in-the-cta-engine)
- [4. The Analysis Pool](#4-the-analysis-pool)
  - [4.1 Execution order](#41-execution-order)
  - [4.2 Post-processing: index-fund suppression](#42-post-processing-index-fund-suppression)
- [5. The Eight Analyzers — Quantitative Detail](#5-the-eight-analyzers--quantitative-detail)
  - [5.1 Slope (`analyzers/slope.py`)](#51-slope-analyzersslopepy)
  - [5.2 Volatility (`analyzers/volatility.py`)](#52-volatility-analyzersvolatilitypy)
  - [5.3 Concentration (`analyzers/concentration.py`)](#53-concentration-analyzersconcentrationpy)
  - [5.4 Earnings (`analyzers/earnings.py`)](#54-earnings-analyzersearningspy)
  - [5.5 Dividends (`analyzers/dividends.py`)](#55-dividends-analyzersdividendspy)
  - [5.6 Beta (`analyzers/beta.py`)](#56-beta-analyzersbetapy)
  - [5.7 Performance (`analyzers/performance.py`)](#57-performance-analyzersperformancepy)
  - [5.8 Index Fund (`analyzers/index_fund.py`)](#58-index-fund-analyzersindex_fundpy)
- [6. The CTA Engine — Eleven Priorities](#6-the-cta-engine--eleven-priorities)
  - [6.1 Helpers and gates used throughout](#61-helpers-and-gates-used-throughout)
  - [6.2 Priority 1 — Steep decline (SELL)](#62-priority-1--steep-decline-sell)
  - [6.3 Priority 2 — Excessive volatility (SELL)](#63-priority-2--excessive-volatility-sell)
  - [6.4 Priority 3 — Winner drift (REBALANCE or informational HOLD)](#64-priority-3--winner-drift-rebalance-or-informational-hold)
  - [6.5 Priority 4 — Index fund informational (HOLD)](#65-priority-4--index-fund-informational-hold)
  - [6.6 Priority 5 — High portfolio beta (BUY)](#66-priority-5--high-portfolio-beta-buy)
  - [6.7 Priority 6 — Single-stock concentration (BUY — up to 3 CTAs)](#67-priority-6--single-stock-concentration-buy--up-to-3-ctas)
  - [6.8 Priority 7 — Sector over-concentration (BUY — up to 3 CTAs)](#68-priority-7--sector-over-concentration-buy--up-to-3-ctas)
  - [6.9 Priority 8 — Dead weight (SELL — suppressed for conservative)](#69-priority-8--dead-weight-sell--suppressed-for-conservative)
  - [6.10 Priority 9 — Underrepresented sector (BUY — up to 3 CTAs)](#610-priority-9--underrepresented-sector-buy--up-to-3-ctas)
  - [6.11 Priority 10 — Unrealized loss (HOLD)](#611-priority-10--unrealized-loss-hold)
  - [6.12 Priority 11 — Portfolio healthy (HOLD)](#612-priority-11--portfolio-healthy-hold)
  - [6.13 Post-processing: sort, index suppression, dedup, tiny-buy drop, total-buy cap](#613-post-processing-sort-index-suppression-dedup-tiny-buy-drop-total-buy-cap)
- [7. The Sentence Composers](#7-the-sentence-composers)
  - [7.1 Deterministic template selection](#71-deterministic-template-selection)
  - [7.2 Sentence 1 — portfolio state (slope + volatility + P&L)](#72-sentence-1--portfolio-state-slope--volatility--pl)
  - [7.3 Sentence 2 — timing/catalyst (earnings + dividends)](#73-sentence-2--timingcatalyst-earnings--dividends)
  - [7.4 Sentence 3 — call to action](#74-sentence-3--call-to-action)
- [8. The Top-Level Assembler](#8-the-top-level-assembler)
  - [8.1 Pipeline orchestration](#81-pipeline-orchestration)
  - [8.2 Brief assembly](#82-brief-assembly)
  - [8.3 Top CTA extraction](#83-top-cta-extraction)
  - [8.4 Caution score](#84-caution-score)
  - [8.5 Projected positions](#85-projected-positions)
  - [8.6 The result dict](#86-the-result-dict)
  - [8.7 Snapshot persistence](#87-snapshot-persistence)
- [9. Failure Modes and Defensive Behavior](#9-failure-modes-and-defensive-behavior)
- [10. Determinism and Reproducibility](#10-determinism-and-reproducibility)
- [11. Quick Reference — Numerical Constants Summary](#11-quick-reference--numerical-constants-summary)
- [12. Where to Look in the Code](#12-where-to-look-in-the-code)

---

## 1. High-Level Topology

Conceptually the engine is a tree-shaped pipeline with five named layers:

1. **Risk profile loader** — pulls the user's risk tier from settings and produces an override-aware threshold dictionary used by every downstream analyzer.
2. **Analysis pool** — runs all eight analyzers in a controlled order (slope and volatility first, then earnings, then everything else), then applies post-processing to suppress concentration flags on index ETFs.
3. **CTA engine** — reads the pool's combined output and emits a list of CTAs across eleven priority levels, each carrying an action verb, a target ticker, a dollar amount, a reason code, a severity, and a structured detail dict.
4. **Sentence composers** — three independent composers (sentence1 portfolio state, sentence2 timing/catalyst, sentence3 action) each pull a deterministic template from a shared JSON file and fill it with analyzer-derived variables.
5. **Top-level assembler** — joins the three sentences into a single brief, maps the top CTA's action to a color, computes the caution score, applies every CTA to a deep copy of positions to build a projected portfolio, writes a snapshot to the rolling history if anything material changed, and returns either a 7-tuple (for the dashboard widget) or a full result dict (for the dedicated Lens page).

Two thin entry points wrap the assembler. `generate_lens()` returns the canonical 7-tuple `(brief, color, recommended_tickers, deposit_amount, underweight_sector, action_type, caution_score)` used by `LensDisplay.refresh()` on the dashboard. `generate_lens_full()` returns the complete result dict consumed by the dedicated Vector Lens page (which renders the brief, caution score, CTA report, two projection graphs, and two allocation pies). Both call the same underlying `build_lens_output()`; the 7-tuple is just a flattened slice of the same dict.

The engine has no global state outside of (a) the sentence template cache, populated on first use, and (b) the rolling `lens_history.json` file on disk. Every call to `build_lens_output()` is otherwise stateless and idempotent for identical inputs.

---

## 2. Inputs, Contracts, and the Canonical Positions Summary

### 2.1 Inputs

`build_lens_output()` accepts three arguments:

- **`positions`** — a list of plain dictionaries, each with at minimum: `ticker` (uppercase symbol), `shares` (float), `equity` (cost basis in dollars at entry, i.e. `shares × entry_price`), `price` (most recent quote), `sector` (string, may be `"Unknown"`), and `name` (display label). The store also enriches these with `added_at` timestamps. The Lens engine never mutates the caller's list shape but does decorate each dict in place with a `_current_value` field during the analysis pool's preflight, plus an inferred `price` if missing.
- **`store`** — the `DataStore` instance. The engine treats it as a read-only oracle: it calls `get_snapshot(ticker, refresh)`, `get_history(ticker, period, refresh)`, `get_quote(ticker)`, `get_meta(ticker)`, `get_dividends(ticker)`, and `get_earnings(ticker)`. The Lens engine never writes to the store and never invalidates store caches.
- **`settings`** — the user's settings dict. The engine reads `risk_tier` (default `"regular"`), `refresh_interval` (default `"5 min"`), and `lens_signals` (per-threshold overrides surfaced in Settings → Lens Signal Thresholds).

A fourth boolean flag — `save_history` — controls whether a snapshot is appended to `lens_history.json` on success. The debug runner sets this to `False` so synthetic-portfolio runs do not pollute the user's real Lens history.

### 2.2 The empty-portfolio short-circuit

If the input `positions` list is empty, `build_lens_output()` returns a fixed onboarding result without invoking any analyzer, CTA logic, or sentence composer. The brief reads: *"Add your first position to see Lens analytics tailored to your actual holdings."* All numeric fields are zero, the action type is `hold`, and the color is the neutral `#8d98af`. This is the only path that bypasses the full pipeline.

### 2.3 The analyzer interface contract

Every analyzer module exposes a single function with the signature:

```python
def analyze(positions, store, settings, risk_profile, **kwargs) -> dict
```

The return value is always a dict with two top-level keys:

- **`ticker_results`** — a `dict[str, dict]` mapping each ticker symbol to its per-ticker result.
- **`portfolio_result`** — a single dict for the portfolio-level aggregate.

Each per-ticker and portfolio result has the shape `{'value': float, 'severity': str, 'flag': bool, 'weight': float, 'details': dict}` where:

- `value` is the analyzer's primary numeric output (annualized slope %, annualized vol %, weight %, beta multiple, days-until-event, unrealized return %, etc.).
- `severity` is one of `'none'`, `'low'`, `'moderate'`, `'high'`, `'critical'` (the canonical 5-level ladder used by the whole engine, with severity-ordering map `{none: 0, low: 1, moderate: 2, high: 3, critical: 4}`).
- `flag` is a boolean shortcut: True if this result should be considered actionable by the CTA engine. Analyzers compute this from severity plus any additional gates (e.g. volatility only flags when weight > 15%; concentration only flags when at least one sub-signal triggers).
- `weight` is the ticker's portfolio weight expressed as a fraction (0.0–1.0), used by sentence composers for impact ranking.
- `details` is an analyzer-specific dict carrying everything the CTA engine and sentence composers might need (e.g. `annualized_pct`, `direction`, `sub_signals`, `drift_multiple`, `entry_weight_pct`, `outlook`, `next_earnings_date`, `beta`, `entry_price`, etc.).

Earnings is the one analyzer that accepts an additional keyword argument: `prior_results`, a dict containing the slope and volatility analyzer outputs. This lets earnings compute its `outlook` field (`beat_likely`, `miss_risk`, or `neutral`) by reading the per-ticker slope and volatility numbers already computed in phase 1.

### 2.4 The canonical positions summary

The analysis pool's first action — before any analyzer runs — is to build a single dict it calls the **canonical positions summary**, attached to the pool result as `_positions_summary`. Every weight calculation anywhere downstream must come from this dict; the pool's docstring is explicit on this point. Its shape is:

```
{
    'total_equity': float,                       # sum of current market values
    'ticker_weights': dict[str, float],          # per-ticker weight, sums to ~1.0
    'ticker_current_prices': dict[str, float],   # per-ticker live quote
    'ticker_current_values': dict[str, float],   # shares × current price
    'sector_weights': dict[str, float],          # per-sector weight, sums to ~1.0
}
```

The summary is built by `_build_positions_summary()` in three steps:

1. For each ticker, fetch the current snapshot from the store. If the snapshot has a usable price, use it; otherwise fall back to the position's stored `price` field. The resulting `ticker_current_prices` dict is the ground-truth quote map for the run.
2. For each ticker, multiply `shares × ticker_current_prices[ticker]` to produce `ticker_current_values`. Sum across all tickers to get `total_equity`.
3. Divide each ticker's current value by `total_equity` to get `ticker_weights`. Aggregate by sector to get `sector_weights`.

If `total_equity` is zero (every position has shares=0 or no quote available), the summary is built with empty weight dicts and a `total_equity` of 0.0, which downstream code treats as a sentinel by clamping divisions to a minimum of 1.0.

After the summary is built, the pool enriches each position dict in place with two fields: `_current_value` (its `ticker_current_values` entry) and, if the position dict's own `price` is missing, the freshly resolved `price`. This in-place enrichment is why all analyzers can compute current value via a small helper `_cv(p)` that prefers `_current_value` before falling back to `shares × price` and then to cost-basis `equity` as a last resort.

A debug sanity check runs at the end: if `ticker_weights` summed across tickers is more than 0.01 off from 1.0 (with non-zero total_equity), the pool prints a `[lens DEBUG]` warning with the full weight breakdown. This is a development guardrail against silent weight-summing bugs.

---

## 3. Risk Profiles — How Tiers Bend Every Threshold

The Lens engine's behavior is governed by three risk tiers stored as `DEFAULT_RISK_PROFILES` in `vector/constants.py`:

### 3.1 The three tiers and their threshold tables

The `high` tier (Aggressive) is the most permissive — it lets stocks fall further, swing harder, and concentrate heavier before flagging anything. The `regular` tier (Moderate, the default) sits in the middle. The `low` tier (Conservative) is the most cautious and trips on smaller moves.

| Analyzer | Field | high (Aggressive) | regular (Moderate, default) | low (Conservative) |
|---|---|---|---|---|
| slope | critical | -50 % annualized | -40 % | -35 % |
| slope | high | -35 % | -28 % | -25 % |
| slope | moderate | -20 % | -15 % | -12 % |
| volatility | critical | 80 % annualized | 65 % | 55 % |
| volatility | high | 60 % | 50 % | 42 % |
| volatility | moderate | 45 % | 35 % | 30 % |
| concentration | critical | 60 % single-stock weight | 50 % | 40 % |
| concentration | high | 50 % | 40 % | 30 % |
| concentration | moderate | 40 % | 30 % | 20 % |
| beta | critical | 2.2 | 1.8 | 1.4 |
| beta | high | 1.6 | 1.3 | 1.1 |
| beta | moderate | 1.2 | 1.0 | 0.8 |
| performance | critical | -60 % unrealized loss | -50 % | -40 % |
| performance | high | -40 % | -30 % | -25 % |
| performance | moderate | -25 % | -18 % | -15 % |
| sell_scale | — | 0.25 (fraction of position sold per CTA) | 0.50 | 0.10 |

(Note: `sell_scale` is later read in `cta_engine.py` as 0.30/0.50/0.15 in the code's docstrings — the actual numeric source of truth is whatever `DEFAULT_RISK_PROFILES` holds at runtime.)

The `sell_scale` is the most powerful single dial: it sets the fraction of a flagged position's current value that a sell-type CTA recommends trimming. A conservative user's `sell_scale` of 0.10 means even a critical-severity decline triggers a CTA to sell only 10% of the position. Aggressive users at 0.25 sell up to 25% and moderate at 0.50 sells up to 50%, doubling the recommended trim amount.

### 3.2 User overrides

After `load_risk_profile()` selects the tier's default thresholds, it walks the user's `settings["lens_signals"]` dict and applies eight possible overrides:

- `stock_concentration_pct` → `profile['concentration']['moderate']`
- `sector_concentration_pct` → `profile['concentration']['sector_moderate']`
- `steep_downtrend_pct` → `profile['slope']['high']`
- `high_beta_threshold` → `profile['beta']['high']`
- `stock_vol_threshold_pct` → `profile['volatility']['high']`
- `dead_weight_pct` → `profile['dead_weight_pct']` (top-level, used by CTA priority 8)
- `loss_threshold` → `profile['performance']['moderate']`
- `winner_drift_multiple` → `profile['winner_drift_multiple']` (top-level)

The override pattern is intentional: it only mutates the *named* threshold, leaving the rest of the tier's ladder intact. A user who increases their stock concentration threshold from 30 % to 35 % still has the tier's critical/high concentration values unchanged.

**The "changed away from default" gate.** An override is applied **only when the user has deliberately moved that setting off its shipped default** — the `_changed(ls, key)` helper compares the value in `settings["lens_signals"]` against `DEFAULT_SETTINGS['lens_signals']` (numeric compare when both parse as floats, equality otherwise; a key absent from settings is treated as unchanged). Values left at the shipped default defer to the active risk tier. This gate is deliberate and important: applying the shipped defaults *unconditionally* (the old behaviour) overwrote the per-tier thresholds with a single cross-tier value, flattening Conservative/Moderate/Aggressive and even inverting their ordering — e.g. Conservative concentration `moderate` = 35 would end up **greater than** its `high` = 30, so a 34 % holding skipped straight past `moderate` to `high`. With the gate, an untouched setting honours the tier (so the tier selection stays meaningful and monotonic) while a value the user actually changed still wins.

### 3.3 Conservative-tier extra gates in the CTA engine

The CTA engine reads `risk_profile['tier']` directly and applies additional gates that go beyond threshold adjustments:

- Priority 1 (steep decline) and Priority 2 (excessive volatility) only fire on `critical` severity for conservative users — `high`-severity flags are suppressed.
- Priority 3 (winner drift) is converted from `rebalance` to an informational `hold` with a new reason code `winner_drift_informational` for conservative users.
- Priority 8 (dead weight) is suppressed entirely.
- All sell-type CTAs run through `_conservative_sell_blocked(ticker, severity, ticker_weight)`, which blocks the sell if: market cap is > $5B (or unknown — the conservative default is to *assume large cap and block*), severity isn't `critical`, or the ticker's weight is below 5 %.
  - **Dominant-position exception (don't regress):** the very first check inside the gate is `if ticker_weight > 0.50: return False` — a holding that is more than **half the book** is *always* eligible to be trimmed, even for a conservative investor. Without this exception a 78 %-in-one-leveraged-ETF book had its sell suppressed and was instead told to *deposit* tens of thousands of dollars to dilute the position back down (unactionable). The dominant-position check runs before the market-cap, severity, and weight-floor checks, so it overrides all of them.

The market-cap lookup in `_market_cap()` reads `market_cap` (or `marketCap`) from both the quote dict and the meta dict, returning the first hit. If no value is found anywhere, the function returns 0.0 and the conservative gate substitutes 100 billion dollars (a deliberately high default that blocks the sell). The principle is: when uncertain about whether a stock is large or small, a conservative profile treats it as a large blue-chip not to be touched.

---

## 4. The Analysis Pool

`run_analysis()` is the orchestrator that runs all eight analyzers in three phases and then performs post-processing.

### 4.1 Execution order

**Phase 1 — independents needed by earnings**: `slope` and `volatility` run first. They are independent of each other and of every other analyzer, but earnings depends on their per-ticker results to set its `outlook` field.

**Phase 2 — earnings**: runs with `prior_results={'slope': slope_res, 'volatility': vol_res}` so it can compute `outlook` per ticker.

**Phase 3 — remaining independents**: `concentration`, `dividends`, `beta`, `performance`, and `index_fund` run in arbitrary order — all are independent.

Every analyzer call goes through `_safe_analyze(name, fn, *args, **kwargs)` which catches any exception, logs it at debug level (so it never spams stdout in normal operation), and returns a neutral placeholder result so the rest of the pipeline can proceed. The neutral result has empty `ticker_results` and a portfolio result of `{'value': 0.0, 'severity': 'none', 'flag': False, 'details': {}}`. The Lens engine's design principle is: a single analyzer failure must never prevent the others from producing useful output.

### 4.2 Post-processing: index-fund suppression

After all analyzers complete, the pool walks the index_fund analyzer's `ticker_results`. For every ticker the index_fund analyzer flagged as a large index ETF (broad-market, sector, or otherwise), the pool zeroes out the same ticker's concentration flag (`flag = False`) and downgrades its severity to `'none'`. This is the rule that prevents Vector from telling the user "you are 60 % concentrated in VOO — sell down VOO" when VOO is itself a diversified index fund. The suppression is unidirectional: concentration is suppressed for index ETFs but the index_fund analyzer's own informational flag (which becomes priority 4 in the CTA engine) remains.

The pool's return value bundles all eight analyzer results under their keys, plus three pool-level extras: `_risk_profile` (the resolved profile dict), `_store` (the store reference, threaded so the CTA engine can call `get_quote` and `get_meta` for market-cap lookups), and `_positions_summary` (the canonical summary discussed earlier).

---

## 5. The Eight Analyzers — Quantitative Detail

Every analyzer follows the same outer pattern: iterate over positions, compute per-ticker numbers, classify into the 5-level severity ladder, populate `ticker_results`, then aggregate to a `portfolio_result`. The differences are in what they measure, how they classify, and what extra fields they store under `details`.

### 5.1 Slope (`analyzers/slope.py`)

The slope analyzer measures price-direction over a 6-month lookback per ticker using linear regression. Key constants: `_MIN_DATA_POINTS = 30` (any history with fewer than 30 cleaned daily closes is treated as insufficient data and skipped), `_SLOPE_CLAMP_MIN = -80.0`, `_SLOPE_CLAMP_MAX = 250.0` (the final annualized percentage is clamped to this window to keep outliers from breaking downstream sentence formatting and CTA arithmetic). *The max was raised from 150 to 250 so genuine momentum names show distinct, data-driven figures in the brief instead of all pinning to an identical "+150.0 %". Positive slopes carry no severity — they all classify `none` — so this only affects the displayed value, never CTA logic.*

The per-ticker procedure:

1. Pull 6-month daily closes via `store.get_history(ticker, '6mo', refresh)`.
2. Clean the list — drop None, NaN, and non-positive values.
3. If fewer than 30 cleaned points remain, mark `insufficient_data = True`, log a debug skip, and use 0 for both `raw_slope` and `annualized`.
4. Otherwise call `linear_regression_slope_percent(clean)` (from `vector.analytics`) to get a slope in "percent per trading day" units, then multiply by 252 (trading days per year) to get annualized %.
5. Run a three-stage sanity-correction routine to keep the regression slope from disagreeing wildly with actual price movement:
   - Compute peak-to-current decline annualized as `((last_price - max_price) / max_price) × 100 × 2` (the ×2 converts a 6-month % move to a year). If the regression slope is more than 5 % more negative than this peak-to-current decline, replace the slope with the peak-to-current value. *A stock cannot have fallen more than its actual drawdown from its highest point.*
   - Otherwise, compute trough-to-current rise annualized as `((last_price - min_price) / min_price) × 100 × 2`. If the regression slope is more than 5 % more positive than this trough-to-current rise, replace with the trough-to-current value. *A stock cannot have risen more than its actual climb from its lowest point.*
   - Finally, if the slope still disagrees with actual total return (annualized `(last - first) / first × 100 × 2`) by more than 25 percentage points, override with the actual.

   Each correction logs a debug line naming the ticker and the before/after values.

6. Guard against NaN/Inf — if `annualized` is non-finite after all corrections, reset to 0 and mark insufficient.
7. Clamp the annualized value into `[-80, 250]` and log a debug message if the clamp activated.
8. Classify into severity using `_classify(annualized_pct, thresholds)`:
   - `<= critical` (default -25, or whatever the active tier specifies) → `'critical'`
   - `<= high` (default -15) → `'high'`
   - `<= moderate` (default -5) → `'moderate'`
   - `<= 5` → `'low'`
   - else → `'none'`
9. Compute the `direction` label: `'up'` if annualized > 5, `'down'` if < -5, `'flat'` otherwise.
10. Set `flag = sev in ('moderate','high','critical') and not insufficient_data`.

Portfolio-level slope is the weighted sum of every ticker's raw daily slope multiplied by each ticker's weight, then annualized (× 252) and clamped/classified by the same rules. The portfolio result also tracks three list fields and three counts: `up_tickers`, `down_tickers`, `flat_tickers`, `up_count`, `down_count`, `total_count`. From these counts the portfolio determines its `state`: `'broad_decline'` if more than 70 % of tickers are down, `'broad_uptrend'` if more than 70 % are up, otherwise `'mixed'`. This state field is the primary input to sentence1's portfolio-level template selection.

### 5.2 Volatility (`analyzers/volatility.py`)

Volatility uses a 1-year daily lookback (longer than slope's 6mo for statistical stability) and computes annualized standard deviation of log returns scaled to a percentage. Key constants: `_MIN_DATA_POINTS = 30`, `_VOL_CLAMP_MIN = 0.0`, `_VOL_CLAMP_MAX = 150.0`.

Per-ticker procedure:

1. Pull 1-year history.
2. Clean as in slope.
3. If fewer than 30 cleaned points, return 0.0 with a debug skip.
4. Otherwise: compute `log_returns = numpy.diff(numpy.log(prices))`, take `std(log_returns) × sqrt(252) × 100`.
5. Guard against NaN/Inf, clamp into `[0, 150]`, log if clamped.
6. Compute `daily_std = vol / sqrt(252) / 100` for the details dict.
7. Classify using the 5-level volatility ladder:
   - `> critical` (default 55) → `'critical'`
   - `> high` (default 40) → `'high'`
   - `> moderate` (default 28) → `'moderate'`
   - `> low` (default 15) → `'low'`
   - else → `'none'`
8. Flag = `severity in ('high','critical') AND weight > 0.15`. *This is a deliberate guard: tiny positions don't trigger volatility CTAs even if they're individually explosive. The user only sees a sell-for-volatility recommendation when a meaningful chunk of the portfolio is the source of the swings.*

Portfolio-level volatility is the weighted average of per-ticker volatilities (using the same weight assigned per ticker). The portfolio result tracks `most_volatile_ticker` and `most_volatile_vol` for use by sentence composers.

### 5.3 Concentration (`analyzers/concentration.py`)

Concentration is the only analyzer with multiple sub-signals. Each ticker can independently trigger `stock_concentration` (its weight exceeds the moderate threshold), `winner_drift` (it has drifted up to more than 2× its entry weight while also exceeding 30 % current weight), or both. The portfolio-level result is separate and tracks sector over-concentration.

Per-ticker procedure:

1. Use the canonical summary's `_current_value` (already in place from the pool preflight) — divide by `total_current_value` to get the per-ticker `weight` fraction. Multiply by 100 for `weight_pct`.
2. Compute `entry_weight = cost_equity / total_cost_basis` — note this uses *cost basis* on both sides, not market value. The point of `entry_weight` is to answer: "if a user originally allocated 25 % to NVDA at entry, what fraction are they at now?" Mixing cost and market here would corrupt the comparison.
3. Compute `drift_multiple = current_weight / entry_weight` (clamped via the guard `if entry_weight > 0.001 else 1.0`).
4. **Sub-signal A — stock concentration** (skipped if ticker is in `INDEX_ETFS`): classify `weight_pct` against the concentration thresholds. If `> critical` (default 50) → critical; `> high` (default 40) → high; `> moderate` (default 30) → moderate; `> low` (default 20) → low; else none. If severity is moderate, high, or critical, append `'stock_concentration'` to `sub_signals` and set `best_severity`.
5. **Sub-signal B — sector accumulation** (skipped if index ETF): add the ticker's current value to the running `sector_weights` map keyed by `pos['sector']` (or `'Unknown'`).
6. **Sub-signal C — winner drift** (skipped if index ETF): if `weight_pct > 30` AND `drift_multiple > 2.0` AND **`current_value > cost_equity`**, append `'winner_drift'`. Severity is `'high'` if `drift_multiple > 2.5`, else `'moderate'`. The severity ladder's order map (`_SEV_ORDER`) is used to keep `best_severity` at the higher of the two sub-signal severities. *The `current_value > cost_equity` clause is essential and must not be removed: without it, a position that merely fell **less** than its peers (so its current-value weight exceeds its cost-basis weight, making `drift_multiple > 2.0`) gets mislabeled a "winner that drifted" — producing "price appreciation pushed…" language and contradictory SELL+HOLD CTAs on a holding that is actually underwater. The clause requires the position to genuinely be up from cost before it counts as a runaway winner.*

The per-ticker `flag` is True if any sub-signal triggered. The `details.heaviest_concentration_type` is the first sub-signal in the list (an order-dependent field — `'stock_concentration'` is appended before `'winner_drift'` so a ticker with both flags shows stock_concentration as the heaviest type).

Portfolio-level concentration analyzes the accumulated `sector_weights`:

1. Normalize to percentages by dividing each sector's accumulated value by the sum.
2. Compute `sector_count = number of known (non-Unknown) sectors`, falling back to total sector count if all are Unknown.
3. Identify `heaviest_sector` (max-weight sector) and `heaviest_pct`.
4. Classify:
   - `heaviest_pct > 60` OR `sector_count <= 1` → `'high'`
   - `heaviest_pct > sector_moderate` (default 50) OR `sector_count <= 2` → `'moderate'`
   - `heaviest_pct > 40` → `'low'`
   - else → `'none'`
5. **Index-dominated downgrade** (don't regress): compute `index_weight_pct` = (sum of index-ETF current values ÷ total current value) × 100. Index ETFs are excluded from the per-sector tally (sub-signal B above), so a heavily-index book otherwise shows `sector_count ≤ 1/2` and trips a false `high`/`moderate` sector flag — which then produces spurious "buy individual stocks to diversify" CTAs. If `index_weight_pct >= 50` AND `sector_sev` is `moderate` or `high`, downgrade it to `'low'`. The reasoning: the index funds *are* the diversification, so the small non-index remainder is not a concentration problem.
6. Flag = severity in `('moderate', 'high', 'critical')`.

The portfolio details dict includes `sector_weights` (the full per-sector percentage map), `sector_count`, `heaviest_sector`, `heaviest_sector_weight`, and `concentration_type = 'sector'`.

### 5.4 Earnings (`analyzers/earnings.py`)

Earnings depends on slope and volatility (passed in via `prior_results`) to set its `outlook` field. Severity is purely a function of how soon the next earnings event is:

- `days_until <= 7` → `'high'`
- `<= 14` → `'moderate'`
- `<= 30` → `'low'`
- otherwise (or `None`) → `'none'`

Per-ticker procedure:

1. Fetch `store.get_earnings(ticker)` (a list of upcoming earnings records). **Index ETFs are skipped** — a ticker in `INDEX_ETFS` is given an empty earnings list without calling the store, since index funds have no earnings reports (the fetch 404s on Yahoo and wastes an API call); they keep the neutral `'none'` result.
2. Iterate, parse each `date` field via `_parse_date()` (which accepts `date`, `datetime`, or `'%Y-%m-%d'` / `'%Y-%m-%dT%H:%M:%S'` strings).
3. Pick the first event with `ed >= today` — record its date, days-until, and `eps_estimate_avg`.
4. Compute `outlook` from the prior slope/vol analysis via `_determine_outlook(slope_ann, vol_ann)`:
   - If slope > 15 % AND vol ≤ 28 % → `'beat_likely'` (strong steady uptrend with low volatility — historically associated with beats).
   - If slope < -5 % OR vol > 40 % → `'miss_risk'` (declining trend OR chaotic price action — historically associated with misses or large negative reactions).
   - Otherwise → `'neutral'`.
5. Classify severity from `days_until`.
6. Flag = `severity != 'none'`.
7. Track `tickers_with_upcoming` (the list of all flagged tickers) and `nearest_ticker` / `nearest_days` / `nearest_eps` (the portfolio's single closest event).

The portfolio result uses the nearest-event severity. The `value` field is the nearest event's days-until (or `999.0` if no upcoming earnings exist).

### 5.5 Dividends (`analyzers/dividends.py`)

Dividends mirrors earnings' time-to-event severity ladder and adds yield tracking. Per-ticker:

1. Fetch `store.get_dividends(ticker)`.
2. For each dividend record with a parseable date: if the date is within the trailing 12 months (between `today - 365 days` and `today`), add the amount to `annual_div_total`. If the date is in the future and we haven't set `next_ex_date` yet, record it as the next upcoming.
3. Compute `annual_yield_pct = (annual_div_total / current_price) × 100` if both are positive.
4. Severity is the same days-until ladder as earnings (7/14/30 days → high/moderate/low).
5. Flag = severity ≠ 'none'.

Portfolio-level: track `nearest_ticker`, `nearest_days`, `tickers_with_upcoming`, and `portfolio_yield_pct` (weighted sum of per-ticker yields).

### 5.6 Beta (`analyzers/beta.py`)

Beta measures market sensitivity vs SPY. Per-ticker:

1. Fetch SPY 1-year history once (shared across all ticker betas).
2. For each ticker, fetch its 1-year history. Truncate both ticker and SPY to the same length `n = min(len(ticker), len(spy))`. If `n < 10`, default to beta = 1.0 (insufficient data).
3. Compute daily simple returns: `t_ret = numpy.diff(t_arr) / t_arr[:-1]`, same for SPY.
4. Compute SPY return variance. If variance < 1e-12, default beta = 1.0 (degenerate market data).
5. Beta = `numpy.cov(t_ret, s_ret)[0][1] / var_s`.
6. Classify:
   - `beta > critical` (default 1.8) → `'critical'`
   - `> high` (default 1.3) → `'high'`
   - `> moderate` (default 1.0) → `'moderate'`
   - `> 0.5` → `'low'`
   - else → `'none'`
7. Flag = severity in `('high', 'critical')`.

Portfolio beta is computed differently from a per-ticker average: the analyzer builds a `closes_map` of every ticker's history, asks `portfolio_daily_returns(positions, closes_map)` (from `vector.analytics`) for the weighted daily portfolio return series, then computes `portfolio_beta(port_rets, spy_rets)` via covariance-over-variance. If anything in this pipeline fails (any missing history, mismatched lengths) the portfolio beta defaults to 1.0.

### 5.7 Performance (`analyzers/performance.py`)

Performance measures unrealized P&L from cost basis. It is a loss-only flagger — gains never trigger flags. Per-ticker:

1. Compute `entry_price = cost_equity / shares` if shares > 0.
2. Compute `current_value = shares × current_price` if price available, else use `cost_equity`.
3. Compute `unrealized_pct = (current_price / entry_price - 1) × 100`.
4. Compute `unrealized_dollar = current_value - cost_equity`.
5. Classify via the (negative) performance ladder:
   - `< critical` (default -40) → `'critical'`
   - `< high` (default -25) → `'high'`
   - `< moderate` (default -15) → `'moderate'`
   - `< low` (default -5) → `'low'`
   - else → `'none'`
6. Flag = severity in `('moderate', 'high', 'critical')`.

Portfolio-level: sum `total_cost_basis` and `total_current_value` across positions, compute `total_unrealized_pct = (total_unrealized_dollar / total_cost_basis) × 100`, classify with the same ladder. Track `worst_ticker` and `worst_return_pct` for use by sentence composers.

### 5.8 Index Fund (`analyzers/index_fund.py`)

Index fund is the simplest analyzer — pure membership-check plus weight threshold. Per-ticker:

1. `is_index = ticker in INDEX_ETFS` (the frozenset of known broad/sector ETFs).
2. `fund_type` is looked up from `INDEX_FUND_TYPES.get(ticker, 'other')` — values like `'broad_market'`, `'sector'`, `'international'`, etc.
3. Flag = `is_index AND weight_pct > 30`.
4. Severity = `'moderate'` if flagged, else `'none'`.

Portfolio-level: sum all index-ETF weights into `total_index_weight`, track the `dominant_index` (the heaviest single index holding), flag if total index weight > 30 %.

This analyzer's output is what feeds the index_fund suppression in the analysis pool's post-processing — every ticker flagged here gets its concentration flag wiped — and what produces priority-4 informational hold CTAs in the CTA engine.

---

## 6. The CTA Engine — Eleven Priorities

The CTA engine (`cta_engine.py`) reads `pool_results` and emits a list of CTAs. Every CTA is a dict with the shape:

```
{
    'priority': int,       # 1 (highest) to 11
    'action': str,         # 'sell', 'rebalance', 'buy_new', 'buy_more', or 'hold'
    'ticker': str,         # target ticker (may be '' for portfolio-wide holds)
    'dollars': float,      # absolute dollar amount, always non-negative
    'reason': str,         # canonical reason code (steep_decline, high_volatility, …)
    'severity': str,       # one of the 5 levels
    'details': dict,       # action-specific metadata
}
```

Final priority sorting is ascending by `priority` (1 first). The list is then deduplicated and capped before being returned.

### 6.1 Helpers and gates used throughout

- **`_round10(v)`** — rounds dollars to the nearest $10. Every dollar amount the user ever sees is `_round10`-rounded.
- **`_cap_buy_amount(raw, total_equity, group_size)`** — enforces two ceilings on buy CTAs: no single buy can exceed 25 % of current portfolio value, and the combined cap for buys in the same diversification group is 50 % of portfolio split evenly across the group. The effective per-CTA cap is `min(0.25 × total_equity, (0.50 × total_equity) / group_size)`, then `_round10`-applied. *This is what keeps a "you're underweight in Healthcare" suggestion from telling the user to dump 80 % of their portfolio into a single stock.*
- **`_drop_tiny_buys(cta_list, total_equity)`** — removes any `buy_new`/`buy_more` CTA whose dollar amount is below the noise floor `max($200, 1 % of total_equity)` (`_MIN_BUY_DOLLARS = 200.0`, `_MIN_BUY_FRACTION = 0.01`). Sub-1 % "deposit $30 into KO" suggestions are noise, not advice. Sells and holds are untouched.
- **`_cap_total_buys(cta_list, total_equity, risk_tier)`** — after dropping tiny buys, sums every remaining buy CTA's dollars; if the total exceeds the tier's cap (`_MAX_TOTAL_BUY_FRACTION_BY_TIER` = `high 0.35 / regular 0.30 / low 0.20`, falling back to `_MAX_TOTAL_BUY_FRACTION = 0.30` for an unknown tier) it scales **all** buys down proportionally by `cap / total_buy` (then `_round10`), dropping any that round to zero. Conservative is capped tightest because its sells are mostly suppressed, so an uncapped buy total would otherwise *be* the entire (large, positive) net CTA delta — the "deposit tens of thousands into a burning portfolio" case. Sells and holds are untouched.
- **`_sell_too_small(dollars, position_value)`** — True if `position_value < $1000` (`_MIN_POSITION_VALUE_FOR_SELL`) or `|dollars| < $500` (`_MIN_SELL_DOLLARS`). Tiny positions and tiny sell amounts are filtered out — the engine refuses to suggest a $30 trim of a $50 position.
- **`_get_ticker_sector(ticker)`** — walks `SECTOR_SUGGESTIONS` to find which sector a ticker belongs to. Returns `'Unknown'` if not found.
- **`_pick_sector_tickers(sector, held_tickers, n=2)`** — returns up to n suggestion tickers from `SECTOR_SUGGESTIONS[sector]`, preferring tickers not already held.
- **`_underweight_sectors_sorted(sector_weights, held_sectors, exclude_sectors)`** — returns sectors sorted lightest-first, excluding `exclude_sectors`. Unheld sectors come first (those have effective weight 0), then held sectors by ascending weight.
- **`_best_underweight_sector(...)`** — first element of the above (defaults to `'Technology'` if nothing matches).
- **`_split_dollars_by_underweight(sectors, sector_weights, total_dollars)`** — splits a dollar amount across sectors proportional to how underweight each is. The "underweight score" per sector is `max(avg_weight - current_weight, 1.0)` where `avg_weight = 100 / num_sectors`. Sectors are then allocated `(score / total_score) × total_dollars`, `_round10`-rounded, sorted descending by allocation.
- **`_conservative_sell_blocked(ticker, severity, ticker_weight)`** — conservative-tier-only gate described in section 3.3 (including the dominant-position `> 50 %` exception).
- **`_market_cap(ticker)`** — reads market cap from store quote then meta, returns 0.0 if unknown.
- **`_CONCENTRATION_DILUTION_FACTOR`** (module constant, `0.75`) — the fraction of a concentration trigger that the "buy elsewhere to dilute" math (priorities 6 and 7) targets. See those priorities for why the dilution target must sit *below* the trigger.

### 6.2 Priority 1 — Steep decline (SELL)

For each ticker in slope's `ticker_results` whose severity is `'high'` or `'critical'` AND `flag` is True:

1. Run the conservative-sell block.
2. Compute `sev_factor = 1.0` if critical else `0.5` — critical-severity sells get the full `sell_scale` fraction; high-severity gets half.
3. Compute `pos_value = ticker_current_values[t]` (or fall back to `weight × total_equity`).
4. `dollars = _round10(pos_value × sell_scale × sev_factor)`.
5. Apply `_sell_too_small` filter.
6. Emit the CTA with `details.slope_pct = annualized_pct`.

### 6.3 Priority 2 — Excessive volatility (SELL)

For each ticker in volatility's `ticker_results` with `flag = True` (recall: volatility analyzer flags require severity high/critical AND weight > 15 %):

1. Conservative-sell block.
2. Same `sev_factor` rule (1.0 critical, 0.5 high).
3. Same `dollars` formula.
4. Same `_sell_too_small` filter.
5. **Anti-double-flag check**: skip if a steep_decline CTA already exists for this ticker. *A ticker that's both crashing and volatile only gets one sell recommendation, the steep_decline one, because that's the higher-priority signal.*

### 6.4 Priority 3 — Winner drift (REBALANCE or informational HOLD)

For each ticker in concentration's `ticker_results` whose `sub_signals` includes `'winner_drift'` AND `flag = True`:

0. **Skip if a sell already exists for this ticker** (don't regress): if any CTA already in the list targets this ticker with `action == 'sell'` (from priority 1 steep-decline or priority 2 high-volatility), skip the drift signal entirely. A position cannot simultaneously be a runaway winner to rebalance/hold *and* a steep-decline/high-vol position to sell — emitting both is contradictory (the `SELL FCEL` + `HOLD FCEL winner_drift` case). The risk sell takes precedence. This must be gated here at generation time, because `_dedupe_ctas` deliberately permits a sell and a hold to coexist on the same ticker.
1. Get `entry_weight = entry_weight_pct / 100` and `current_weight = ticker_weights[t]`.
2. Compute `position_value` from current values, `raw_rebalance = (current_weight - entry_weight) × total_equity`.
3. Cap rebalance at 35 % of position value: `max_rebalance = position_value × 0.35`.
4. `dollars = _round10(min(raw_rebalance, max_rebalance))`.
5. A `[lens DEBUG]` line prints the drift calculation breakdown.
6. **Branch on tier**: if conservative, emit a `hold` CTA with `dollars = 0.0` and reason `winner_drift_informational` — the user is *told* about the drift but not asked to do anything. Otherwise emit a `rebalance` CTA with the calculated dollar amount.
7. Non-conservative tiers also apply `_sell_too_small`.

Details carry `current_weight`, `entry_weight`, and `drift_multiple` for sentence rendering.

### 6.5 Priority 4 — Index fund informational (HOLD)

For each ticker flagged by the index_fund analyzer: emit a `hold` CTA with `dollars = 0.0`, reason `index_fund_informational`, severity `'moderate'`, details containing `weight_pct` and `fund_type`. The flagged ticker is also added to a local `index_cta_tickers` set used later for buy-suppression.

### 6.6 Priority 5 — High portfolio beta (BUY)

If the portfolio's beta result has `severity in ('high', 'critical')` AND `flag = True`:

1. Identify the heaviest sector from concentration's portfolio result and add it to `avoid_sectors`.
2. Walk underweight sectors in lightest-first order, and within each sector, walk `LOW_BETA_BY_SECTOR[sector]` looking for low-beta tickers that are not already held AND not in `avoid_sectors`. Collect up to 2 suggestions.
3. Fallback path: if zero suggestions found, walk every sector's low-beta list to pick anything not already held.
4. Set `dollars = _cap_buy_amount(0.10 × total_equity, total_equity, 1)`.
5. Emit a `buy_new` CTA with the first suggestion as the primary ticker, `suggested_tickers` carrying the full list of up to 2.

### 6.7 Priority 6 — Single-stock concentration (BUY — up to 3 CTAs)

For each ticker with `sub_signals` including `stock_concentration` AND `flag = True`:

1. Skip if the ticker is in `INDEX_ETFS` or has an existing index_fund CTA.
2. Calculate the dollar amount needed to dilute this position to its target weight: `trigger_pct = concentration.moderate` (default 30), `target_weight = (trigger_pct × _CONCENTRATION_DILUTION_FACTOR) / 100` (i.e. `trigger × 0.75`), `v_stock = ticker_current_values[t]`, `v_total_new = v_stock / target_weight`, `total_dollars = _round10(v_total_new - total_equity)`. *This is the deposit amount that, when invested entirely in other positions, would reduce the over-weight stock's share down to a target safely **below** the trigger.* **The dilution target must sit below the trigger, never equal to it (don't regress):** a holding sitting right at the trigger weight would need ≈$0 to "dilute" back to that same weight — this produced the $70-on-a-$17k-portfolio bug. The `× 0.75` factor (`_CONCENTRATION_DILUTION_FACTOR`) is what guarantees a materially-sized buy while still scaling with the user's chosen threshold; do not set the target back to the raw trigger.
3. Skip if `total_dollars <= 0`.
4. Determine the over-concentrated ticker's sector via `_get_ticker_sector(t)`, with fallback to the position's stored sector or a guess based on whichever sector exceeds 40 %. This sector is added to the `exclude` set.
5. Get up to 3 underweight sectors excluding the over-concentrated one. Fall back to top-3 underweight without exclusion if none match.
6. Split `total_dollars` across the 3 target sectors using `_split_dollars_by_underweight`.
7. For each `(sector, alloc_dollars)`: pick one suggestion ticker from `SECTOR_SUGGESTIONS[sector]` (preferring unheld), verify it's not in the excluded sector, cap with `_cap_buy_amount(alloc_dollars, total_equity, group_size)`, emit a `buy_new` CTA with reason `reduce_concentration`.

### 6.8 Priority 7 — Sector over-concentration (BUY — up to 3 CTAs)

If the portfolio's concentration result is flagged:

1. Identify `heavy_sector` and `heavy_pct`.
2. Calculate `total_dollars`: read `sector_trigger = concentration.sector_moderate` (default 50). If `heavy_pct > sector_trigger`, dilute toward a target **below** the trigger — `target = (sector_trigger × _CONCENTRATION_DILUTION_FACTOR) / 100` (i.e. `trigger × 0.75`), `v_total_new = sector_eq / target`, `total_dollars = _round10(v_total_new - total_equity)`. Otherwise default to `_round10(0.10 × total_equity)` (a 10 % top-up). *This is the same trigger-vs-target collision as single-stock concentration (priority 6): diluting a heavy sector back to its own trigger weight needs ≈$0, so the target is shifted to 0.75× the trigger.*
3. Pull top-3 underweight sectors excluding the heavy one. Same fallback logic as priority 6.
4. Split dollars proportionally. For each allocation: pick a sector-suggestion ticker, *verify it's not in the heavy sector* (and if it is, walk the suggestion list to find a substitute that isn't), cap with `_cap_buy_amount`, emit a `buy_new` with reason `sector_underweight`.

### 6.9 Priority 8 — Dead weight (SELL — suppressed for conservative)

If the tier is not `'low'`, walk slope's `ticker_results`. For each ticker where `weight < 0.02` (less than 2 % of portfolio) AND `annualized_pct <= 2.0` (essentially flat or declining) AND not in `INDEX_ETFS`:

1. `pos_value = ticker_current_values[t]`, `dollars = _round10(pos_value)`.
2. Apply `_sell_too_small` filter.
3. Emit a `sell` CTA with reason `dead_weight`, severity `'low'`. *The recommendation is to liquidate the entire small flat position — the calculated dollars are the full position value, not a fractional trim.*

### 6.10 Priority 9 — Underrepresented sector (BUY — up to 3 CTAs)

If the portfolio has at least 3 known sectors (`sector_count >= 3`):

1. Identify "thin" sectors — those with weight < 10 % and not Unknown — sorted lightest-first.
2. For up to 3 thin sectors: pick a sector-suggestion ticker, compute a top-up deposit `raw_deposit = (0.10 × total_equity - sector_val) / 0.90` (the algebra: solving `(sector_val + d) / (total_equity + d) = 0.10` for d).
3. Cap with `_cap_buy_amount(raw_deposit, total_equity, group_size=min(thin_count, 3))`.
4. Emit `buy_new` with reason `sector_underweight`, severity `'low'`.

### 6.11 Priority 10 — Unrealized loss (HOLD)

For each ticker flagged by performance: emit a `hold` CTA with `dollars = 0.0`, reason `unrealized_loss`, severity carried through from the analyzer. Details carry `unrealized_pct`, `unrealized_dollar`, `entry_price`.

### 6.12 Priority 11 — Portfolio healthy (HOLD)

A catch-all fired only when the CTA list is otherwise empty: emit a single `hold` CTA with `ticker = ''`, `dollars = 0.0`, reason `portfolio_healthy`, severity `'none'`. This guarantees the sentence composers always have at least one CTA to render.

### 6.13 Post-processing: sort, index suppression, dedup, tiny-buy drop, total-buy cap

After all priorities are emitted, the list is sorted ascending by `priority`, then these post-pass steps run in order:

1. **Index-fund buy suppression**: if `index_cta_tickers` is non-empty, drop any `buy_new` or `buy_more` CTA whose ticker is in that set. *We never recommend buying more of an index fund that's already triggered an informational hold.*
2. **`_dedupe_ctas`** runs three sub-steps:
   - **Deduplicate by `(action, ticker)`**: if the same action targets the same ticker at multiple priorities, keep the lowest-priority-number (highest-priority) one.
   - **Sell-group conflict resolution**: a single ticker can't carry both `sell` and `rebalance` CTAs — collapse to the highest-priority of the two using a `(ticker, '_sell_group')` slot key. (Note: a `sell` and a `hold` on the same ticker are deliberately *allowed* to coexist here — the winner-drift-vs-sell contradiction is prevented earlier, at generation time in priority 3, not in dedup.)
   - **Per-sector buy cap**: across the whole CTA list, no target sector receives more than 3 buy CTAs. Beyond 3, surplus buys are dropped.
3. **`_drop_tiny_buys`**: drop any `buy_new`/`buy_more` below the noise floor `max($200, 1 % of total_equity)`. Sub-1 % deposit suggestions are noise.
4. **`_cap_total_buys`**: sum all remaining buy dollars; if the total exceeds the tier-aware cap (`_MAX_TOTAL_BUY_FRACTION_BY_TIER` = `high 0.35 / regular 0.30 / low 0.20` of equity), scale every buy down proportionally by `cap / total_buy` and drop any that round to zero. Several buy priorities (high beta + concentration dilution + sector underweight) can stack, so this keeps the *combined* recommended deposit to a sensible slice of the portfolio.

The resulting list is the canonical CTA output. Steps 3 and 4 touch only buy CTAs; sells and holds pass through unchanged.

---

## 7. The Sentence Composers

Three composers produce the three sentences that make up the user-facing brief. All three share the same template-loading and deterministic-selection logic. The template file is `vector/lens/templates/sentences.json`, loaded and cached once per process by `_templates.load_templates()` (which checks three candidate paths to handle dev, PyInstaller, and Nuitka build environments).

### 7.1 Deterministic template selection

Every composer uses the same `_pick(templates, hash_key)` helper: SHA-256 hash the key, take the result modulo the template list length, return that template. Hash keys are constructed from a stable serialization of portfolio state — typically the sorted ticker list plus salient severity flags or a `s2`/`s3` discriminator — so:

- The same portfolio state always picks the same template (no randomness on repeated runs).
- Different portfolios produce different templates (the hash spreads selections across the available options).
- Adding or removing positions changes the hash and rotates the selection.

This avoids both "the same sentence forever" (boring) and "different sentence on every refresh" (incoherent).

### 7.2 Sentence 1 — portfolio state (slope + volatility + P&L)

`sentence1.compose()` is P&L-aware: it prefers to highlight tickers where slope, volatility, and unrealized P&L align (e.g. a losing position that's also wildly volatile). The selection cascade is:

1. **Position loss with volatility**: collect every ticker with volatility severity high/critical AND unrealized loss < -5 %. Pick the deepest loss. Render `templates.combined.position_loss_with_volatility` with `{ticker, loss_pct, vol, slope}`.
2. **High vol + declining slope**: collect every ticker with vol severity high/critical AND slope < -5 %. Sort by `(align, slope)` where `align = 0` if the ticker is also at unrealized loss (preferred), 1 otherwise. Pick the first. Render `combined.high_vol_declining`.
3. **High vol + rising slope**: collect every ticker with vol severity high/critical AND slope > 5 %. Sort by `(align, -slope)` preferring tickers with unrealized gains. Render `combined.high_vol_rising`.
4. **Portfolio-level slope state**: if no individual ticker triggers the combined templates, fall back to portfolio-state templates keyed by the slope analyzer's `state` field (`'broad_decline'`, `'broad_uptrend'`, or `'mixed'`). The context dict carries `slope`, `vol`, `up_count`, `down_count`, `total`, and joined ticker lists (top 5).
5. **Low-vol stable**: ultimate fallback when nothing else triggers. Renders `combined.low_vol_stable` with `{slope, vol}`.

If template formatting fails (KeyError or ValueError from `str.format`), the raw template is returned unformatted as a graceful degradation. If every step yields nothing, the sentence is the hardcoded `'The portfolio is holding steady with no unusual signals.'`.

### 7.3 Sentence 2 — timing/catalyst (earnings + dividends)

`sentence2.compose()` picks the most imminent earnings or dividend event. Its cascade:

1. **Both within 14 days**: if both earnings and a dividend are within 14 days, render `combined_catalyst.earnings_and_dividend` with `{e_ticker, e_days, d_ticker, d_days}`.
2. **Earnings within 30 days**: read the earnings ticker's `outlook` (`beat_likely`, `miss_risk`, `neutral`), use it as the inner key into `earnings.earnings_imminent`, render with `{e_ticker, e_days, eps}`.
3. **Dividend within 30 days**: render `dividends.dividend_upcoming` with `{d_ticker, d_days, yield_pct}` where `yield_pct` is the per-ticker yield if available, else the portfolio's yield.
4. **Earnings beyond 30 days**: render `earnings.earnings_distant`.
5. **No dividend data**: render `dividends.no_dividends` with `{yield_pct}`.
6. **Fallback**: render `earnings.no_earnings_data`, or the hardcoded `'No imminent catalysts detected across current holdings.'`.

The hash key for sentence 2 includes the sorted ticker list plus the `'|s2'` discriminator so the same portfolio doesn't pick the same hash bucket for both sentences.

### 7.4 Sentence 3 — call to action

`sentence3.compose()` is preference-driven, not strictly priority-driven:

1. First, walk the CTA list looking for any CTA whose reason is in `_DIVERSIFICATION_REASONS = {'reduce_concentration', 'sector_underweight'}`. The first match (which is the highest-priority diversification CTA in the sorted list) becomes the top CTA. *Diversification recommendations are always preferred for the brief because they're the most actionable and approachable for casual investors — telling someone "consider adding $400 to Healthcare via JNJ" beats telling them "your portfolio beta is 1.42".*
2. If no diversification CTA exists, fall back to the highest-priority CTA in the list (which by sorting is `cta_list[0]`).
3. Render via `_render_cta(top, pool_results, hash_key)`, which looks up `templates[action][reason][severity]` (or `[default]` if no severity-specific bucket exists), with a final fallback to `hold.portfolio_healthy.default`.

`_build_ctx(cta, pool_results)` builds the template context dict with every variable a sentence might reference: `ticker`, `dollars`, `weight`, `slope`, `vol`, `sector`, `sector_weight`, `heavy_ticker`, `target_weight`, `entry_weight`, `value` (portfolio beta), `unrealized_pct` (absolute), `unrealized_dollar` (absolute), `count`, `total`.

There's also `compose_full_report(cta_list, pool_results)` which renders every CTA in the list as its own sentence and returns a `list[str]`. This is what feeds the All Projections card on the dedicated Lens page — the user sees the brief's single chosen sentence plus the full per-CTA breakdown.

---

## 8. The Top-Level Assembler

`build_lens_output()` is the choreographer.

### 8.1 Pipeline orchestration

Each pipeline stage is wrapped in its own try/except so any single failure logs at debug level and substitutes a safe default:

1. Run the analysis pool. If it throws, return `_fallback_result()` (a fixed "unable to generate" payload with caution_score 0, empty CTAs, neutral hold action).
2. Compute the CTA list. On failure, use an empty list.
3. Compose sentences 1, 2, 3. On failure, use empty strings.
4. Compose the full report. On failure, use an empty list.

### 8.2 Brief assembly

The three sentences are joined: `brief = ' '.join(non_empty_sentences)`. If all three failed, the brief defaults to `'No signals detected — the portfolio is holding steady.'`.

### 8.3 Top CTA extraction

The first CTA in the sorted list (highest priority) drives several output fields:

- `action_type = top_cta['action']` (or `'hold'` if no CTAs).
- `color = _ACTION_COLORS[action_type]`. The mapping is fixed:
  - `sell` → `#ff4d4d` (red)
  - `rebalance` → `#ff9f43` (orange)
  - `buy_new`, `buy_more` → `#38bdf8` (cyan)
  - `hold` → `#8d98af` (grey)
- `recommended_tickers` — `details.suggested_tickers` if present, else `[top_cta['ticker']]`, else `[]`.
- `deposit_amount = top_cta['dollars']`.
- `underweight_sector = details.target_sector` or `details.heavy_sector` or `''`.

### 8.4 Caution score

`_compute_caution_score(cta_list, total_equity, pool_results)` produces an integer 1–99 that summarises overall risk pressure. It is the **greater** of two independent measures: a **trade-flow score** (how much trading the CTAs imply) and an **exposure-weighted risk floor** (how dangerous the book is regardless of whether any trade was recommended).

```
if total_equity <= 0: return 0

# (a) trade-flow score
weighted_total = 0
for each CTA:
    if action in ('sell', 'rebalance'):
        weighted_total += dollars                # full weight
    elif action in ('buy_new', 'buy_more'):
        weighted_total += dollars × 0.30         # 30% weight
    # hold actions ignored
score_pct = (weighted_total / total_equity) × 100

# (b) exposure-weighted risk floor
floor = _risk_floor(pool_results)

return clamp(round(max(score_pct, floor)), 1, 99)
```

**Trade-flow weighting** is asymmetric and deliberate: a sell signal is a "you should reduce risk" message that carries full weight; a buy signal is a "you have room to grow" opportunity that contributes only 30 %. Hold actions are entirely ignored — so trade-flow alone is a directional risk indicator, not a generic activity meter.

**Why the floor exists.** Trade-flow alone collapses in tiers that suppress sells: a genuinely dangerous Conservative book whose large-cap sells are all blocked would show a near-zero trade-flow score and read as "calm". The `_risk_floor()` term reads analyzer severities directly so a dangerous portfolio still scores high even when its recommended trades are suppressed.

**`_risk_floor(pool_results)`** maps every analyzer severity through the points ladder `_SEVERITY_CAUTION_POINTS = {none: 0, low: 8, moderate: 30, high: 60, critical: 88}`, then returns the `max` of three continuous components so the dominant risk drives the score:

- **`pos_pts`** — exposure-weighted **average** danger across all positions: `Σ (weight × broad)`, where `broad` is the worst severity that ticker carries across `volatility`, `concentration`, `performance`, and `slope`.
- **`single_pts`** — the **worst single position**, damped by its weight: `max over tickers of (single × min(1, weight / 0.45))`, where `single` is the worst severity across `volatility`, `concentration`, and `performance` (note: `slope` is excluded from the single-position term). The `min(1, w/0.45)` damping means a small dangerous satellite no longer pins the score — only a *large* dangerous position drives it.
- **`port_pts`** — portfolio-level risks that warrant caution on their own: the sector-concentration portfolio severity, plus aggregate `volatility`/`beta` severity but **only once elevated to high/critical** (a ~1.0 beta or low aggregate vol is normal market exposure, not caution).

**Why this replaced the old flat max-of-severities (don't regress).** The previous floor was a flat max across all per-ticker severities at full weight — so one 41 %-vol satellite at 20 % weight pinned a "near-perfect" portfolio to 60/99, and the whole score collapsed into ~5 buckets (8/30/60/88). The weight-aware floor restores granularity: a healthy book lands in the single digits, a disaster lands at 88, and only a *large* dangerous position can drive the score up.

If `total_equity <= 0`, the score is 0. The threat level returned in the result dict is simply `caution_score / 100.0`.

### 8.5 Projected positions

`_apply_all_ctas(positions, cta_list, store, settings)` simulates every CTA against a deep copy of positions and returns `(projected_positions, net_cta_delta)`. The simulation rules per CTA:

- **`sell` / `rebalance`**: subtract dollars from the position's `_value`. If `_value` falls to 0 or below, delete the position from the map. Recalculate `shares = _value / price` if price > 0. Add to `net_delta` as negative.
- **`buy_more`**: add dollars to the position's `_value`. Recalculate shares. Add to `net_delta` as positive.
- **`buy_new`**: if the ticker is already held, treat as `buy_more`. Otherwise fetch the ticker's snapshot via `store.get_snapshot()` to get price, sector, name. Create a new position dict with `shares = dollars / price` (or 0 if no price), `_value = dollars`, `equity = dollars`. Add to net_delta.
- **`hold`**: no change.

The final projected list strips the internal `_value` field but copies it into `equity` (so projected equity reflects projected current value). This list is what the Lens page's "With All Lens Projections" graph and "Projected Allocation" pie consume.

### 8.6 The result dict

The full result dict has thirteen keys: `brief`, `color`, `recommended_tickers`, `deposit_amount`, `underweight_sector`, `action_type`, `caution_score`, `full_report`, `ctas`, `threat_level`, `pool_results`, `projected_positions`, `net_cta_delta`. The 7-tuple wrapper in `lens_engine.py` selects the first seven.

### 8.7 Snapshot persistence

If `save_history=True` (the default — debug runs pass False), `_save_snapshot(result)` runs in its own try/except. It:

1. Opens `lens_history.json` from the user data dir, falling back to an empty `{'snapshots': []}` if the file is missing or unparseable.
2. Builds a snapshot dict with `timestamp` (ISO 8601 seconds), `brief`, `caution_score`, `action_type`, `color`, `total_equity`, `cta_count`.
3. **Dedup guard**: if the most recent existing snapshot has identical `brief`, `caution_score`, `action_type`, AND `cta_count`, skip the append entirely. The file grows only when something material changes — no time-only-different entries.
4. Append, truncate to the last 50 entries (rolling window), write back.

The dedup guard is what keeps the history file from accumulating thousands of identical entries when the auto-refresh timer runs every minute on a quiet portfolio.

---

## 9. Failure Modes and Defensive Behavior

The engine is built with the assumption that any external data source — yfinance, the on-disk cache, a settings JSON, a single ticker's history — can fail or return malformed data at any time. The defenses are:

- **Analyzer-level**: every analyzer is wrapped in `_safe_analyze` which returns a neutral result on exception. One broken analyzer never blocks the others.
- **History-level guards**: every analyzer that consumes price history filters None/NaN/non-positive values, requires a minimum of 30 cleaned data points, falls back to "insufficient data" otherwise.
- **NaN/Inf guards**: slope and volatility both check `math.isfinite()` on their final values and substitute 0 if non-finite, then clamp to documented min/max.
- **Sanity correction (slope only)**: three layers of cross-checks against actual price movement override any regression slope that disagrees with reality by more than the documented thresholds.
- **CTA-level**: every CTA stage is independent — if one priority's logic crashes, the others continue. The pipeline-level try/except in `build_lens_output` is the outermost net.
- **Sentence-level**: `str.format` failures fall through to returning the raw template, then ultimately to a hardcoded fallback sentence.
- **Assembler-level**: a total analysis-pool failure returns `_fallback_result()` so the UI never crashes — at worst it shows an "Unable to generate a lens insight right now" message in neutral grey.

All non-trivial failures log via `_log.debug(...)` so they're visible in debug builds without flooding stdout in production.

---

## 10. Determinism and Reproducibility

For a fixed `(positions, store_snapshot, settings)` input, the entire pipeline produces identical output. The sources of nondeterminism the engine deliberately rules out:

- Template selection is SHA-256-keyed — same hash → same template.
- Per-ticker iteration in analyzers uses `for pos in positions:` which preserves user-defined order. Where order matters (e.g. winning the "first upcoming earnings event" race), the analyzer keeps the first hit it sees in input order.
- The CTA list is sorted by priority; ties within a priority are broken by the iteration order (which is again input order).
- Dedup keys are tuples of `(action, ticker)`, not anything time- or hash-based.
- The dollar rounding (`_round10`) and the per-CTA cap (`_cap_buy_amount`) are both pure functions.

This is what makes the engine testable via the debug runner: the same synthetic portfolio at the same risk tier always produces the same CTA list, the same brief, and the same caution score. The only time-dependent input is the market data — and even that is cached per-ticker with TTLs that keep results stable within a refresh window.

---

## 11. Quick Reference — Numerical Constants Summary

For convenience, the table below collects every numerical threshold and constant the engine uses. Most are tier-dependent and shown under "regular"; see section 3.1 for high/low tier values.

| Constant | Value (regular tier where applicable) | Used by |
|---|---|---|
| `_MIN_DATA_POINTS` (slope, vol) | 30 | history-based analyzers |
| `_SLOPE_CLAMP_MIN` / `_MAX` | -80 % / 250 % annualized | slope |
| Slope sanity-correction tolerance | 5 % vs peak/trough, 25 % vs actual | slope |
| Annualization multiplier | 252 (trading days) | slope, volatility, beta |
| `_VOL_CLAMP_MIN` / `_MAX` | 0 % / 150 % annualized | volatility |
| Volatility flag weight gate | > 15 % portfolio weight | volatility |
| Winner-drift weight gate | > 30 % current weight | concentration |
| Winner-drift multiple gate | > 2.0× entry weight (high if > 2.5×) | concentration |
| Sector-concentration severity | > 60 % heavy / sector_count ≤ 1 → high | concentration |
| Earnings days-until ladder | 7 / 14 / 30 days → high/moderate/low | earnings |
| Outlook `beat_likely` | slope > 15 % AND vol ≤ 28 % | earnings |
| Outlook `miss_risk` | slope < -5 % OR vol > 40 % | earnings |
| Dividend trailing window | 365 days | dividends |
| Beta minimum-data-points | 10 | beta |
| Performance loss ladder | -5 / -15 / -25 / -40 → low/mod/high/crit | performance |
| Index-ETF weight flag gate | > 30 % single-ticker, > 30 % portfolio total | index_fund |
| Index-dominated sector downgrade | index weight ≥ 50 % → sector severity floored to `low` | concentration |
| `_MIN_SELL_DOLLARS` | $500 | CTA engine sell gates |
| `_MIN_POSITION_VALUE_FOR_SELL` | $1,000 | CTA engine sell gates |
| `_MIN_BUY_DOLLARS` / `_MIN_BUY_FRACTION` | greater of $200 and 1 % of equity | `_drop_tiny_buys` |
| Per-CTA buy cap | 25 % of total equity | `_cap_buy_amount` |
| Group buy cap | 50 % of total equity / group_size | `_cap_buy_amount` |
| `_MAX_TOTAL_BUY_FRACTION_BY_TIER` | high 0.35 / regular 0.30 / low 0.20 (fallback 0.30) | `_cap_total_buys` |
| `_CONCENTRATION_DILUTION_FACTOR` | 0.75 (dilution target = 0.75 × trigger) | priorities 6 & 7 |
| Dollar rounding | nearest $10 | `_round10` |
| Priority 3 rebalance cap | 35 % of position value | winner drift CTA |
| Priority 5 high-beta deposit | 10 % of total equity | high-beta CTA |
| Priority 6 single-stock dilution target | 0.75 × `concentration.moderate` (default 0.75 × 30) | single-stock concentration |
| Priority 7 default deposit | 10 % of equity (> `sector_moderate` heavy dilutes to 0.75 × trigger) | sector over-concentration |
| Priority 8 dead-weight gates | weight < 2 % AND annualized ≤ 2 % | dead-weight CTA |
| Priority 9 thin-sector cutoff | weight < 10 % AND non-Unknown | underrepresented sector |
| Conservative blocked-sell market cap | > $5B | `_conservative_sell_blocked` |
| Conservative blocked-sell weight floor | < 5 % | `_conservative_sell_blocked` |
| Conservative dominant-position sell exception | weight > 50 % always eligible | `_conservative_sell_blocked` |
| Sell-group dedup | one of {sell, rebalance} per ticker | `_dedupe_ctas` |
| Per-sector buy cap | 3 CTAs / sector | `_dedupe_ctas` |
| Caution score sell weight | 1.0× | `_compute_caution_score` |
| Caution score buy weight | 0.30× | `_compute_caution_score` |
| `_SEVERITY_CAUTION_POINTS` | none 0 / low 8 / moderate 30 / high 60 / critical 88 | `_risk_floor` |
| Risk-floor single-position damping | × min(1, weight / 0.45) | `_risk_floor` |
| Caution score | max(trade-flow score, risk floor), clamped [1, 99] | `_compute_caution_score` |
| Lens history rolling cap | 50 snapshots | `_save_snapshot` |
| Action color: sell | `#ff4d4d` | assembler |
| Action color: rebalance | `#ff9f43` | assembler |
| Action color: buy_new / buy_more | `#38bdf8` | assembler |
| Action color: hold | `#8d98af` | assembler |

---

## 12. Where to Look in the Code

| Concept | File |
|---|---|
| Public entry points | `vector/lens_engine.py` |
| Top-level assembly | `vector/lens/lens_output.py` |
| Analyzer orchestration | `vector/lens/analysis_pool.py` |
| Risk tier resolution | `vector/lens/risk_profile.py` |
| CTA generation | `vector/lens/cta_engine.py` |
| Sentence 1 (state) | `vector/lens/sentence1.py` |
| Sentence 2 (catalysts) | `vector/lens/sentence2.py` |
| Sentence 3 (action) | `vector/lens/sentence3.py` |
| Template loading | `vector/lens/_templates.py` |
| Templates JSON | `vector/lens/templates/sentences.json` |
| Slope analyzer | `vector/lens/analyzers/slope.py` |
| Volatility analyzer | `vector/lens/analyzers/volatility.py` |
| Concentration analyzer | `vector/lens/analyzers/concentration.py` |
| Earnings analyzer | `vector/lens/analyzers/earnings.py` |
| Dividends analyzer | `vector/lens/analyzers/dividends.py` |
| Beta analyzer | `vector/lens/analyzers/beta.py` |
| Performance analyzer | `vector/lens/analyzers/performance.py` |
| Index fund analyzer | `vector/lens/analyzers/index_fund.py` |
| Risk profiles, ETF lists | `vector/constants.py` |
| Debug runner | `vector/lens/debug_runner.py` |
| Lens UI display | `vector/widget_types/lens.py` |
| Full Lens page | `vector/pages/lens_page.py` |
