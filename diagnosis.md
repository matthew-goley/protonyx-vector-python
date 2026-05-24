# Lens Engine Diagnosis — 50-Portfolio Debug Run (2026-05-24)

This run was generated **after** the 2026-05-23 fixes. Those are confirmed working:
`winner_drift` no longer fires on paper losers, `sector_underweight` reports the target
sector's weight, index-dominated books are no longer told to "buy stocks to diversify",
and the aggregate buy cap + severity-floor caution are in place.

The issues below are the ones still visible in this run. **All six were fixed in this pass**
— each entry lists the evidence, root cause (`file` / function), and the change made.

---

## Severity summary

| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | Caution score collapses to ~5 buckets (`8/30/60/88`) and over-reports healthy books — "near-perfect" portfolios read **60/99** | **High** | **Fixed** |
| 2 | Default `lens_signals` overrides clobber the per-tier thresholds → tiers barely differ and even **invert** (Conservative *more* aggressive than Aggressive) | **High** | **Fixed** (root cause of #1) |
| 3 | Conservative "deposit into a fire": sells suppressed but dilution buys uncapped → **+$39k** deposit ask on a 78%-leveraged-ETF book | **High** | **Fixed** |
| 4 | `winner_drift` HOLD emitted on a ticker that is **also** being SOLD (contradiction: `SELL FCEL` + `HOLD FCEL winner_drift`) | Medium | **Fixed** |
| 5 | Sub-$200 buy CTAs (`+$10` KO, `+$30`, `+$110`) — noise, not advice | Low | **Fixed** |
| 6 | Pluralization: "3 positions are rising and **1 are** falling", "**1 positions** trending up" | Low | **Fixed** |

Issue 2 is the keystone — it is the root cause of the caution-score inflation in #1 and the
tier inversions. Fixing it first made the rest fall into place.

---

## 1. Caution score is quantized and over-reports healthy portfolios  **[High — Fixed]**

**Evidence**
- Across all 50 portfolios the caution score only ever took **5 values**: `8, 9, 30, 60, 88`.
- `03 Core + Satellite` and `07 Balanced Growth & Value` — both labelled *NEAR-PERFECT* —
  read **60/99** in every tier. A healthy core-and-satellite book is not "60% cautious".
- A genuine `DISASTER` (`49 Leverage Lover`, 78% in a leveraged ETF) and a *MODERATE*
  `12 Modest Winner` both topped out at the same `88`, so the score couldn't separate danger
  levels.

**Root cause** — `lens_output.py :: _severity_caution_floor`
- The floor was `max` of analyzer severities mapped through a coarse table
  `{none:0, low:8, moderate:30, high:60, critical:88}`, and it counted the **worst single
  ticker** at full weight. So one 41%-vol satellite at ~20% weight (`UNH` in #03, `LLY`/`CAT`
  in #07) pinned the whole book to `high → 60`. The trade-flow score rarely exceeded the
  floor, so caution was effectively a 4-value category.

**Fix applied** — replaced `_severity_caution_floor` with **`_risk_floor`**, an
exposure-weighted, continuous floor (`max` of three components):
- `pos_pts` — weight-averaged per-position danger (a small volatile satellite contributes
  little; a 78% position contributes almost everything).
- `single_pts` — worst single position **damped by its weight** (`× min(1, w/0.45)`), so a
  genuinely dangerous concentrated holding still scores critical while a minor satellite
  cannot.
- `port_pts` — sector over-concentration, plus aggregate volatility / beta **only once
  elevated** (a ~1.0 beta or low aggregate vol is normal market exposure, not caution — this
  also stopped all-index books reading `30` in the Conservative tier).

Result: caution now spans ~25 distinct values (`6 … 88`). `03 → 14/14/7`, `07 → 24/11/8`,
`01 Index → 8/8/8`, while `49 → 88` and `12 → 86/59/29`.

---

## 2. Default `lens_signals` overrides flatten (and invert) the risk tiers  **[High — Fixed]**

**Evidence**
- Tiers were nearly identical on many portfolios, and on concentration they **inverted**:
  `11 Mild Single-Stock Tilt` (AAPL ~34%) read Conservative **60 + $4,890 of buys** but
  Moderate/Aggressive **"portfolio healthy", $0** — the *most* protective tier produced the
  *largest* ask.
- Normal-vol quality names (`UNH` 41%, `LLY` 38%, `CAT`, `AVGO` 42%) classified as **high
  volatility** in *every* tier, generating sells and inflating caution.

**Root cause** — `risk_profile.py :: load_risk_profile`
- The shipped `DEFAULT_SETTINGS['lens_signals']` (vol high=35, concentration moderate=35,
  steep_downtrend=-20, beta high=1.3, loss=-15) were applied **unconditionally** on top of
  every tier, overwriting the carefully-tiered `DEFAULT_RISK_PROFILES` with a single
  cross-tier value. Because every test (and every real user seeded from defaults) carries
  those values, the risk-tier selection was largely inert — and the override even produced
  **invalid orderings** (Conservative concentration `moderate`=35 **>** `high`=30, so a 34%
  position skipped straight to `high`).

**Fix applied** — overrides are now applied **only when the user has changed a value away
from the shipped default** (`_changed()` helper compares against
`DEFAULT_SETTINGS['lens_signals']`). Untouched settings defer to the tier, so
Conservative/Moderate/Aggressive are once again meaningfully different and monotonic. `11`
now reads `46 / 23 / 8` (correct ordering); `UNH`/`LLY`/`CAT` drop to `moderate` vol.

> This honours the documented contract ("user overrides take precedence") while restoring the
> tier system: a value left at the default is treated as "not overridden".

---

## 3. Conservative "deposit into a fire" — uncapped net-positive CTA delta  **[High — Fixed]**

**Evidence**
- `49 Leverage Lover` (Conservative): **Net CTA delta +$39,290** — the engine suppressed the
  SOXL sell (78% of the book) and instead told the user to *deposit* $15k+$15k+$9k to dilute
  it. Unactionable: you cannot dilute a 78% position by depositing 20% more.
- `48 Everything Wrong` (Conservative): **+$16,700**. `41 PLUG 100%`: buys-only, no trim.

**Root cause** — `cta_engine.py`
- `_conservative_sell_blocked` blocked the trim of *any* large-cap / unknown-cap position
  regardless of how much of the book it was, and `_cap_total_buys` used a single 0.40 cap for
  all tiers — so with sells suppressed, the (huge) dilution buys became the entire net delta.

**Fix applied**
- `_conservative_sell_blocked` now has an exception: a position **> 50% of the book** is
  always eligible to be trimmed (even a conservative investor should reduce a holding that is
  more than half the portfolio).
- `_cap_total_buys` is now **tier-aware** (`_MAX_TOTAL_BUY_FRACTION_BY_TIER` =
  `high 0.35 / regular 0.30 / low 0.20`), so Conservative is asked to deposit the least.

`49` Conservative now **SELLS SOXL −$7,620** and the net delta drops to **+$12,040**;
`41` Conservative now trims PLUG and diversifies out (net +$550).

> *Deferred / design decision (not changed):* even with the trim, "buy to dilute" still
> produces sizeable deposits for an extreme single-stock book, and a concentrated position
> that is neither volatile nor declining (e.g. `45` BA at 79% but rising) still never gets a
> trim CTA. A "trim extreme concentration > ~60% regardless of volatility" signal would close
> this, but it changes the documented buy-to-dilute philosophy — flagged for a product call.

---

## 4. `winner_drift` HOLD on a ticker that is also being SOLD  **[Medium — Fixed]**

**Evidence**
- `42 Speculative Inferno` (Conservative): the same ticker **FCEL** carried both
  `SELL FCEL high_volatility (critical)` **and** `HOLD FCEL winner_drift_informational
  (critical)` — a "runaway winner, hold" and a "too volatile, sell" on one position.

**Root cause** — `cta_engine.py` priority-3 loop appended a winner-drift CTA without checking
whether the ticker had already been flagged for a steep-decline / high-volatility sell in
priorities 1–2.

**Fix applied** — priority 3 now `continue`s if the ticker already has a `sell` CTA. The risk
sell takes precedence. (`_dedupe_ctas` allows a sell and a hold on the same ticker, so this
had to be gated at generation time.) Verified: zero sell+winner_drift pairs across all 50.

---

## 5. Sub-$200 buy CTAs are noise  **[Low — Fixed]**

**Evidence** — `26` `BUY UNH +$10`, `12` `BUY KO +$30`, `18`/`19` `BUY … +$110`.

**Root cause** — priority 7/9 `sector_underweight` dilution math yields tiny dollar amounts
when a sector is only marginally thin, with no floor.

**Fix applied** — `_drop_tiny_buys` removes any buy below `max($200, 1% of equity)` before the
total-buy cap. Verified: no buy CTA under $200 remains.

---

## 6. Pluralization with a count of 1  **[Low — Fixed]**

**Evidence** — `26` "3 positions are rising and **1 are** falling"; `27` "**1 positions**
trending up versus 3 declining".

**Root cause** — the `portfolio_mixed` templates in `sentences.json` hard-coded a plural noun
(`positions`/`holdings`/`tickers`) and verb (`are`) after a count placeholder.

**Fix applied** — reworded the four affected templates to count-agnostic gerunds
("`{up_count}` advancing versus `{down_count}` declining", etc.) that read correctly for any
count. Now: "1 advancing versus 3 declining".

---

## Working as intended / not changed (for context)

- **Tier behaviour is now monotonic** for concentration risk (Conservative ≥ Moderate ≥
  Aggressive caution; e.g. `11 → 46/23/8`, `12 → 86/59/29`, `18 → 88/88/60`).
- **`sell_scale` ordering** (`regular 0.50 > high 0.25 > low 0.10`) is unchanged — Moderate
  still recommends the largest sell dollars. This is a deliberate-looking but debatable
  semantic; left for a product decision rather than guessed at.
- **`high_beta` buy** still appears on already-broken books (a low-beta name suggested to damp
  portfolio beta). Dollars are bounded by the tier buy-cap; left as-is.
- **Disasters correctly read 88** and healthy/index books read single digits.
