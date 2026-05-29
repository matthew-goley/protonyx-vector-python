# Vector Lens — Diagnosis from `output.md` (50-portfolio debug run)

_Source: `output.md` generated 2026-05-28 from `debug_test.json` (50 portfolios × 3 tiers)._
_This document is analysis only — no engine logic was changed. Each item lists the **symptom** (with evidence), the **root cause** (file:line), and a **recommended change**._

> **Read this first — the dominant finding.** A large share of the bad output traces to **one upstream problem: positions whose `sector` came back missing / `"Unknown"`.** Near-perfect, fully diversified books (#01–#08) are repeatedly told that sectors they *clearly hold* (Healthcare via JNJ, Financial Services via JPM, Consumer Defensive via PG) are "thin at 0%". That can only happen if those holdings were never counted under their real sector. Index-only books (#01, #08) behave correctly because index detection keys off the static `INDEX_ETFS` list, not live metadata — so the breakage is specifically in the **live sector-metadata path**. Fixing sector resolution will, by itself, correct a majority of the wrong CTAs and a big chunk of the inflated caution scores below. It is plausible the bulk live run hit yfinance rate limits and returned empty sectors; even so, the engine must degrade gracefully when sector is absent.

---

## CRITICAL

### C1. Missing/`Unknown` sector data has no fallback, and it cascades into wrong advice
**Symptom.** Well-diversified books are told to buy sectors they already own:
- **#02 Diversified Blue Chips** (one leader per sector, holds JNJ/JPM/PG/AMZN/XOM/CAT/NEE/GOOGL/LIN/AAPL): brief says *"Healthcare exposure is thin at 0%"* → BUY UNH/V/KO. It holds JNJ (Healthcare), JPM (Financial Services), PG (Consumer Defensive).
- **#04 Dividend Diversified** (holds JNJ, JPM): *"$990 into AAPL (Technology)… 0% underexposure"* + BUY UNH + V.
- **#05 Eight-Sector Spread** (holds ABBV=Healthcare, MA=Financials): *"Healthcare underrepresented at 0%"* → BUY UNH + JPM.
- **#16, #11, #17, #39** — same pattern (BUY UNH/V while JNJ/JPM held).

**Root cause.** Sectors are tallied from each position's `sector` string:
- `vector/lens/analysis_pool.py:169-172` (`_build_positions_summary`) — `sector = p.get('sector') or 'Unknown'`.
- `vector/lens/analyzers/concentration.py:82-84` — same.
- The debug build path takes the sector straight from the live snapshot with no static fallback: `vector/lens/debug_runner.py:70` (`snapshot.get('sector', 'Unknown')`).

When the live sector is empty, the holding lands in an `"Unknown"` bucket, so:
1. It is **not** counted under its true sector → the CTA engine's `_underweight_sectors_sorted` (`vector/lens/cta_engine.py:98-119`) treats that true sector as "unheld" → recommends buying it (UNH/V/AAPL).
2. `known_sectors`/`sector_count` collapse (`concentration.py:105-119`) → a false **high-severity** sector-concentration flag → spurious priority-7 `sector_underweight` BUYs **and** a pinned caution score (see C2).

**Recommended change.**
- Add a **static ticker→sector fallback map** and use it whenever the live sector is missing/`Unknown`. The data already exists implicitly in `SECTOR_SUGGESTIONS` / `LOW_BETA_BY_SECTOR` / `COMMON_TICKERS` (`vector/constants.py:130-187`); promote it to an explicit `TICKER_SECTOR` dict and consult it in `_build_positions_summary`, `concentration.py`, and `_build_mock_position`.
- In `concentration.py`, **don't let an `Unknown` bucket masquerade as a single real sector** — exclude `Unknown` weight from the `sector_count<=1 ⇒ high` collapse (lines 105-119) so missing data can't fabricate a concentration flag.
- **Verify the run wasn't rate-limited**: re-run the debug suite with a warmed `market_data.json` cache and confirm sectors populate. If they still don't, the snapshot/meta path (`store.get_snapshot`/`get_meta`) needs a retry/fallback.

### C2. Caution score collapses into ~3 buckets (10, 62, 95–97); the whole mid-band is dead
**Symptom.** Wildly different portfolios share identical scores:
- **62/99** for *near-perfect* #02/#04/#05/#07 **and** moderate #11/#13/#14/#16/#17/#24/#25.
- **95–97/99** for nearly every "messed up"/"disaster" (#20, #26, #31–#37, #41–#50).
- A "good, minor flaw" book (#12) swings **92 (conservative) / 61 / 35 (aggressive)** — non-monotonic and extreme.

**Root cause.** The risk floor maps severities through only five discrete points and takes their `max`:
- `vector/lens/lens_output.py:201` — `_SEVERITY_CAUTION_POINTS = {none:0, low:10, moderate:35, high:62, critical:90}`.
- `_risk_floor` (`lens_output.py:204-267`) → any single `high` severity pins the floor to **62**; any `critical` pins to **90**, then the breadth lift pushes disasters to **95–97**. Nothing populates 11–34, 36–61, 63–89.
- The pervasive **62** is largely a *downstream artifact of C1* (the false high-severity sector flag).

**Recommended change.**
- Fix C1 first — that alone removes most spurious 62s.
- Make the floor **continuous within a severity band** (e.g. interpolate by how far a metric is past its threshold) so scores spread across 1–99 instead of snapping to 62/90.
- Re-examine the conservative tier specifically: tighter thresholds push severities up (higher caution) while sells are suppressed (fewer actions) — the worst of both. See C3/H4.

### C3. The brief contradicts the danger (and the caution score)
**Symptom.**
- **#38 Two-Position** (AAPL+NVDA, ~50/50, 100% tech), conservative: caution **97/99** but brief says *"No actionable signals detected — the portfolio's risk metrics, diversification, and momentum are all within normal bounds."* and **zero CTAs**.
- **#28 Dividend Trap** (PFE/VZ/INTC/T, all beaten down): *"5 of 5 positions are trending upward — +150.0% annualized."*
- **#35 Extreme Winner Drift** (AAPL 79%): leads *"Strength across holdings — 3 of 4 appreciating."*
- **#19, #36, #39** — momentum-positive lead on books dominated by losers / single-sector bets.

**Root cause.**
- Sentence 1 chooses a loss/decline lead **only when volatility is high** (`vector/lens/sentence1.py:53-97`); otherwise it falls through to a pure slope-direction sentence (`sentence1.py:106-133`) that ignores unrealized losses and concentration entirely. Low-vol-but-underwater books (Dividend Trap) and calm-but-concentrated books (winner drift) therefore lead with "strength".
- The `portfolio_healthy` fallback line is emitted whenever the top CTA is `portfolio_healthy` (`vector/lens/sentence3.py:60,89` → `templates/sentences.json:239`), with no check against the caution floor.

**Recommended change.**
- Sentence 1 should factor **breadth of unrealized loss** and **dominant single-stock/sector weight** even when volatility is low, and must **not** lead with "strength/momentum" when the risk floor is elevated.
- Reconcile sentence 3: never say *"all within normal bounds"* when the caution floor is high or when actions were merely **suppressed by tier** (vs genuinely absent). Distinguish "healthy" from "risky but no action recommended for your tier".

---

## HIGH

### H1. The clamped slope (`+150.0%` / `-80.0%`) is surfaced verbatim in the brief
**Symptom.** `+150.0%` appears as a literal portfolio slope in #19, #28, #36, #49 (and high figures like +109.2% #15, +128.0% #22). It reads as a bug/non-credible.
**Root cause.** `vector/lens/analyzers/slope.py:14,21` clamp to `[-80, 150]`; the clamped `port_annual` flows into sentence 1's `slope` field (`sentence1.py:43,111-119`). The code comment at `slope.py:18-20` claims the ceiling "is rarely surfaced" — that is **out of date**: the portfolio-state sentence surfaces it on every mixed/uptrend book.
**Recommended change.** Either (a) format the figure qualitatively above a believable bound (e.g. ">50% → 'strongly positive'") instead of printing the clamp, or (b) compute the portfolio slope from a regression on **total portfolio value** rather than `Σ per-ticker rawslope×252×weight`, which over-amplifies and saturates the clamp.

### H2. `SELL X` and `HOLD X` emitted for the same ticker (reads contradictory)
**Symptom.** #41 (100% PLUG): *SELL PLUG -$620* **and** *HOLD PLUG (unrealized_loss)*. Same double-listing in #31, #32, #33, #42, #44, #50.
**Root cause.** Priority 2 (`high_volatility` sell) and priority 10 (`unrealized_loss` hold) both fire for one ticker, and `_dedupe_ctas` **intentionally** permits a sell + a hold on the same ticker (`vector/lens/cta_engine.py:738-749`).
**Recommended change.** When a ticker already carries a `sell`/`rebalance`, suppress (or merge into) its informational `unrealized_loss` HOLD so the projections list never tells the user to both sell and hold the same position — particularly for single-holding books.

### H3. Tiny sub-floor BUY CTAs leak through after total-buy scaling
**Symptom.** Buys far below the stated $200 floor: #30 *BUY IBM +$80*, #36 *BUY JNJ +$140*, #40 *BUY JNJ +$100*, #47 *BUY JNJ +$120*.
**Root cause.** Order of operations in `compute_ctas` (`vector/lens/cta_engine.py:652-656`): `_drop_tiny_buys` runs **before** `_cap_total_buys`. The danger-aware `_cap_total_buys` then scales every buy **down** (`cta_engine.py:687-689`), producing new sub-$200/sub-1% amounts that are never re-filtered.
**Recommended change.** Re-apply the tiny-buy floor (`_drop_tiny_buys`) **after** `_cap_total_buys`, or drop any buy that falls below the floor post-scaling.

### H4. Calm-but-concentrated books are told to *deposit*, never to trim (non-conservative tiers)
**Symptom.**
- **#45 70% Concentrated Loser** (BA ~80%, underwater): every tier only BUYs (AAPL/UNH/V); **net CTA delta is positive** (+$660/+$990/+$1,170) — i.e. "deposit more into a falling 80% position".
- **#34 Single Stock 60%** (TSLA ~76%): moderate/aggressive recommend **only** buy-to-dilute, **no TSLA trim**. (Conservative does trim TSLA via the >50% exception.)
**Root cause.** Single-stock concentration (priority 6, `cta_engine.py:394-470`) is **BUY-only**. There is no "trim the concentrated name" sell path for non-conservative tiers unless volatility/slope independently flags it. The danger throttle `_critical_weight` (`cta_engine.py:697-721`) only counts **critical**-severity positions, so a concentration that is `high`/`moderate` (not `critical`) escapes the throttle and the buy budget stays large.
**Recommended change.** For very high single-stock weight (e.g. >50–60%), generate a **trim/rebalance SELL** (mirroring winner-drift) regardless of tier, instead of recommending fresh deposits to dilute. Consider including concentration `high` in the danger-weight throttle.

### H5. Dead-weight CTA still effectively never fires
**Symptom.** **#16 Tiny Dead-Weight Tail** holds F and T as sub-1% odd lots (the scenario's whole point) — **no** `dead_weight` CTA in any tier; instead it shows the C1 false "buy UNH/V".
**Root cause.** Priority 8 requires the position to also be nearly flat: `w < 0.02 and ann <= 2.0` (`vector/lens/cta_engine.py:543`). A real odd-lot can have any slope, so the `ann <= 2.0` gate suppresses it. (This is the same "dead code" failure mode `CLAUDE.md` says was fixed — it is **not** fixed in this output.)
**Recommended change.** Base dead-weight detection on **weight + dollar value alone** (it is a tidy-up suggestion), not on slope; drop the `ann <= 2.0` condition or widen it substantially.

---

## MEDIUM

### M1. Duplicate `'Financials'` vs `'Financial Services'` sector keys (latent)
**Symptom/risk.** `SECTOR_SUGGESTIONS` and `LOW_BETA_BY_SECTOR` define **both** keys (`vector/constants.py:134-135, 177-178`). yfinance returns only `'Financial Services'`. The duplicate `'Financials'` key can therefore never be "held" → `_underweight_sectors_sorted` always lists it as unheld → a phantom "Financials 0%" recommendation even when JPM is held. (In this run the missing-data bug C1 dominates, masking it, but it is a real defect.)
**Recommended change.** Collapse to a single canonical taxonomy that matches yfinance (`'Financial Services'`), or normalize sector strings on ingest. Remove the duplicate key.

### M2. Winner-drift rebalance ignores tier (`sell_scale`)
**Symptom.** #35 *REBALANCE AAPL -$7,660* is **identical** across all three tiers; #43/#48 NVDA -$6,750/-$7,500 likewise.
**Root cause.** The rebalance amount is `(current_w − entry_w)×equity` capped at 35% of the position (`cta_engine.py:278-281`) and never multiplied by `sell_scale`, unlike every other sell (`cta_engine.py:218,245`).
**Recommended change.** Decide intentionally: either apply `sell_scale` so the trim varies by tier like other sells, or document why winner-drift is tier-invariant.

### M3. High-volatility sell magnitudes are large and counter-intuitive across tiers
**Symptom.** #49 Leverage Lover: *SELL SOXL* is **-$44,930 (moderate)** vs **-$22,460 (aggressive)** vs **-$8,990 (conservative)** — the moderate recommendation is ~$45k and exceeds the aggressive one.
**Root cause.** `dollars = pos_value × sell_scale × sev_factor` (`cta_engine.py:241-245`); `sell_scale` is higher for `regular` (0.5) than `high` (0.25), so moderate trims more than aggressive. No cap relative to position size is applied to vol sells.
**Recommended change.** Sanity-check the tier ordering of `sell_scale` for vol/decline sells, and consider a cap so a single sell can't dwarf the rest of the de-risking plan.

### M4. Caution score is non-monotonic and over-sensitive across tiers
**Symptom.** #12 → 92/61/35; #18 → 94/94/62; #19 → 94/94/64. A "good, minor flaw" book scoring 92 on conservative is alarmist.
**Root cause.** Tier thresholds shift per-position severities up/down, and the discrete floor (C2) amplifies each step. Conservative ends up highest-caution **and** lowest-action.
**Recommended change.** After C1/C2, validate that caution moves smoothly and sensibly with tier; cap how far tier alone can move the score for the same holdings.

---

## LOW / POLISH

### L1. Suggestion tickers are repetitive
Every Healthcare rec is **UNH**, every Financials rec is **V/JPM**, every beta fix is **JNJ/ABT/IBM**. `_pick_sector_tickers` always returns the top-market-cap name (`cta_engine.py:89-95`). Consider rotating among the candidate list for variety.

### L2. `index_fund_informational` HOLD shown at `moderate` severity
The informational index HOLD (`cta_engine.py:326-341`, severity hard-coded `moderate`) appears beside real CTAs (#10, #15, #16, #21, #23) and may slightly color perception. Consider `low`/`none` for a purely informational line.

### L3. Brief is identical across tiers even when the action plan differs drastically
#19 conservative (no sells) and moderate (near-full liquidation) share nearly identical briefs. The brief never reflects that the tier changed the recommended action. Quality improvement, not a bug.

### L4. "Trending upward" counts can contradict P&L
Direction counts come from 6-month slope (`slope.py:145,166-176`); a deeply underwater name that recently bounced reads as "up". Pairing "5 of 5 trending upward" (#28) with five underwater holdings is misleading — gate the "trending up" framing against unrealized P&L or soften the wording.

---

## Suggested fix order
1. **C1** (sector fallback) — unblocks the most wrong output; re-run to confirm whether the run was rate-limited.
2. **C2** (caution granularity) — largely resolves once C1 lands; then add intra-band interpolation.
3. **C3 / H1 / L4** (brief vs reality, clamped slope) — credibility of the headline text.
4. **H2 / H3 / H5** (contradictory SELL+HOLD, sub-floor buys, dead-weight) — self-contained CTA-list fixes.
5. **H4 / M2 / M3 / M4** (trim-vs-deposit logic, tier consistency) — behavioral tuning, validate against a re-run.
6. **M1 / L1 / L2 / L3** (taxonomy cleanup + polish).

_No code was modified in producing this diagnosis._
