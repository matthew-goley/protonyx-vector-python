# Lens Engine Diagnosis v2 (post-fix review)

_Source: regenerated `output.md` (2026-05-29 10:40), after the LENS_VERSION 0.1.2 changes._
_Compared against: the previous run (10:12) and the v1 diagnosis (findings B1–B12, N1)._
_Engine files: `vector/lens/cta_engine.py`, `vector/lens/sentence3.py`, `vector/lens/lens_output.py`._

This builds on the v1 diagnosis. It records, for every v1 finding, whether the fix **worked**, **partially worked**, **did not fix it**, or **regressed**, then adds the **new issues (R-series)** the fixes introduced. No code was changed in this pass; the next pass will edit.

## Data-drift caveat (read first)

`output.md` is generated with **live yfinance prices**, and the two runs are ~28 minutes apart, so some differences are data, not code. Confirmed drift: loss percentages shifted slightly (AMC 72.8%→72.1%, COIN drawdown 14.6%→13.2%, NKE 61.2%→61.1%), and **#28 INTC now classifies as `winner_drift` (appreciating)** instead of a loser, breaking the "Dividend Trap" intent. When a single portfolio's behavior changed, I only call it a code effect if the mechanism is in the code I touched; otherwise it is flagged as possible drift.

---

## Status of v1 findings

| ID | v1 severity | Status now | Evidence |
|----|-------------|-----------|----------|
| B1 proceeds-aware buy cap | Critical | **FIXED** | de-risk plans now net ≤ ~0 across the board |
| B2 no-deposit-into-danger | Critical | **FIXED (mostly)** | conservative/disaster deposits gone; one new gap (R2) and a narrow miss (B3-residual) |
| B3 conservative net deposits | Critical | **PARTIALLY FIXED** | loss/vol-driven cases fixed; concentration-driven + one sub-threshold case remain |
| B4 dominant trim headlines brief | High | **FIXED** | #35, #12, #27, #43, #48 all now lead with the trim |
| B5 dead-weight sector exclusion (conservative) | High | **FIXED** | #16 conservative no longer buys GOOGL into the T odd-lot sector |
| B8 buy-CTA severity cap | Medium | **FIXED** | no buy CTA shows critical/high anymore |
| B9 caution top-band spread | High | **NOT EFFECTIVELY FIXED** | disasters still 95–96; new mis-rank (#38 > #36) |
| B6 equal-dollar splits | Medium | NOT FIXED (deferred) | #13/#18/#20/#45 identical amounts |
| B7 repetitive filler tickers | Medium | NOT FIXED (deferred) | GE/AMZN/PG/UNH/META everywhere |
| B10 tier monotonicity | Medium | NOT FIXED (and worsened, see R3) | #05 unchanged; #29 now non-monotonic |
| B11 clamp values verbatim | Low | NOT FIXED (deferred) | "+60.0%", "-80.0%" still present |
| B12 brief names one sector, list spans three | Low | NOT FIXED (deferred) | #13 brief "Consumer Defensive/PG" vs PG/AMZN/GE |

---

## A. What the fixes resolved (confirmed working)

### B1 — proceeds-aware buy cap: WORKING
Every plan that frees capital now nets ≤ ~0 (was strongly positive in v1):
- #15 moderate **-$10** (was +$2,720), aggressive **+$10** (was +$4,210)
- #19 moderate **-$2,720**, aggressive **+$10** (was +$2,890)
- #22 moderate **-$180** (was +$2,440), aggressive **-$280** (was +$4,370)
- #23 moderate **-$560** (was +$2,210)
- #28 moderate **-$1,250**, aggressive **+$10** (was +$3,430)
- #40 moderate **-$150** (was +$780)
- #36 aggressive **-$10** (was net positive)
Trim-redistribution (rebalance) cases still hold: #18 moderate net -$2,020, #45 -$3,900, #38 aggressive exactly $0 (buys capped to the NVDA trim).

### B2 — no deposit into a dangerous book with no proceeds: WORKING
- #21 conservative now **$0** (only HOLD VOO; was +$1,850 at caution 92)
- #22 conservative now **$0**
- #31/#32/#33/#40/#46/#47 conservative now **$0** (HOLDs only)

### B4 — the dominant trim headlines the brief: WORKING
The flagship case is fixed: **#35 all tiers now lead "AAPL's weight has expanded from 24% to 79% … rebalancing $7,640"** (v1 buried this behind a $370 JPM buy). Also #12, #18, #20, #27, #34, #41, #43, #45, #48, #50 now lead with the trim.

### B5 — dead-weight sector exclusion at conservative: WORKING
#16 conservative is now just "HOLD VTI" (no GOOGL buy into the 2-share T odd-lot sector). Net $0.

### B8 — buy-CTA severity capped: WORKING
All buy CTAs now read `moderate`/`low`. Examples: #12 `reduce_beta` moderate (was critical), #21 KO `reduce_beta` moderate (was critical), #29 JNJ `reduce_beta` moderate.

---

## B. New issues / regressions introduced by the fixes (R-series)

### R1. Empty "No CTAs generated" output (regression from B2)
**Observed:** #22 conservative now prints **"_No CTAs generated._"** with caution 93. The brief still says the right thing (`portfolio_caution`), but the CTA panel is empty.
**Cause:** the priority-11 `portfolio_healthy` fallback in `compute_ctas` is appended **before** the new buy-drop branch (`cta_engine.py` ~line 773). When B2 drops all buys and the book has no sells/holds to leave behind (conservative tier, vol-danger so no `unrealized_loss` HOLDs, no index HOLD), the list ends empty.
**Fix next pass:** after the buy-drop branch, if `ctas` is empty, append a synthesized `hold` CTA (`portfolio_caution` when `danger`/caution is elevated, else `portfolio_healthy`) so the list is never empty. (Severity-aware so the UI renders a card consistent with the brief.)

### R2. A concentrated position can lose all CTA representation when its dilution buys are dropped
**Observed:**
- #19 conservative: only **HOLD NKE**. INTC at **49% weight** (high-vol) is neither sold (suppressed at conservative) nor mentioned — its single-stock dilution buys were dropped by B2, and nothing replaced them. The brief even says "other risk signals are not confirming a sell."
- #29 moderate: see R3.
**Cause:** priority-6 single-stock concentration emits **buy-to-dilute** CTAs; when those are dropped (B2) or capped to zero (B1), the concentration risk has no remaining CTA. There is no informational fallback for "concentrated but we're not acting."
**Fix next pass:** when a single-stock/sector concentration flag exists but its dilution buys were dropped/zeroed, emit an informational `hold` (e.g. `reduce_concentration_informational`) for the heavy ticker so the risk stays visible, mirroring `winner_drift_informational`.

### R3. B1 over-couples an unrelated risk-sell with diversification buys
**Observed:** #29 "All Tech" (100% Technology):
- conservative → **+$2,530** (3 diversification buys; coherent: "diversify your single-sector book")
- aggressive → **+$5,670** (3 diversification buys)
- moderate → **only SELL ORCL -$660**, diversification buys **gone**
At the moderate tier ORCL trips the volatility sell, so B1 caps **all** buys to the $660 ORCL proceeds, which then fall below the noise floor and are dropped. A small, unrelated vol-sell wiped the legitimate "you are 100% tech, diversify" advice that both neighboring tiers give.
**Cause:** `cta_engine.py` ~lines 764–772 caps **every** buy to **total** sell+rebalance proceeds, regardless of whether the buy addresses the same risk as the sell. A $660 vol-trim of ORCL is not "capital freed for diversification."
**Fix next pass (design choice for the next prompt):** make the proceeds cap risk-aware. Options:
1. Only cap diversification buys against `rebalance`/`reduce_concentration` proceeds (the redistribution semantics), and treat `sell` (steep_decline/high_volatility) proceeds separately so a vol-sell doesn't suppress sector diversification.
2. Allow a small base diversification allowance (e.g. `min(base_fraction, …)`) even when a sell is present, so concentration advice survives a minor risk-trim.
3. Only apply the sell-proceeds cap when the buys are dilution of the **sold name's** concentration (same-ticker/same-sector), not for independent sector-underweight buys.

### R4. Tiny residual positive net deltas (+$10)
**Observed:** several capped de-risk plans land at exactly **+$10** (#15 aggressive, #19 aggressive, #26 aggressive, #28 aggressive).
**Cause:** `_cap_total_buys` scales buys to the proceeds then `_round10` rounds to the nearest 10, which can nudge a buy $10 above the proceeds.
**Fix next pass:** floor (round down) buy amounts after the proceeds cap, or subtract one rounding step, so a "redistribute" plan is never net positive. Cosmetic but it contradicts the B1 invariant.

---

## C. Still unresolved from v1

### B9 — caution score still saturates the top band (and now mis-ranks)
The 0.8→0.65 breadth-multiplier change shaved only ~1 point off the top; disasters moved from 96–97 to **95–96**. Granularity at the top is essentially unchanged, and there is a **clear mis-ordering**:
- **#38 conservative = 96** — a 2-stock book (AAPL+NVDA) where **both are rising winners**, NVDA at 55%. Pure concentration.
- **#36 conservative = 95** — five positions all **45–70% underwater** (Deep Losers Club).
A book of rising winners should not out-score a book of five deep losers. The driver is `single_pts` in `_risk_floor` (`lens_output.py` ~lines 247–249): any one position with a `critical` concentration flag contributes `P[critical]=90 × min(1, w/0.45)`, so a single 55% holding pins the floor to ~90 before the breadth lift. Concentration is **structural exposure**, not realized danger, yet it scores like a critical loss.
**Fix next pass:**
- Lower the `critical`/`high` anchors in `_SEVERITY_CAUTION_POINTS` (e.g. critical 90→80, high 62→55), or
- Down-weight **concentration** severity relative to **volatility/performance** in `single_pts`/`pos_pts` (a 55% rising position is less dangerous than a 55% crashing one), and/or
- Reduce the breadth multiplier further (0.65→~0.5).
This also fixes the optics in section D below.

### B3 — residual conservative deposits (two distinct sub-cases)
The B3 fix resolved the loss/vol-driven cases. Two patterns remain:

**(a) Coherent and arguably acceptable — concentration-driven deposits.** #11, #13, #17, #25, #29, #39 still net positive because the flagged risk is *under-diversification*, and depositing into other sectors is the correct remedy. These are defensible **if** the caution score reflected concentration as lower-grade than realized loss (see B9). Right now #29 conservative reads **caution 92 + deposit $2,530**, which *looks* contradictory only because B9 over-scores concentration. Fixing B9 makes these coherent without removing useful advice. Recommend: do **not** suppress these buys; fix the caution score instead.

**(b) Genuinely still wrong — sub-threshold speculative losers.** #23 conservative: net **+$1,840**, brief leads "Elevated volatility (56%) … SOFI -75.9%", then recommends depositing into PG/AMZN/GE. The SOFI/SOUN risk is real but their combined weight keeps `danger_weight` below the **0.30** `_NO_DEPOSIT_DANGER_WEIGHT` gate, and their sells are suppressed at the conservative tier, so B2 never fires.
**Fix next pass:** trigger the no-deposit gate when **any position has a `critical` signal whose sell was suppressed** (conservative tier), not only when aggregate `danger_weight ≥ 0.30`. That catches a small-but-critical speculative loser without lowering the global threshold (which would risk false positives on mild books).

### B6 — equal-dollar diversification splits (deferred in v1, still present)
#13 PG/AMZN/GE all **$890**; #18 AMZN/GE/META all **$400**; #20 all **$570**; #45 all the same. `_split_dollars_by_underweight` gives equal scores to fully-unheld sectors. Low priority; decide whether to consolidate into fewer larger buys or accept and document.

### B7 — repetitive filler tickers (deferred, still present)
GE, AMZN, PG, UNH, JPM, META recur as the suggestion in nearly every portfolio (`_pick_sector_tickers` returns the head of each sector list deterministically). Quality/personalization gap.

### B10 — tier non-monotonicity (still present, now with a new instance)
- #05 unchanged: conservative healthy (27), **moderate SELL MA (27)**, aggressive healthy (14).
- **New instance (from R3):** #29 conservative deposits, moderate only sells ORCL, aggressive deposits — the moderate tier behaves qualitatively differently from both neighbors.

### B11 — clamp boundary values printed verbatim (deferred, still present)
"+60.0%" in #15/#22/#49; "-80.0%" in #31/#37/#42/#44.

### B12 — brief names one sector while the CTA list spans three (deferred, still present)
#13 brief cites "Consumer Defensive … PG" but the CTAs are PG (Cons. Defensive), AMZN (Cons. Cyclical), GE (Industrials).

---

## D. Cross-cutting insight: concentration is over-weighted in the risk floor

Three separate symptoms share one root cause — **the caution floor treats single-stock/sector concentration as equivalent to a realized critical loss**:
1. B9 mis-rank (#38 rising-winners 96 > #36 deep-losers 95).
2. B3(a) "caution 92 + deposit" optics on healthy concentrated books (#29).
3. #38/#49 conservative scoring 95–96 on books whose only issue is one dominant *rising* position.

Recommend treating concentration as a **lower-grade** contributor than volatility/performance in `_risk_floor` (`lens_output.py`). This is the single highest-leverage change for the next pass: it corrects the score ordering and removes the "deposit at caution 92" appearance without touching the (correct) advice.

---

## Priority order for the next editing pass

1. **R3** — make the proceeds cap risk-aware so a small vol-sell does not wipe diversification advice (`cta_engine.py`). Highest behavioral impact; currently loses correct advice at the moderate tier.
2. **D / B9** — down-weight concentration in `_risk_floor` and/or lower the severity anchors so the score stops mis-ranking and the "caution 92 + deposit" optics disappear (`lens_output.py`).
3. **R1** — never emit an empty CTA list; synthesize a `portfolio_caution`/`portfolio_healthy` HOLD after the buy-drop (`cta_engine.py`).
4. **R2** — informational HOLD for a concentrated name whose dilution buys were dropped (`cta_engine.py`).
5. **B3(b)** — extend the no-deposit gate to "a critical signal whose sell was suppressed" (`cta_engine.py`).
6. **R4** — floor buy amounts after the proceeds cap so net delta is never +$10 (`cta_engine.py`).
7. **B6 / B7 / B11 / B12** — quality polish (splits, suggestion variety, clamp wording, brief/CTA sector reconciliation), lower priority.

All Lens-logic edits in the next pass must bump `LENS_VERSION` (`constants.py`, currently `0.1.2`) and update the affected "don't regress" notes in `CLAUDE.md`.
