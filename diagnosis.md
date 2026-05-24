# Lens Engine Diagnosis — 50-Portfolio Debug Run (2026-05-23)

Diagnosis only. No code has been changed. Each issue lists **evidence** (from `output.md` /
terminal), **root cause** (file:line), and a **proposed minimal fix** for the next pass.

The earlier concentration-dilution fix is working — e.g. `18 Single-Stock Heavy` now reads
"reduce NVDA's 59% concentration toward the 26% target" with material `$3,330` buys, not `$70`.
The issues below are separate.

---

## Severity summary

| # | Issue | Severity | Fix size |
|---|---|---|---|
| 1 | Index funds excluded from sector tally → diversified index portfolios flagged as *concentrated* and told to buy single stocks | **High** | Small |
| 2 | `winner_drift` fires on paper-**losing** positions ("price appreciation pushed…" on a -67% stock) | **High** | 1 line |
| 3 | `sector_underweight` sentence prints the **heavy** sector's weight as the **target** sector's exposure ("Financials is underrepresented at 71%") | **High** | 1 line |
| 4 | No global cap on aggregate buys — `high_beta` + 3×`reduce_concentration` + `sector_underweight` stack to 50–140% of portfolio | Medium | Small |
| 5 | Tiers are **non-monotonic**: Conservative is *less* cautious than Moderate (suppresses sells); caution score under-reports real risk | Medium | Design decision |
| 6 | `sell_scale` ordering makes **Moderate** the most aggressive seller (regular 0.50 > high 0.25 > low 0.10) | Medium | Data + decision |
| 7 | Slope clamp at +150% → identical "+150.0%" in many briefs | Low | 1 const / wording |
| 8 | ETF fundamentals 404 spam (VTI/VXUS/SCHD/VYM/TQQQ/SOXL) + wasted API calls | Low | Small guard |
| 9 | Buy-only dilution can't fix extreme concentration when sells are suppressed (Conservative) | Low | Note / design |

Issues 2 and 3 are one-liners. Issue 1 is the most user-visible (it makes "perfect" index
portfolios look broken).

---

## 1. Index funds are excluded from the sector tally → diversified portfolios look concentrated  **[High]**

**Evidence**
- `01 Index Three-Fund` (VTI/VXUS/VOO/SCHD — about as diversified as a portfolio gets):
  brief = *"A $670 deposit into AAPL (Technology) addresses the portfolio's 0% underexposure to
  this sector"* with **3 high-severity `sector_underweight` BUYs** (AAPL/UNH/JPM).
- `08 Lazy Two-Fund` (VOO/VXUS/SCHD): same — buy AAPL/UNH/JPM, "Technology underrepresented at 0%".
- `06 Global Balanced` (VTI/VXUS/VYM/AAPL/JNJ): *"Financials… 53% underexposure"*, buy JPM/PG.

A fully index-diversified portfolio should read "healthy," not "buy individual stocks to fix
diversification."

**Root cause**
- `analyzers/concentration.py:77-79` accumulates `sector_weights` only for **non-index** positions
  (`if not is_index:`). So an all-index portfolio has an empty sector map.
- `analyzers/concentration.py:98-112`: `sector_count` counts only non-index sectors, then
  `if heaviest_pct > 60 or sector_count <= 1: 'high'` / `elif … sector_count <= 2: 'moderate'`.
  All-index → `sector_count == 0` → **`high` sector-concentration flag**. Index-heavy with ≤2 other
  sectors (e.g. `06`) → `moderate`.
- `cta_engine.py` priority 7 (`port_conc.get('flag')`) then fires and emits `sector_underweight`
  BUYs into the "missing" real sectors.
- `analyzers/index_fund.py:62-74` already computes `total_index_weight` at the portfolio level, but
  **`cta_engine.py` never consults it** to suppress the sector-diversification CTAs.

The irony: the more thoroughly index-diversified the portfolio, the *more* concentrated the engine
thinks it is, because the index weight vanishes from the sector tally.

**Proposed minimal fix** (pick one)
- In `cta_engine.py`, read `idx_res['portfolio_result']['details']['total_index_weight']`; if it's
  high (≈ ≥ 50%), skip priority 7 and priority 9 `sector_underweight` CTAs (the index already
  supplies broad sector exposure), and don't let priority 7 fire purely off `sector_count <= 1/2`.
- *Or* in `concentration.py`, when `total_index_weight` is high, don't set the sector flag from the
  `sector_count <= 1/2` rule (only flag on a genuine non-index heavy sector).

Either is a few lines. The CTA-engine guard is the most contained.

---

## 2. `winner_drift` fires on paper-LOSING positions  **[High, 1-line fix]**

**Evidence**
- `28 Dividend Trap`: *"INTC is rising at +150.0% annualized … INTC dominates at 45% …
  **HOLD INTC — winner_drift_informational**"* — INTC was entered at $45 and is a loser here.
- `42 Speculative Inferno` (Conservative): the **same ticker FCEL** gets
  `SELL FCEL high_volatility` **and** `HOLD FCEL winner_drift_informational` — contradictory.
- `44 Beaten-Down Penny Disaster`: `HOLD FUBO winner_drift_informational` on a position down ~65%.
- `36 Deep Losers Club`: `HOLD INTC winner_drift_informational` in an all-losers book.
- Terminal: `[lens DEBUG] winner_drift FCEL: current_weight=0.422, entry_weight=0.188 …`,
  `winner_drift FUBO: current_weight=0.344, entry_weight=0.135 …`.

The `winner_drift` template literally says *"Price appreciation has pushed {ticker} from X% to Y%"*,
so it **assumes** the position went up — but the detector never checks that.

**Root cause**
- `analyzers/concentration.py:57` `drift_multiple = weight / entry_weight`, where `weight` is the
  position's share of **current** value and `entry_weight` its share of **cost basis**.
- `analyzers/concentration.py:70`:
  `if not is_index and weight_pct > 30 and drift_multiple > 2.0:` → flags winner drift.

In an all-loser basket, the position that fell *least* has the highest `current/cost` ratio, so its
current weight exceeds its cost-basis weight → `drift_multiple > 2` → flagged a "winner" even though
it's underwater. The signal conflates "this went up" with "the others went down more."

**Proposed minimal fix**
Add an actual-appreciation gate to the condition (the position must really be up from entry):

```python
if (not is_index and weight_pct > 30 and drift_multiple > 2.0
        and current_value > cost_equity):
```

`current_value` and `cost_equity` are already computed a few lines above. One line, no signature
changes. This also resolves the contradictory SELL+HOLD-drift pairs.

---

## 3. `sector_underweight` sentence reports the wrong sector's weight  **[High, 1-line fix]**

**Evidence**
- `13 Healthcare Lean`: *"**Financials** exposure is thin at **59%**"* — Financials isn't at 59%;
  59% is the **Healthcare** (heavy) weight. 59% is also not "thin."
- `17 Tech Overweight`: *"**Financials** is underrepresented at **71%**"* — 71% is Technology's weight.
- `39 Energy All-In`: *"address the **92%** underweight"* about Technology — 92% is Energy's weight.
- (`08`'s "Technology underrepresented at 0%" reads OK only by accident, because the heavy weight is 0.)

**Root cause**
- `cta_engine.py` priority 7 builds the CTA with `details['sector_weight'] = heavy_pct`
  (the **heavy/source** sector's weight) while `details['target_sector']` is the underweight sector.
- `sentence3.py:_build_ctx` maps `'sector': details['target_sector']` but
  `'sector_weight': details.get('sector_weight', 0)` → so the template
  (`templates/sentences.json:188-194`) renders the heavy sector's % as the target sector's exposure.
- Priority 9 sets `sector_weight = sw_pct` (the thin sector's real weight), so priority-9 wording is
  correct — only priority-7 CTAs are wrong.

**Proposed minimal fix**
In `cta_engine.py` priority 7, pass the **target** sector's current weight instead of the heavy one:

```python
'sector_weight': round(sector_weights.get(sector, 0.0) * 100, 1),
```

(`sector_weights` here is the `_positions_summary` map of fractions.) One line per the priority-7
`ctas.append`. Now "Financials is underrepresented at X%" prints Financials' actual (small) weight.

---

## 4. No global cap on aggregate buy recommendations  **[Medium]**

**Evidence**
- `48 Everything Wrong` (Conservative): **Net CTA delta $28,440** = `high_beta $4,180` +
  `reduce_concentration $6,960 ×3` + `sector_underweight GE $3,380`.
- `49 Leverage Lover`: Net delta **$42,590** of buys.
- `20 Moderate Winner Drift`: Net delta **$15,120** (~73% of the book) in new buys.

Each priority is individually capped by `_cap_buy_amount` (25% per CTA, 50% per diversification
group), but **nothing caps the sum across priorities**. `high_beta` (10% of equity) + three
`reduce_concentration` buys (up to ~16.7% each = 50%) + `sector_underweight` stack to 60%+ — i.e. the
brief asks the user to deposit well over half (sometimes more than all) of their portfolio at once.

**Root cause**
- `cta_engine.py`: priorities 5/6/7/9 each append buys with only per-CTA/per-group caps; there is no
  pass that bounds total buy dollars.

**Proposed minimal fix**
After `compute_ctas` builds the list (or in `_dedupe_ctas`), scale down all buy CTAs proportionally
so their **sum ≤ a fraction of `total_equity`** (e.g. 30–40%). Small, localized post-pass; sells and
holds untouched.

---

## 5. Tiers are non-monotonic; caution score under-reports real risk  **[Medium — design]**

**Evidence**
- `05 Eight-Sector Spread`: Conservative = *portfolio healthy*; Moderate = **3 steep-decline SELLs**
  (MSFT/ABBV/MA); Aggressive = *portfolio healthy*. The middle tier is scarier than both ends.
- `49 Leverage Lover` (78% in a leveraged ETF, SOXL): Conservative **caution 13/99**, Moderate 55.
- `41 PLUG 100% loser`: Conservative caution 17 vs Moderate 67.

A Conservative investor should be the *most* protective, yet sees the *fewest* warnings and the
*lowest* caution on genuinely dangerous books.

**Root cause**
- `cta_engine.py:131-151 _conservative_sell_blocked` blocks a sell if market cap > $5B (assumes
  large-cap = safe), if severity isn't `critical`, or if weight < 5%. For `05`, MSFT/ABBV/MA are
  large-cap → all sells suppressed → "healthy." Moderate has no such block and a looser slope
  threshold than Aggressive, so it alone fires.
- `lens_output.py:201-214 _compute_caution_score`: caution = (Σ sell$ + 0.30·Σ buy$) / total_equity.
  It's a function of **recommended trade dollars only**, not portfolio risk. When Conservative
  suppresses sells, the dollars (and thus caution) collapse — so the safest-styled investor is shown
  the calmest score on the riskiest portfolio.

**Proposed fix (needs a product decision, not a pure one-liner)**
- Make Conservative at least as cautious as Moderate: relax the blanket large-cap sell block (e.g.
  still flag/inform even if it trims a smaller fraction), or
- Decouple caution from CTA dollars — derive it (at least partly) from analyzer **severities**
  (concentration/volatility/beta/loss), so a 78%-leveraged-ETF book scores high regardless of whether
  sells are suppressed. This is the more correct fix and is moderate-sized.

---

## 6. `sell_scale` ordering makes Moderate the most aggressive seller  **[Medium]**

**Evidence**
- `34 Single Stock 60%` TSLA: Moderate `SELL TSLA -$4,260`, Aggressive `-$2,130`, Conservative `$0`.
- `constants.py:195/203/211`: `high` (Aggressive) `sell_scale = 0.25`, `regular` (Moderate) `0.50`,
  `low` (Conservative) `0.10`.

So Moderate trims the largest amounts and Conservative the smallest. If the intent is "aggressive
investors hold through volatility; conservative investors trim risk," this is backwards — Conservative
should have the *highest* sell_scale, not the lowest. (Also: `CLAUDE.md` documents 0.3/0.5/0.15;
the code is 0.25/0.50/0.10 — minor doc drift to fix while here.)

**Proposed fix**
Re-decide the three `sell_scale` values to be monotonic with intent (a data change in
`constants.py`), then reconcile `CLAUDE.md`. Confirm desired semantics first.

---

## 7. Slope clamp at +150% → repeated "+150.0%" in briefs  **[Low]**

**Evidence**: `15`, `22` (AMD), `28` (INTC), `49` (SOXL) all read exactly *"+150.0% annualized"*.

**Root cause**: `analyzers/slope.py:15 _SLOPE_CLAMP_MAX = 150.0`; genuine momentum names exceed it and
pin to the cap, so the same number recurs.

**Proposed fix**: raise the clamp, or when a value is clamped have the sentence say
"more than +150%"/"triple-digit" rather than a precise "+150.0%". Cosmetic/credibility only.

---

## 8. ETF fundamentals 404 spam + wasted API calls  **[Low]**

**Evidence (terminal)**: `HTTP Error 404 … No fundamentals data found for symbol: VTI / VXUS / SCHD /
VYM / TQQQ / SOXL`.

**Root cause**: `analyzers/earnings.py:84` calls `store.get_earnings(t)` for **every** position,
including index ETFs, which have no earnings/fundamentals → 404 (caught, but logged and counted as an
API call). Same pattern likely for dividend/meta fetches on ETFs.

**Proposed fix**: skip the earnings (and any fundamentals-only) fetch when `t in INDEX_ETFS`. Removes
the log noise and trims API calls on every index-holding portfolio.

---

## 9. Buy-only dilution can't fix extreme concentration when sells are suppressed  **[Low / design]**

**Evidence**: `41 PLUG 100%` (Conservative): no PLUG sell (suppressed); buys $940×3 + $570 — modest
deposits that cannot actually move a 100% position toward target. The advice is structurally unable to
fix the problem in that tier.

**Root cause**: Conservative suppresses sells (Issue 5) and priority 6/7 dilute by *buying only*; for a
near-100% single position, buying alone needs multiples of the portfolio (then gets capped), so the
projected allocation never reaches target.

**Proposed fix**: tied to Issue 5 — when a single position is extreme (e.g. >60–70%), allow a trim CTA
even in Conservative (informational or scaled), so the advice is achievable. Defer until Issue 5's
direction is decided.

---

## Working as intended / not bugs (for context)

- **Concentration dilution** (the earlier fix) is correct: `18`, `22`, `45` produce materially-sized,
  below-trigger dilution targets.
- **Genuine sector concentration** detected correctly: `29 All Tech`, `25 Energy Heavy`, `39 Energy All-In`.
- **Unrealized-loss holds** fire correctly on real paper losers (`10 PFE`, `36`, `31`, `44`).
- **High-vol / high-beta sells** fire on speculative names (`33 Crypto Miners`, `22`, `42`).
- **Some portfolios landed in a different grade band than the file's label** (e.g. `12 Modest Winner`
  intended NVDA ~28% but live price put it at 44%, tripping drift+concentration). That's the expected
  consequence of live prices driving weights — not an engine bug.

---

## Suggested fix order for the next pass

1. **#2 winner_drift gate** (1 line) — removes contradictory/incorrect signals.
2. **#3 sector_weight variable** (1 line) — fixes nonsensical "underrepresented at 71%".
3. **#1 index-fund sector suppression** (small) — stops "perfect" index portfolios from being told to buy stocks.
4. **#4 global buy cap** (small) — keeps deposit asks realistic.
5. **#8 skip ETF earnings fetch** (small) — removes 404 noise.
6. **#5 / #6 / #9 tier + caution + sell_scale semantics** — group these; they need a product decision
   on what Conservative/Moderate/Aggressive should *mean*, then a coordinated tweak.
7. **#7 slope clamp wording** (cosmetic) — last.
