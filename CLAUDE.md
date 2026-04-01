# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Vector** is a PyQt6 desktop portfolio analytics app for stock investors. It tracks positions, fetches market data via Yahoo Finance (yfinance), and displays analytics (trend direction, volatility, sector allocation, Sharpe ratio, beta, dividends) in a customisable dark/light themed dashboard. Data is persisted locally in `%LOCALAPPDATA%/Protonyx/Vector/` (falls back to `~/Vector/data/`) as JSON files.

Current version: **0.3.8**

## Setup & Running

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

No build step, test suite, or linter is configured.

## Building (Nuitka)

```bash
python -m nuitka --standalone --windows-console-mode=disable --enable-plugin=pyqt6 --output-filename="Vector-v0.3.8.exe" --include-data-dir=assets=assets main.py
```

- `--include-data-dir=assets=assets` copies the entire `assets/` folder next to the exe
- `resource_path()` automatically resolves assets correctly in all three environments: dev, PyInstaller, and Nuitka standalone (see `vector/paths.py`)

## Architecture

### Module Responsibilities

| Module | Role |
|---|---|
| `main.py` | Entry point — calls `vector.app.main()` |
| `vector/app.py` | Thin shell: `DARK_STYLESHEET`, `LIGHT_STYLESHEET`, `MainShell`, `VectorMainWindow`, `main()` — all page classes live in `vector/pages/` |
| `vector/pages/dashboard.py` | `DashboardPage`, `DashboardGrid`, `WidgetPickerDialog`, grid constants (`_UNIT`, `_GAP`, `_CELL`, `_CONTENT_W`) |
| `vector/pages/lens_page.py` | `VectorLensPage`, `_GraphCard` (Monte Carlo), `_PieCard` (diversification pie), `_CTAReportCard` (full CTA list), `_CautionCard`, `_MCContextCard` |
| `vector/pages/onboarding.py` | `OnboardingPage`, `PositionDialog`, `PositionCard` |
| `vector/pages/profile.py` | `ProfilePage` |
| `vector/pages/settings.py` | `SettingsPage`, `_AccordionSection`, `_AnimatedChevron`, `QDoubleSpinBoxCompat` |
| `vector/analytics.py` | Portfolio math: trend slope, volatility, Sharpe ratio, beta, insight HTML generation |
| `vector/store.py` | `DataStore` — single source of truth: positions, settings, app state, market data, layout; replaces `storage.py` |
| `vector/market.py` | Legacy `MarketDataService`; superseded by `DataStore` but may still be referenced |
| `vector/storage.py` | Legacy `StorageManager`; superseded by `DataStore` |
| `vector/lens_engine.py` | Thin wrapper: `generate_lens()` returns 7-tuple, `generate_lens_full()` returns complete result dict |
| `vector/lens_templates.py` | Legacy stub (empty) — templates now in `vector/lens/templates/sentences.json` |
| `vector/lens/` | **Lens engine package** — modular analysis, CTA generation, sentence composition |
| `vector/lens/lens_output.py` | Top-level assembler: orchestrates pool → CTAs → sentences → result dict |
| `vector/lens/analysis_pool.py` | Runs all 8 analyzers, caches results, handles dependencies and post-processing |
| `vector/lens/cta_engine.py` | Generates prioritized CTAs with dollar amounts from analyzer results |
| `vector/lens/risk_profile.py` | Loads user risk tier (`high`/`regular`/`low`), returns threshold overrides |
| `vector/lens/sentence1.py` | Portfolio state composer (slope + volatility → one sentence) |
| `vector/lens/sentence2.py` | Timing/catalyst composer (earnings + dividends → one sentence) |
| `vector/lens/sentence3.py` | CTA composer (top-priority action → one sentence) |
| `vector/lens/analyzers/slope.py` | Per-ticker and portfolio slope (direction) analysis |
| `vector/lens/analyzers/volatility.py` | Per-ticker and portfolio volatility analysis |
| `vector/lens/analyzers/concentration.py` | Stock weight, sector weight, winner drift detection |
| `vector/lens/analyzers/earnings.py` | Upcoming earnings dates + EPS estimates + outlook |
| `vector/lens/analyzers/dividends.py` | Upcoming ex-dividend dates + trailing yield |
| `vector/lens/analyzers/beta.py` | Per-ticker and portfolio beta vs SPY |
| `vector/lens/analyzers/performance.py` | Unrealized P&L from cost basis |
| `vector/lens/analyzers/index_fund.py` | Index ETF detection and classification |
| `vector/lens/templates/sentences.json` | All sentence templates (5+ variations per category) |
| `vector/monte_carlo.py` | `run_projection()`, `build_historical_curve()` — GBM Monte Carlo simulation |
| `vector/widget_base.py` | `VectorWidget` — base `QFrame` for all dashboard widgets; handles edit-mode drag, context menu |
| `vector/widget_registry.py` | `discover_widgets()` / `get_widget_class()` — registry of all concrete widget types |
| `vector/widget_types/` | 8 concrete widget implementations + `LensDisplay` (see below) |
| `vector/widgets.py` | Shared UI primitives: `CardFrame`, `GradientBorderFrame`, `GradientLine`, `BlurrableStack`, `DimOverlay`, `EmptyState`, `LoadingButton` |
| `vector/constants.py` | File paths, TTL constants, default settings values, threshold maps |
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
| `SharpeRatioWidget` | Annualised Sharpe ratio |
| `PositionsListWidget` | Scrollable positions table |
| `DividendCalendarWidget` | Upcoming dividend dates |

### Vector Lens (`vector/widget_types/lens.py`)

`LensDisplay` is a reusable QFrame (not a VectorWidget) that renders the "Lens Brief" readout with typewriter animation and gradient-highlighted text. It is a **permanent fixture** on the dashboard (cannot be removed or repositioned) and also appears on the dedicated Vector Lens page. The dashboard instance includes a "Vector Lens ›" button that navigates to the full Lens page.

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
5. The splash is shown for a **minimum of 2 seconds** total. If construction finishes in under 2 s, a `QTimer` waits out the remainder. If it takes longer, the splash closes immediately after.
6. `splash.finish(window)` closes the splash and `window.show()` reveals the main window.

### Data Flow

1. `VectorMainWindow` owns `DataStore`, all settings/state, and the `QTimer` for auto-refresh.
2. On startup: load JSON state → show `OnboardingPage` (first run) or `MainShell` (returning).
3. `MainShell` hosts a sidebar + `QStackedWidget` with `DashboardPage`, `VectorLensPage`, `ProfilePage`, `SettingsPage`.
4. `DashboardPage` has a permanent `LensDisplay` at the top, followed by a free-form grid of `VectorWidget` instances; grid layout is loaded from / saved to `dashboard_layout.json`.
5. `DashboardPage.update_dashboard()` calls `compute_portfolio_analytics()` → refreshes the lens and calls `widget.refresh()` on each placed widget.
6. Edit mode (toolbar button) enables drag-to-reposition and right-click delete on grid widgets (the lens is not affected).
7. A `QTimer` drives auto-refresh at the interval set in `SettingsPage` (1 min / 5 min / 15 min / manual).

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
4. `cta_engine.py` reads analyzer results and generates prioritized CTAs with dollar amounts
5. `sentence1.py` composes a portfolio state sentence from slope + volatility data
6. `sentence2.py` composes a timing/catalyst sentence from earnings + dividends data
7. `sentence3.py` composes a CTA sentence from the highest-priority action
8. `lens_output.py` joins the 3 sentences, computes caution score, applies all CTAs to build `projected_positions`, and returns the full result dict

**Analyzer interface:** Every analyzer exposes `analyze(positions, store, settings, risk_profile) → dict` with `ticker_results` (per-ticker) and `portfolio_result` (aggregate). Each result has `value`, `severity` (`none`/`low`/`moderate`/`high`/`critical`), `flag` (bool), `weight`, and `details`.

**CTA priorities (11 levels, 1 = highest):**
1. Steep decline (sell)
2. Excessive volatility (sell)
3. Winner drift (rebalance)
4. Index fund informational (hold)
5. High portfolio beta (buy)
6. Single-stock concentration (buy)
7. Sector over-concentration (buy)
8. Dead weight (sell)
9. Underrepresented sector (buy)
10. Unrealized loss (hold)
11. Portfolio healthy (hold)

**Risk profiles:** Three tiers (`high`/`regular`/`low`) with different severity thresholds per analyzer. Stored in `constants.py` as `DEFAULT_RISK_PROFILES`. User overrides from `settings.json` → `lens_signals` take precedence. Risk tier stored in `settings.json` → `risk_tier` (default `"regular"`).

**Sentence templates:** All templates live in `vector/lens/templates/sentences.json`, organized by sentence type → signal category → severity. Each leaf has 5+ variations. Selection is deterministic (SHA-256 hash of portfolio state). All language is observational — no directives.

**Color mapping:** Action type → hex color: `sell` → `#ff4d4d`, `rebalance` → `#ff9f43`, `buy_new`/`buy_more` → `#4da6ff`, `hold` → `#8d98af`.

**Caution score:** 1–99, computed as `total CTA dollars / total equity × 100` (clamped). Represents what fraction of the portfolio the engine suggests moving.

**Projected positions:** `_apply_all_ctas()` in `lens_output.py` applies every CTA to a deep copy of positions:
- `sell`/`rebalance`: reduces position value (removes if fully sold)
- `buy_more`: increases existing position value
- `buy_new`: adds a new position (fetches sector/name from store)
- `hold`: no change
Returns `projected_positions` (list) and `net_cta_delta` (net cash flow: buys minus sells).

`LensDisplay.refresh()` in `widget_types/lens.py` handles all tuple lengths (7, 6, 5, 4, 3, 2) for backwards compatibility.

### Monte Carlo (Lens page)

`_GraphCard` in `pages/lens_page.py` renders GBM projections. Key notes:
- Graph A ("Current Portfolio"): projects the portfolio as-is using current positions.
- Graph B ("With All Lens Recommendations"): uses `projected_positions` (all CTAs applied) for Monte Carlo simulation. Title shows sell/buy totals: "With All Lens Recommendations — -$X  +$Y".
- Both graphs pass `total_equity` as `current_value` to `run_projection` so historical curves normalise to the same base.
- Projections display percentage change relative to current equity, not raw dollar values.
- matplotlib `FigureCanvasQTAgg` captures wheel events — fixed with `self._canvas.wheelEvent = lambda event: event.ignore()` so scrolling works when the mouse is over a chart.
- Monte Carlo parameters (projection period, simulation count) are configurable via Settings → Monte Carlo and stored under `monte_carlo` in `settings.json`. Mapping constants: `MONTE_CARLO_HORIZON_DAYS`, `MONTE_CARLO_SIMULATIONS` in `constants.py`.
- Between the projection graphs and the pie charts, two insight cards are rendered side-by-side: `_CautionCard` (left, 1:2 ratio) shows a semi-circular arc gauge with the portfolio caution score (1–99); `_MCContextCard` (right) shows a multi-CTA context description (sell total, buy total, net delta). Both are populated in `VectorLensPage._update_insights()`.
- Below the pie charts, `_CTAReportCard` displays all CTA recommendations with colored action-type indicators (red=sell, blue=buy, orange=rebalance, grey=hold) and dollar amounts.
- Pie A ("Current Allocation"): sector grouping from current positions. Pie B ("Projected Allocation"): sector grouping from `projected_positions`.

### Settings Page (`pages/settings.py`)

Six accordion sections plus two static sections:

| Section | Type | Contents |
|---|---|---|
| General | Static card | Theme, currency, date format |
| Data & Refresh | Accordion | Auto-refresh interval, clear cache, reset all data |
| Portfolio Direction Thresholds | Accordion | Strong/steady/neutral/weak/depreciating slope cutoffs |
| Volatility | Accordion | Lookback period, low/high vol cutoffs |
| Lens Signal Thresholds | Accordion | Stock/sector concentration %, steep downtrend %, high beta threshold, vol threshold % |
| Monte Carlo | Accordion | Projection period combo, simulation count combo |
| Positions | Static card | Add/remove positions |
| About | Static card | Version, brand, credits |

**Accordion fix**: `_AccordionSection._measure()` always remeasures (no cache), forces `layout().activate()` before `sizeHint()`, and calls `parent.adjustSize()` in `_on_finished()` so the scroll area recomputes its range when multiple accordions are open simultaneously.

**LoadingButton gradient**: `LoadingButton.start_loading()` sets `setProperty('loading', True)` + `style().unpolish/polish()` before `setEnabled(False)`. The CSS rule `QPushButton[accent='true'][loading='true']:disabled` in both stylesheets preserves the gradient during loading state.

### Onboarding (`pages/onboarding.py`)

`OnboardingPage` keyboard shortcut: pressing **A** opens the Add Position dialog (calls `open_add_modal()`).

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
| `settings.json` | Theme, currency, date_format, refresh_interval, direction_thresholds, volatility, lens_signals, monte_carlo |
| `app_state.json` | `onboarding_complete`, `first_launch_date` |
| `market_data.json` | Per-ticker: quote, meta, history, history_ohlcv, history_intraday, dividends, earnings — with UTC timestamps |
| `dashboard_layout.json` | Ordered list of `{class_name, row, col, rowspan, colspan}` for the dashboard grid |
| `price_cache.json` | Legacy cache — superseded by `market_data.json`; kept for backwards compat |

### Assets

All assets live in `assets/` and are loaded via `resource_path()`:

| File | Purpose |
|---|---|
| `assets/vector_full.png` | Full logo used in the UI |
| `assets/vector_taskbar.png` | Taskbar / window icon |
| `assets/splashboard.png` | Splash screen image (1400×800 source, displayed at 700×400) |

`resource_path()` in `vector/paths.py` handles three environments:
- **Dev**: resolves relative to the repo root (`Path(__file__).parent.parent`)
- **PyInstaller**: resolves from `sys._MEIPASS`
- **Nuitka standalone**: resolves from `Path(sys.executable).parent` (detected via `sys.frozen`)

The app falls back to a procedurally generated placeholder logo if `vector_full.png` or `vector_taskbar.png` are missing. The splash screen is silently skipped if `splashboard.png` is missing (pixmap will be null).
