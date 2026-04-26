# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Vector** is a PyQt6 desktop portfolio analytics app for stock investors. It tracks positions, fetches market data via Yahoo Finance (yfinance), and displays analytics (trend direction, volatility, sector allocation, Sharpe ratio, beta, dividends) in a customisable dark/light themed dashboard. Data is persisted locally in `%LOCALAPPDATA%/Protonyx/Vector/` (falls back to `~/Vector/data/`) as JSON files.

Current version: **0.4.2**

## Setup & Running

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

No build step, test suite, or linter is configured.

## Building (Nuitka)

Use `build.bat` (release) or `build-debug.bat` (console-enabled for tracebacks). Both wipe the previous `.dist/` folder first.

```bash
python -m nuitka --standalone --windows-console-mode=disable --enable-plugin=pyqt6 ^
  --output-filename="Vector-v0.4.2.exe" ^
  --include-data-dir=assets=assets ^
  --include-data-dir=vector/lens/templates=vector/lens/templates ^
  --include-package=vector.lens --include-package=vector.lens.analyzers ^
  --include-package=yfinance --include-package=pandas --include-package=numpy ^
  --include-package=lxml --include-package=bs4 --include-package=requests ^
  --include-package=urllib3 --include-package=certifi ^
  main.py
```

- `--include-data-dir=assets=assets` copies the entire `assets/` folder next to the exe
- `--include-data-dir=vector/lens/templates=...` bundles `sentences.json` — required or all Lens sentences come back empty
- `--include-package=yfinance|pandas|numpy|lxml|bs4|requests|urllib3|certifi` — yfinance runtime deps Nuitka misses statically; without these, onboarding crashes on ticker validation
- `--include-package=vector.lens|vector.lens.analyzers` — belt-and-suspenders for the Lens subpackages
- `resource_path()` automatically resolves assets correctly in all three environments: dev, PyInstaller, and Nuitka standalone (see `vector/paths.py`). `vector/lens/_templates.py` uses it with a package-local fallback, so `sentences.json` loads regardless of where the packager placed it.

## Architecture

### Module Responsibilities

| Module | Role |
|---|---|
| `main.py` | Entry point — calls `vector.app.main()` |
| `vector/app.py` | Thin shell: `DARK_STYLESHEET`, `LIGHT_STYLESHEET`, `MainShell`, `VectorMainWindow`, `_ShortcutsDialog`, `main()` — all page classes live in `vector/pages/` |
| `vector/pages/dashboard.py` | `DashboardPage`, `DashboardGrid`, `WidgetPickerDialog`, grid constants (`_UNIT`, `_GAP`, `_CELL`, `_CONTENT_W`) |
| `vector/pages/lens_page.py` | `VectorLensPage`, `_GraphCard`, `_PieCard`, `_CTAReportCard`, `_CautionCard`, `_MCContextCard`, `_LensHistoryDialog`, `_LensHistoryCard`, `_CautionBadge` |
| `vector/pages/onboarding.py` | `OnboardingPage`, `PositionDialog`, `PositionCard`, `_RiskTierCard` |
| `vector/pages/profile.py` | `ProfilePage` |
| `vector/pages/settings.py` | `SettingsPage`, `_AccordionSection`, `_AnimatedChevron`, `QDoubleSpinBoxCompat`, `_RiskTierOption` |
| `vector/analytics.py` | Portfolio math: trend slope, volatility, Sharpe ratio, beta, insight HTML generation |
| `vector/store.py` | `DataStore` — single source of truth: positions, settings, app state, market data, layout |
| `vector/lens_engine.py` | Thin wrapper: `generate_lens()` returns 7-tuple, `generate_lens_full()` returns complete result dict |
| `vector/lens/` | **Lens engine package** — modular analysis, CTA generation, sentence composition |
| `vector/lens/lens_output.py` | Top-level assembler: orchestrates pool → CTAs → sentences → result dict. Also writes `lens_history.json` snapshots (rolling 50) with dedup. |
| `vector/lens/analysis_pool.py` | Runs all 8 analyzers, caches results, handles dependencies and post-processing |
| `vector/lens/cta_engine.py` | Generates prioritized CTAs with dollar amounts from analyzer results |
| `vector/lens/risk_profile.py` | Loads user risk tier (`high`/`regular`/`low`), returns threshold overrides |
| `vector/lens/sentence1.py` | Portfolio state composer (slope + volatility → one sentence) |
| `vector/lens/sentence2.py` | Timing/catalyst composer (earnings + dividends → one sentence) |
| `vector/lens/sentence3.py` | CTA composer (top-priority action → one sentence) |
| `vector/lens/analyzers/slope.py` | Per-ticker and portfolio slope (direction) analysis. Uses `_log.debug` for slope-correction diagnostics (no stdout spam). |
| `vector/lens/analyzers/volatility.py` | Per-ticker and portfolio volatility analysis |
| `vector/lens/analyzers/concentration.py` | Stock weight, sector weight, winner drift detection |
| `vector/lens/analyzers/earnings.py` | Upcoming earnings dates + EPS estimates + outlook |
| `vector/lens/analyzers/dividends.py` | Upcoming ex-dividend dates + trailing yield |
| `vector/lens/analyzers/beta.py` | Per-ticker and portfolio beta vs SPY |
| `vector/lens/analyzers/performance.py` | Unrealized P&L from cost basis |
| `vector/lens/analyzers/index_fund.py` | Index ETF detection and classification |
| `vector/lens/templates/sentences.json` | All sentence templates (5+ variations per category) |
| `vector/lens/debug_runner.py` | Synthetic-portfolio harness for exercising the Lens engine offline. Passes `save_history=False` so test runs do not pollute `lens_history.json`. |
| `vector/monte_carlo.py` | `run_projection()`, `build_historical_curve()` — GBM Monte Carlo simulation |
| `vector/widget_base.py` | `VectorWidget` — base `QFrame` for all dashboard widgets; handles edit-mode drag, context menu |
| `vector/widget_registry.py` | `discover_widgets()` / `get_widget_class()` — registry of all concrete widget types |
| `vector/widget_types/` | 8 concrete widget implementations + `LensDisplay` |
| `vector/widgets.py` | Shared UI primitives: `CardFrame`, `GradientBorderFrame`, `GradientLine`, `BlurrableStack`, `DimOverlay`, `EmptyState`, `LoadingButton` |
| `vector/constants.py` | File paths, TTL constants, default settings values, threshold maps, `APP_VERSION` |
| `vector/paths.py` | `resource_path()` (PyInstaller + Nuitka-aware asset lookup), `user_data_dir()`, `user_file()` |

### Pages subpackage (`vector/pages/`)

All page-level QWidget classes live here. `vector/app.py` imports from this subpackage — do not put new page classes directly in `app.py`.

- `_CONTENT_W = 1090` is defined in `pages/dashboard.py` and imported by `pages/lens_page.py` and `pages/settings.py` for consistent fixed-width scroll layout.
- All three scrollable pages (Dashboard, Lens, Settings) use `setWidgetResizable(False)` + `container.setFixedWidth(_CONTENT_W)` so content width is stable on window resize and the scrollbar sits at the window edge.

### Widget Types (`vector/widget_types/`)

| Class | Widget |
|---|---|
| `TotalEquityWidget` | Total portfolio value with 5-day change |
| `PortfolioVectorWidget` | Direction arrow + slope % |
| `PortfolioVolatilityWidget` | Volatility score gauge |
| `PortfolioDiversificationWidget` | Sector allocation pie |
| `PortfolioBetaWidget` | Portfolio beta vs benchmark |
| `SharpeRatioWidget` | Annualised Sharpe ratio (score value rendered at 16pt — **not** 22pt; do not re-inflate) |
| `PositionsListWidget` | Scrollable positions table |
| `DividendCalendarWidget` | Upcoming dividend dates |

### Vector Lens (`vector/widget_types/lens.py`)

`LensDisplay` is a reusable QFrame (not a VectorWidget) that renders the "Lens Brief" readout with typewriter animation and gradient-highlighted text. It is a **permanent fixture** on the dashboard (cannot be removed or repositioned) and also appears on the dedicated Vector Lens page. The dashboard instance includes a "Vector Lens ›" button that navigates to the full Lens page.

**Defensive QTimer pattern:** The typewriter timer (`_tw_timer`) can have its underlying C++ wrapper torn down during widget reparenting (e.g., when a position is added mid-refresh). `_ensure_tw_timer()` probes with `isActive()` inside try/except RuntimeError and reconstructs the QTimer on demand. All three call sites (`_start_typewrite`, start of `_tw_step`, both timer-access points) defer to `_ensure_tw_timer()` before touching the timer. Do not remove this defensive pattern.

### Adding a New Widget

1. Create `vector/widget_types/<name>.py` with a class subclassing `VectorWidget`
2. Set `NAME`, `DESCRIPTION`, `DEFAULT_ROWSPAN`, `DEFAULT_COLSPAN` class attributes
3. Implement `__init__(self, window=None, parent=None)` — call `super().__init__()` first
4. Override `refresh(self)` to update the display when data changes
5. Register it in `vector/widget_registry.py` by importing and adding to `_WIDGETS`
6. `window` arg gives access to `window.store`, `window.positions`, `window.settings`

### Startup & Splash Screen

`main()` in `vector/app.py` follows this exact sequence:

1. `QApplication` is created and the taskbar icon is set.
2. `assets/splashboard.png` is loaded and displayed immediately as a `QSplashScreen` (700×400 px, centred on the primary screen, always-on-top) — this is the **first thing the user sees**.
3. `app.processEvents()` forces the OS to paint the splash before any heavy work begins.
4. `VectorMainWindow()` is constructed (loads data, builds UI) while the splash remains visible.
5. The splash is shown for a **minimum of 2 seconds** total. If construction finishes in under 2 s, a `QTimer` waits out the remainder.
6. `splash.finish(window)` closes the splash and `window.show()` reveals the main window.

### Data Flow

1. `VectorMainWindow` owns `DataStore`, all settings/state, and the `QTimer` for auto-refresh.
2. On startup: load JSON state → show `OnboardingPage` (first run) or `MainShell` (returning).
3. `MainShell` hosts a sidebar + `QStackedWidget` with `DashboardPage`, `VectorLensPage`, `ProfilePage`, `SettingsPage`. Header contains a "?" icon button (48×48 px, rounded) that opens the keyboard-shortcuts modal.
4. `DashboardPage` has a permanent `LensDisplay` at the top, followed by a free-form grid of `VectorWidget` instances; grid layout is loaded from / saved to `dashboard_layout.json`. Beneath the grid, a muted "Last updated N minutes ago" label updates every 30 s from a second `QTimer`.
5. `DashboardPage.update_dashboard()` calls `compute_portfolio_analytics()` → refreshes the lens, calls `widget.refresh()` on each placed widget, and stamps `_last_refresh` (used by `_update_refresh_label()`).
6. Edit mode (toolbar button) enables drag-to-reposition and right-click delete on grid widgets (the lens is not affected).
7. A `QTimer` drives auto-refresh at the interval set in `SettingsPage` (1 min / 5 min / 15 min / manual).

### Keyboard Shortcuts

Registered in `VectorMainWindow._register_shortcuts()`. All use `QShortcutContext.ApplicationShortcut` unless otherwise noted.

| Key | Action |
|---|---|
| **R** | Refresh all data |
| **L** | Open Lens page |
| **D** | Open Dashboard page |
| **S** | Open Settings page |
| **A** | Open Add Position dialog (only active on onboarding page; widget-scoped) |
| **?** | Open Keyboard Shortcuts modal (`_ShortcutsDialog`) |
| **Esc** | Close any open modal |
| **Space** | Advance to next onboarding step (widget-scoped on `OnboardingPage`; ignored if focus is a `QLineEdit`) |

The "?" button in the MainShell header also opens the shortcuts modal. Button is 48×48 px with radius 24 and `padding: 0` — do not shrink; glyph clips at smaller sizes.

### Analytics Engine (`analytics.py`)

- **Direction**: 6-month linear regression slope (annualised %). Thresholds (configurable): Strong ≥18%, Steady ≥5%, Neutral ±5%, Depreciating ≤-18%, Weak ≤-5%.
- **Volatility**: Annualised std-dev of daily returns scaled to 1–100; configurable lookback (3mo/6mo/1y).
- **Sharpe ratio**: Annualised, using a 4.5% risk-free rate, from `portfolio_daily_returns()`.
- **Beta**: Portfolio covariance / benchmark variance via `portfolio_beta()`.
- **Insights**: `_direction_insight`, `_volatility_insight`, `_diversification_insight` return rich-text HTML with data-quality warnings when history is sparse.

### Lens Engine (`vector/lens/` package)

The Lens engine is a modular, tree-structured system: **analyzers → analysis pool → CTA engine → sentence composers → assembler**.

**Entry points:** `lens_engine.py` provides two functions:
- `generate_lens()` — returns the canonical **7-tuple** `(text, color, recommended_tickers, deposit_amount, underweight_sector, action_type, caution_score)` for `LensDisplay.refresh()` and dashboard use.
- `generate_lens_full()` — returns the complete result dict (all 7-tuple fields plus `full_report`, `ctas`, `threat_level`, `pool_results`, `projected_positions`, `net_cta_delta`) for the full Lens page.

**Pipeline flow:**
1. `risk_profile.py` loads the user's risk tier (`high`/`regular`/`low`) and returns threshold overrides
2. `analysis_pool.py` runs all 8 analyzers (slope/vol first, then earnings with prior results, then rest)
3. Post-processing: index-fund suppression forces `concentration` flags off for index ETF tickers
4. `cta_engine.py` reads analyzer results and generates prioritized CTAs with dollar amounts (sector-aware — never suggests tickers in the problem sector; diversification CTAs generate up to 3 buys across different underweight sectors)
5. `sentence1.py` composes a portfolio state sentence from slope + volatility data
6. `sentence2.py` composes a timing/catalyst sentence from earnings + dividends data
7. `sentence3.py` composes a CTA sentence — **always prefers diversification CTAs** (`reduce_concentration`, `sector_underweight`) for the brief
8. `lens_output.py` joins the 3 sentences, computes caution score, applies all CTAs to build `projected_positions`, writes a history snapshot, and returns the full result dict

**Analyzer interface:** Every analyzer exposes `analyze(positions, store, settings, risk_profile) → dict` with `ticker_results` (per-ticker) and `portfolio_result` (aggregate). Each result has `value`, `severity` (`none`/`low`/`moderate`/`high`/`critical`), `flag` (bool), `weight`, and `details`.

**CTA priorities (11 levels, 1 = highest):**
1. Steep decline (sell)
2. Excessive volatility (sell)
3. Winner drift (rebalance)
4. Index fund informational (hold)
5. High portfolio beta (buy) — prefers low-beta tickers from underweight sectors
6. Single-stock concentration (buy — up to 3 CTAs across underweight sectors, excludes the concentrated ticker's sector)
7. Sector over-concentration (buy — up to 3 CTAs, always excludes the overweight sector)
8. Dead weight (sell)
9. Underrepresented sector (buy — up to 3 CTAs, one per thin sector <10%)
10. Unrealized loss (hold)
11. Portfolio healthy (hold)

**Buy amount caps:** `_cap_buy_amount()` is applied to every buy-type priority (5, 6, 7, 9) so diversification deltas remain proportional to portfolio size.

**Sell gates:** Priority 8 (dead weight) is additionally gated by `_sell_too_small()` — tiny positions don't generate sell CTAs.

**Sector awareness:** `_get_ticker_sector()` in `cta_engine.py` looks up a ticker's sector via `SECTOR_SUGGESTIONS`. Every buy CTA verifies the suggested ticker is NOT in the problem sector. `_underweight_sectors_sorted()` returns all sectors sorted lightest-first, with an `exclude_sectors` parameter to skip problem sectors. `_split_dollars_by_underweight()` allocates dollars proportionally to how underweight each target sector is.

**Risk profiles:** Three tiers (`high`/`regular`/`low`) with different severity thresholds per analyzer. Stored in `constants.py` as `DEFAULT_RISK_PROFILES`. User overrides from `settings.json` → `lens_signals` take precedence. Risk tier stored in `settings.json` → `risk_tier` (default `"regular"`), selectable during onboarding and in Settings → Investment Style.

**Sell aggressiveness:** Sell thresholds are raised across all tiers. `sell_scale` controls the fraction of calculated sell amount recommended: `high` = 0.3, `regular` = 0.5, `low` = 0.15. Conservative tier (`low`) additional gates:
- **Priorities 1 & 2:** Only fire on `critical` severity (`high` suppressed).
- **Priority 3:** Converted to informational `hold` with `winner_drift_informational` reason.
- **Priority 8:** Suppressed entirely.

**P&L-aware sentence1:** `sentence1.py` selects the highlighted ticker by preferring alignment between unrealized loss and negative slope (and the inverse). Sentences route to `combined.position_loss_with_volatility` templates when a losing position also has high volatility.

**Sentence templates:** All templates live in `vector/lens/templates/sentences.json`. Selection is deterministic (SHA-256 hash of portfolio state). All language is observational — no directives.

**Color mapping:** `sell` → `#ff4d4d`, `rebalance` → `#ff9f43`, `buy_new`/`buy_more` → `#38bdf8`, `hold` → `#8d98af`.

**Caution score:** 1–99, computed as `total CTA dollars / total equity × 100` (clamped).

**Projected positions:** `_apply_all_ctas()` in `lens_output.py` applies every CTA to a deep copy of positions:
- `sell`/`rebalance`: reduces position value (removes if fully sold)
- `buy_more`: increases existing position value
- `buy_new`: adds a new position (fetches sector/name from store)
- `hold`: no change

Returns `projected_positions` (list) and `net_cta_delta` (net cash flow: buys minus sells).

**Lens history snapshots:** `_save_snapshot()` in `lens_output.py` appends to `lens_history.json` (schema: `{"snapshots": [ ... ]}`) on every successful run, capped at 50 entries (rolling). **Dedup guard:** skips append if `brief`, `caution_score`, `action_type`, and `cta_count` all match the most recent entry — the history file only grows when something material changes. `build_lens_output()` accepts `save_history=True` (default); debug runners pass `save_history=False` to avoid polluting real history.

`LensDisplay.refresh()` in `widget_types/lens.py` handles all tuple lengths (7, 6, 5, 4, 3, 2) for backwards compatibility.

### Vector Lens Page Layout (`pages/lens_page.py`)

Top-to-bottom order inside the scroll container:

1. **History button** (top-right, opens `_LensHistoryDialog`)
2. **Lens Brief** (`LensDisplay`, fixed height 200)
3. **Row: Caution Score (left, fixed 340 px, `AlignTop`, stretch 0) + All Projections (right, `Expanding × Preferred`, stretch 1)**
4. **Row: Graph A + Graph B** (side by side, equal width)
5. **MC Context Card** (full width, alone)
6. **Row: Pie A (Current Allocation) + Pie B (Projected Allocation)**

The row arithmetic is tight: 340 (caution) + 16 (spacing) + 734 (projections) = 1090 (`_CONTENT_W`). Do not add a fixed/min width to `_CTAReportCard` or it will overflow.

### `_CTAReportCard` — Dynamic Sizing (critical, don't regress)

Displays all CTA projections in a scroll area. Sizing is measured, not estimated — earlier hardcoded per-card heights produced clipping.

**Structure (flat, no nested wrappers):**
```
_CTAReportCard (QFrame#cardFrame, Expanding × Minimum)
  └─ QVBoxLayout (outer: 20,16,20,16)
      ├─ Title "All Projections"
      └─ QScrollArea (custom wheel handler)
          └─ _items_container QWidget
              └─ _items_layout QVBoxLayout (margins 0,0,0,4; spacing 4)
                  ├─ card 0  (stretch 0)
                  ├─ card 1  (stretch 0)
                  ├─ …
                  └─ addStretch(1)   ← absorbs excess vertical space
```

**Per-card structure (flat):**
```
QFrame (Expanding × Minimum)
  └─ QVBoxLayout (margins 10,4,10,4; spacing 2)
      ├─ tag QLabel    (AlignBottom | AlignLeft, setFixedHeight(fm.ascent() + 2))
      └─ text QLabel   (word-wrap, AlignTop | AlignLeft, Expanding × Minimum)
```

**Stylesheets must use class selectors** (`QFrame { … }` / `QLabel { … }`) to avoid Qt's "Could not parse stylesheet" warnings. Only supported properties: `background-color`, `border`, `border-left`, `border-radius`, `color`, `font-size`, `font-weight`, `background: transparent`. **No `padding` or `margin` in stylesheets** — use `setContentsMargins` in Python instead. No `box-shadow`, `calc()`, `gap`, `transform`, `::before/::after`.

**Why each piece matters:**
- `tag.setFixedHeight(fm.ascent() + 2)` + `AlignBottom` on tag + `AlignTop` on text → eliminates QLabel's natural leading gap between the action tag and the description.
- `text` is 20pt white (`#e7ebf3`); `tag` is 10pt in the action's color.
- Trailing `addStretch(1)` in `_items_layout` absorbs any surplus space so individual cards are not stretched beyond their `sizeHint` (cards have `Minimum` vpolicy which CAN grow without the stretch).
- `addWidget(card, 0)` sets stretch factor 0 on each card so only the stretch grows.

**Measure-don't-guess sizing (`_resize_for_cards`):**
```python
MAX_HEIGHT = 750
PADDING = 24
self._items_container.adjustSize()
self._items_layout.activate()
self._items_container.layout().activate()
actual = self._items_container.sizeHint().height()
if actual + PADDING <= MAX_HEIGHT:
    self._scroll.setVerticalScrollBarPolicy(ScrollBarAlwaysOff)
    self._scroll.setFixedHeight(actual + PADDING)
else:
    self._scroll.setVerticalScrollBarPolicy(ScrollBarAsNeeded)
    self._scroll.setFixedHeight(MAX_HEIGHT)
```

Called via `QTimer.singleShot(0, …)` after `set_report()` so word-wrap widths are final before measurement. Scroll's custom `wheelEvent` calls `event.ignore()` when `verticalScrollBar().maximum() == 0` so wheel bubbles up to the outer page when there's nothing to scroll.

### Lens Projections (`_GraphCard`)

GBM projection graphs (referred to as "Lens Projections" in the UI, not "Monte Carlo"):

- Graph A ("Current Portfolio"): current positions as-is.
- Graph B ("With All Lens Projections"): uses `projected_positions`. Title shows **net** dollar change: "— +$X" or "— -$X".
- Both pass `total_equity` as `current_value` to `run_projection` so historical curves normalise to the same base.
- Projections display % change relative to current equity.
- **Graph margins (1080p-safe):** `subplots_adjust(left=0.06, right=0.88, top=0.90, bottom=0.22)`. Do not reduce `bottom` below 0.22 — it clips y-axis labels.
- **Canvas min height:** `self._canvas.setMinimumHeight(320)`. Do not drop below 320 at 1080p.
- matplotlib `FigureCanvasQTAgg` captures wheel events — fixed with `self._canvas.wheelEvent = lambda event: event.ignore()` so scrolling works when the mouse is over a chart.
- Monte Carlo parameters configurable via Settings → Monte Carlo. Constants: `MONTE_CARLO_HORIZON_DAYS`, `MONTE_CARLO_SIMULATIONS`.

### Lens History Dialog (`_LensHistoryDialog`)

Opened from the History button on the Lens page. Shows `lens_history.json` snapshots newest-first inside `_LensHistoryCard` entries (each with a `_CautionBadge` circle, relative timestamp, brief text, footer with `cta_count` and `total_equity`).

**Clear History:** button at the bottom-left of the dialog. Shows a `QMessageBox.question` confirmation ("Yes"/"No", default No). On Yes, overwrites `lens_history.json` with `{"snapshots": []}` and closes the dialog.

### Settings Page (`pages/settings.py`)

Seven accordion sections plus static sections:

| Section | Type | Contents |
|---|---|---|
| General | Static card | Theme, currency, date format |
| Investment Style | Static card | Risk tier selection (Conservative/Moderate/Aggressive) — immediate save on click |
| Data & Refresh | Accordion | Auto-refresh interval, clear cache, reset all data, **Export Positions to CSV** |
| Portfolio Direction Thresholds | Accordion | Strong/steady/neutral/weak/depreciating slope cutoffs |
| Volatility | Accordion | Lookback period, low/high vol cutoffs |
| Lens Signal Thresholds | Accordion | Stock/sector concentration %, steep downtrend %, high beta, vol %, dead weight %, loss alert %, winner drift multiple. Shows active risk tier note. |
| Monte Carlo | Accordion | Projection period combo, simulation count combo |
| Positions | Static card | Add/remove positions |
| About | Static card | Version, brand, credits |

**Export Positions to CSV:** `SettingsPage._export_to_csv()` opens a `QFileDialog.getSaveFileName` and writes 11 columns: `ticker, name, sector, shares, entry_price, current_price, cost_basis, current_value, unrealized_pnl_dollar, unrealized_pnl_pct, added_at`.

**Accordion fix**: `_AccordionSection._measure()` always remeasures (no cache), forces `layout().activate()` before `sizeHint()`, and calls `parent.adjustSize()` in `_on_finished()` so the scroll area recomputes its range when multiple accordions are open simultaneously.

**LoadingButton gradient**: `LoadingButton.start_loading()` sets `setProperty('loading', True)` + `style().unpolish/polish()` before `setEnabled(False)`. The CSS rule `QPushButton[accent='true'][loading='true']:disabled` in both stylesheets preserves the gradient during loading state.

### Onboarding (`pages/onboarding.py`)

Keyboard shortcuts (widget-scoped with `WidgetWithChildrenShortcut`):
- **A** — opens Add Position dialog
- **Space** — advances to the next step via `_on_next()`. Guarded: if focus is a `QLineEdit`, space types a space character instead of triggering navigation. Shortcut is not exposed in any button label.

**Horizontal position list:** `cards_scroll` has a custom `wheelEvent` that maps vertical wheel delta to its horizontal scrollbar (~80 px per 120-unit notch) so users can scroll the card list with a normal mouse wheel.

**Risk tier selection:** After adding positions, a "How do you want to invest?" card presents three clickable options — Conservative (`low`), Moderate (`regular`, default), Aggressive (`high`). The selection is saved to `settings.json` → `risk_tier` and `app_state.json` → `risk_tier_selected` on launch. Existing users who completed onboarding before this step silently default to `"regular"` — no re-onboarding.

### DataStore (`store.py`)

`DataStore` is the authoritative data layer — use it for all reads and writes, not `StorageManager` or `MarketDataService`.

**Market data TTLs (stored in `market_data.json`):**

| Data | TTL |
|---|---|
| Quote / intraday history | Matches `refresh_interval` setting |
| 1mo+ daily history | 60 min |
| Meta (name, sector, industry…) | 24 h |
| Dividends | 24 h |
| Earnings calendar | 24 h |

**Key methods:**

- `validate_ticker(ticker)` — live fetch, no cache; used during onboarding
- `get_snapshot(ticker, refresh_interval)` → `{ticker, price, sector, name}`
- `get_history(ticker, period, refresh_interval)` → `list[float]` (close prices)
- `get_ohlcv(ticker, period, refresh_interval)` → `{dates, opens, highs, lows, closes, volumes}`
- `get_dividends(ticker)` → `list[{date, amount}]`
- `get_earnings(ticker)` → `list[{date, eps_estimate_avg, …}]`
- `get_quote(ticker)` / `get_meta(ticker)` — cached accessors (no network call)
- `build_histories(tickers, refresh_interval, lookback)` → history map for analytics
- `build_history_map(tickers, periods, refresh_interval)` → general-purpose close map
- `load_layout()` / `save_layout(layout)` — dashboard widget layout
- `clear_market_cache()` / `reset_all_data()` — wipe helpers

### Storage Layout

All files live under `%LOCALAPPDATA%/Protonyx/Vector/` (Windows) or `~/Vector/data/` (fallback):

| File | Contents |
|---|---|
| `positions.json` | List of position objects: `ticker`, `shares`, `equity`, `sector`, `name`, `price`, `added_at` |
| `settings.json` | Theme, currency, date_format, refresh_interval, risk_tier, direction_thresholds, volatility, lens_signals, monte_carlo |
| `app_state.json` | `onboarding_complete`, `first_launch_date`, `risk_tier_selected` |
| `market_data.json` | Per-ticker: quote, meta, history, history_ohlcv, history_intraday, dividends, earnings — with UTC timestamps |
| `dashboard_layout.json` | Ordered list of `{class_name, row, col, rowspan, colspan}` for the dashboard grid |
| `lens_history.json` | `{"snapshots": [...]}` — rolling 50-entry log of Lens snapshots (dedup'd against last entry) |

### Qt Stylesheet Rules (to avoid parse errors)

Qt supports a limited CSS subset. When writing `setStyleSheet(...)`:
- **Always wrap rules in a class selector** (`QFrame { … }`, `QLabel { … }`) for robust parsing.
- **Supported:** `background`, `background-color`, `color`, `border`, `border-left`, `border-top`, `border-radius`, `font-size`, `font-weight`, `padding`, `padding-left/right/top/bottom`. Use `padding` only on buttons/edits where Qt's box model is known to work; otherwise prefer `setContentsMargins`.
- **Not supported (will cause parse errors):** `gap`, `calc()`, `var()`, `box-shadow` (use `QGraphicsDropShadowEffect`), `transform`, `transition`, `display: flex`, `filter`, `backdrop-filter`, `::before`, `::after`, nested/SCSS selectors.
- Prefer `setContentsMargins()` + layout spacing over stylesheet padding/margin for internal widget layout — it's more predictable across Qt versions.

### Assets

All assets live in `assets/` and are loaded via `resource_path()`:

| File | Purpose |
|---|---|
| `assets/vector_full.png` | Full logo used in the UI |
| `assets/vector.ico` | Taskbar / window icon |
| `assets/splashboard.png` | Splash screen image (1400×800 source, displayed at 700×400) |

`resource_path()` in `vector/paths.py` handles three environments:
- **Dev**: resolves relative to the repo root (`Path(__file__).parent.parent`)
- **PyInstaller**: resolves from `sys._MEIPASS`
- **Nuitka standalone**: resolves from `Path(sys.executable).parent` (detected via `sys.frozen`)

The app falls back to a procedurally generated placeholder logo if `vector_full.png` or `vector.ico` are missing. The splash screen is silently skipped if `splashboard.png` is missing.
