# Vector Lens Engine — Diagnosis

_Source: `output.md` (50 synthetic portfolios × 3 risk tiers = 150 runs, generated 2026-05-28) cross-referenced against the engine source in `vector/lens/`._

_Scope: this is analysis only. No logic has been changed. Every finding cites the portfolio(s) that expose it and the file/line that causes it._

---

## Method

I read all 150 results in `output.md`, then traced each behaviour back through the pipeline:
`analyzers/* → analysis_pool.py → cta_engine.py → sentence{1,2,3}.py → lens_output.py`.
Findings are grounded in code, not inferred from symptoms alone. Live Yahoo prices (May 2026) mean some test portfolios no longer match their *intended* failure mode (e.g. "loser" names that have since recovered above entry) — where that matters I call it out so it isn't mistaken for an engine bug.

---

## Part A — What's working (keep / don't regress)

1. **Index-fund handling is excellent.** Detection, the informational `HOLD` CTA, exclusion from buy suggestions, and the sector-concentration downgrade for index-dominated books all work. #01/#03/#06/#08 produce clean, correct "this index fund *is* your diversification" briefs and never get told to "buy stocks to diversify." (`concentration.py:125-130`, `analysis_pool.py:100-106`, `cta_engine.py:611-617`).

2. **Genuinely healthy books resolve to `portfolio_healthy`.** #04 (all tiers), #05 (moderate/aggressive), #07 (moderate/aggressive), #24 (moderate/aggressive) correctly produce a single neutral HOLD. The "no signals" fallback (`cta_engine.py:596-606`) fires when it should.

3. **Concentration detection is monotonic across tiers and well-calibrated.** Triggers 20/30/40 % for low/regular/high (`constants.py:202-210`) produce sensible, tier-ordered behaviour: #11 (AAPL ~35 %) flags on conservative+moderate but is healthy on aggressive. The dilution-target fix (`_CONCENTRATION_DILUTION_FACTOR = 0.75`, `cta_engine.py:21`) is holding — no "$70 to fix a $17k book" regressions, and briefs correctly say "toward the 15 %/22 %/30 % target".

4. **Risk SELLs target the right names** in moderate/aggressive: steep-decline and high-vol sells correctly hit INTC, FUBO, RGTI, SOFI, LCID, etc. (#19, #32, #37, #42, #46). Severity scaling via `sell_scale` (0.10/0.50/0.25) is visible and ordered.

5. **Unrealized-loss HOLDs are accurate and graded.** Underwater names are identified with correct, monotone severity (#31, #36, #44, #47). Gains never flag (`performance.py:11-25`).

6. **Earnings-proximity catalyst sentence works.** AVGO (6 d), NKE (28 d), GME (12 d), CHPT (6 d) are detected and feed sentence 2 correctly (`earnings.py:28-37`).

7. **Two prior known-bug guards are holding:**
   - Winner-drift requires real appreciation (`current_value > cost_equity`, `concentration.py:74-75`) — no "price appreciation pushed…" text on underwater names.
   - SELL + winner-drift on the same ticker is suppressed (`cta_engine.py:260-261`) — no contradictory `SELL X` + `HOLD X winner_drift`.

8. **Conservative >50 % trim exception works.** #34 (TSLA 76 %) and #41 (PLUG 100 %) do produce a conservative SELL of the dominant position instead of suppressing it (`cta_engine.py:170`).

9. **Brief prose is fluent and varied** — deterministic template selection gives natural-sounding, non-repetitive language across portfolios.

---

## Part B — Issues, ranked by severity

### CRITICAL

#### B1. Broken/disaster portfolios are told to DEPOSIT, not de-risk ("deposit into a fire")

**Symptom.** The dominant recommendation for most MESSED-UP / DISASTER books is to buy more, producing a large *positive* net CTA delta:
- #49 Leverage Lover, conservative: **net +$13,800** (BUY JNJ $5,300 / UNH $8,840 / JPM $8,840, only SELL SOXL $9,180) — i.e. "deposit $13.8k into a leveraged-ETF book."
- #48 Everything Wrong, conservative: **net +$8,340**.
- #35 Extreme Winner Drift, conservative: **net +$5,500** while the actual problem (AAPL 79 %) only gets an *informational* hold.
- #41 Single 100 % PLUG (-68 %), conservative: **net +$630** deposit across a 4-name spread.
- #45 70 % BA loser, all tiers: net +$3,420 / +$5,100 / +$5,970, **zero sells** (BA's loss severity is only "moderate" so it's never trimmed).

**Root cause.** The CTA philosophy is "dilute concentration/sector/beta by *buying* underweight sectors." Every diversification priority (5 high-beta, 6 single-stock, 7 sector, 9 underweight) emits **buys** (`cta_engine.py:323-577`). Sells are simultaneously scaled down (`sell_scale`) and gated (`_sell_too_small` min $500 / min $1,000 position, `_conservative_sell_blocked`). The tier buy-cap (`_cap_total_buys`, `_MAX_TOTAL_BUY_FRACTION_BY_TIER = 0.20/0.30/0.35`, `cta_engine.py:31`) *is* working mechanically — but it only **bounds** the deposit to 20–35 % of equity; it does not flip the direction. So `net = capped_buys − scaled_sells` stays strongly positive on exactly the books where the user should be reducing risk. The cap was designed for this case (per the comment at `cta_engine.py:26-30`) yet 20 % of a large book is still a five-figure deposit recommendation.

**Why it matters.** A user staring at a -68 % single position or a leveraged-ETF book usually should *not* (and often cannot) add 20–35 % fresh capital; the correct move is to trim the dangerous holdings. The tool currently gives the opposite, unactionable advice for its worst-graded portfolios.

**Direction to consider (not yet implemented).** For high-caution/disaster books, prefer trim/rebalance of the offending positions over buy-to-dilute; or suppress net-positive deltas when caution is extreme; or make "buy to dilute" conditional on the book not already being in crisis. Relevant: `cta_engine.py` priorities 5/6/7/9, the sell gates (`_sell_too_small`, `_conservative_sell_blocked`), and `_apply_all_ctas` net-delta in `lens_output.py:279-376`.

---

#### B2. The `+250.0%` slope clamp produces non-credible, identical figures and incoherent briefs

**Symptom.** "+250.0% annualized" appears verbatim across many unrelated names and leads briefs that praise the portfolio's *worst* holding:
- #19 "The +250.0% annualized gain on INTC… strong momentum" (INTC is the designed loser).
- #15/#22 "+250.0%… on AMD", #28/#36 "INTC… +250.0%… strong momentum", #49 "+250.0%… on SOXL".

**Root cause.** `_SLOPE_CLAMP_MAX = 250.0` (`slope.py:18`). Beaten-down, high-volatility names that bounced off a trough have a genuinely huge 6-month regression slope (the trough-to-current cap at `slope.py:99-109` lets it through), which then pins to the round 250 ceiling. Because the ceiling is shared, several different portfolios open with the *identical* "+250.0%" phrase, which reads as a bug to any user. Note: the slope is price-history-relative, not entry-relative, so a "loser" that recovered above entry legitimately shows a positive slope — but the clamped magnitude is the problem.

**Direction to consider.** Lower / soften the clamp, or display a qualitative band ("strong uptrend") rather than an unbelievable precise number above some threshold, so two different names don't both read "+250.0%". `slope.py:18,124-136`.

---

#### B3. Caution score saturates at 88 and clusters on severity buckets — poor differentiation

**Symptom.** The score barely uses its range. The absolute worst books all tie:
- #34 (single 76 % TSLA), #49 (leveraged ETFs), #50 (2-name -62 %), #41 (100 % PLUG) → **all 88**.
- A wide band of distinct "moderate" books → **all 60** (#17, #25 every tier).
- Nothing in 150 runs exceeds **88**; the 89–99 band is dead.
- Caution is also nearly **tier-invariant** for risky books (same 88 or 60 regardless of tier), even though the recommended actions differ wildly.

**Root cause.** `_SEVERITY_CAUTION_POINTS = {none:0, low:8, moderate:30, high:60, critical:88}` (`lens_output.py:201`). `_risk_floor` (`lens_output.py:204-254`) takes `max(pos_pts, single_pts, port_pts)`, and `single_pts`/`port_pts` snap to those exact discrete values; for any genuinely risky book the floor (60 or 88) dominates the continuous trade-flow score, so the final score collapses onto the bucket. `critical = 88` is the structural ceiling, so 89–99 is unreachable (`_compute_caution_score`, `lens_output.py:257-276`).

**Direction to consider.** Make the severity→points mapping continuous / push `critical` toward 99, and let `pos_pts` (the already-continuous weighted average) carry more weight relative to the snapping `single_pts`/`port_pts`, so disasters spread across ~80–99 and moderates across ~30–60. `lens_output.py:201-276`.

---

### MEDIUM

#### B4. Dead-weight detection (priority 8) is dead code — never fires

**Symptom.** Zero `dead_weight` CTAs in all 150 runs. #16, explicitly built to test it (F, T sub-1 % odd lots), never flags them — instead it gets large sector-buy CTAs.

**Root cause.** Priority 8 requires `weight < 0.02` (`cta_engine.py:523`) but then runs the dollars through `_sell_too_small`, which rejects any position worth `< $1,000` (`_MIN_POSITION_VALUE_FOR_SELL`, `cta_engine.py:14,59-65,528`). A sub-2 % position in any realistic book is almost always worth < $1,000, so the two conditions are mutually exclusive. The detector can never pass its own gate.

**Direction to consider.** Exempt dead-weight from the min-position-value floor (it's a "clean up the tail" suggestion, not a risk trim), or drop the floor for this priority. `cta_engine.py:518-541`.

---

#### B5. Over-eager sector-underweight buys on already-diversified / near-perfect books

**Symptom.**
- #02 (graded NEAR-PERFECT, 10 sectors ~10 % each) → "deposit ~$2,400" across KO/APD/V (all tiers).
- #16 (graded GOOD) → "deposit ~$2,700" into GOOGL/AMZN while **ignoring its actual dead-weight tail**.

**Root cause.** Priority 9 fires whenever `sector_count >= 3` and any sector is `< 10 %` (`cta_engine.py:547-550`). In a genuinely equal-weight 10-sector book, several sectors naturally dip just under 10 %, so a near-perfect portfolio is told to deposit money. The `< 10 %` trigger doesn't account for "this book is already balanced." Same root applies to priority 7 firing on mildly-tilted books.

**Direction to consider.** Gate priority 9 on the book not already being well-diversified (e.g. require a meaningful gap below equal-weight, or skip when `sector_count` is high and the spread is tight). `cta_engine.py:543-577`.

---

#### B6. The brief leads by praising the most dangerous holding

**Symptom.** On risk-heavy books the very first sentence foregrounds the volatile/“rising” problem name positively: #15 opens "High volatility (63 %) on AMD has not derailed its +250.0 % uptrend" — for a portfolio whose top action is SELL AMD. The user reads praise of the thing they should sell.

**Root cause.** sentence1's branch ordering puts `high_vol_rising` (`sentence1.py:99-119`) ahead of the portfolio-state sentence, and it selects the *most volatile* ticker whenever slope > 5. The lead-sentence emphasis is decoupled from the portfolio's actual risk posture / top CTA.

**Direction to consider.** Reorder so the lead reflects the dominant signal (loss/risk) rather than the highest-vol *riser*, or tone down the "has not derailed its uptrend" framing for high-vol names. `sentence1.py:99-119`.

---

#### B7. `high_beta` BUY CTA is mislabeled and suggests names that aren't actually low-beta

**Symptom.** Reports show e.g. "BUY MSFT — high_beta (critical)" on a meme book (#30), and MSFT/AAPL are offered as the "low-beta" fix. The action (buy) under a reason named "high_beta" reads oddly, and the suggested tickers aren't genuinely low-beta.

**Root cause.** Priority 5 buys a "low-beta" name from an underweight sector to pull portfolio beta down (`cta_engine.py:323-372`), drawing from `LOW_BETA_BY_SECTOR`, whose Technology entry is `['MSFT','AAPL','ACN','IBM','TXN']` (`constants.py:131`) — high-beta megacaps. Suggesting more tech to a tech-light disaster also undercuts the intent.

**Direction to consider.** Curate `LOW_BETA_BY_SECTOR` to actually-defensive names, and reword the report tag so a buy-to-reduce-beta doesn't display as "high_beta." `cta_engine.py:323-372`, `constants.py:130-143`.

---

### LOW / POLISH

#### B8. "COST reports earnings in 0 days" (#05)
`days_until == 0` yields awkward "in 0 days" copy and implies a stale/as-of-today earnings date. Cosmetic. `earnings.py:90-95`, sentence2 templates.

#### B9. Conservative dilution wants *more* new capital than aggressive
Because the conservative concentration target is lower (15 % vs 30 %), the dilution math demands a larger deposit before the cap clips it. Counterintuitive that the low-risk tier is asked to invest the largest fraction. Worth a design review alongside B1. `cta_engine.py:380-391`, `constants.py:207-214`.

#### B10. Net-delta sign flips across tiers for the same book
e.g. #21: +$2,700 (cons) / -$600 (mod) / -$700 (agg); #33: +$3,170 / -$2,730 / +$2,870. Toggling risk tier flips "deposit" ↔ "withdraw," which is confusing. A downstream symptom of B1 + the sell gating.

#### B11. Stray `print()` debug in `analysis_pool.py`
`_build_positions_summary` still `print()`s a weight-sum warning to stdout (`analysis_pool.py:184-194`). CLAUDE.md notes the standalone copy converted these to `_log.debug`; the app copy did not. Spam risk in console builds.

---

## Part C — Cross-cutting themes

1. **The engine's core bias is "add, don't trim."** Four of the highest-priority non-sell actions are buys, sells are scaled+gated, and the safety cap only bounds (not redirects) deposits. This single design choice drives B1, B5, B9, and B10. It works fine for healthy/mild books and breaks down precisely at the disaster end where correct advice matters most.

2. **Discretization is hurting two outputs.** The `+250` slope clamp (B2) and the severity→points table (B3) both quantize continuous quantities onto a few values, producing identical-looking figures and coarse caution buckets.

3. **A few detectors are effectively unreachable** (dead-weight, B4) or fire too readily (sector-underweight on balanced books, B5) — the thresholds and the shared gates haven't been reconciled.

---

## Part D — Suggested priority order for fixes

| # | Issue | Severity | Primary file(s) |
|---|---|---|---|
| B1 | Disasters recommend net deposits, not de-risking | Critical | `cta_engine.py`, `lens_output.py` |
| B2 | `+250%` slope clamp → non-credible identical figures | Critical | `slope.py`, `sentence1.py` |
| B3 | Caution score saturates at 88 / bucket clustering | Critical | `lens_output.py` |
| B4 | Dead-weight priority can never fire | Medium | `cta_engine.py` |
| B5 | Sector-underweight buys on already-balanced books | Medium | `cta_engine.py` |
| B6 | Brief leads by praising the riskiest holding | Medium | `sentence1.py` |
| B7 | `high_beta` buy mislabeled / not-low-beta picks | Medium | `cta_engine.py`, `constants.py` |
| B8–B11 | Earnings "0 days", conservative dilution, tier sign-flip, stray `print` | Low | various |

_No code changed. Ready to discuss which of these to tackle and in what order._
