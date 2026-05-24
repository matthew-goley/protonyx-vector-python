# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Keeping This File Current (read first)

**Whenever you add or materially change something important — a new module, a new page/widget, a new dependency, a startup-sequence change, a new storage file, a non-obvious invariant, or anything else a future contributor would need to know — update this CLAUDE.md in the same change.** Treat the documentation as part of the work, not an afterthought. If you introduce a file that isn't in the Module Responsibilities table, add a row. If you change a documented behaviour, fix the description. Out-of-date guidance here is worse than none.

## Project Overview

**Vector** is a PyQt6 desktop portfolio analytics app for stock investors. It tracks positions, fetches market data via Yahoo Finance (yfinance), and displays analytics (trend direction, volatility, sector allocation, Sharpe ratio, beta, dividends) in a customisable dark/light themed dashboard. Data is persisted locally in `%LOCALAPPDATA%/Protonyx/Vector/` (falls back to `~/Vector/data/`) as JSON files.

Current version: **0.4.6**

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
  --output-filename="Vector-v0.4.6.exe" ^
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
| `main.py` | Bootstrapper — creates `QApplication`, runs the auth gate, paints the splash, then imports `vector.app` and calls `main(app, splash, t_start, token, user_data)`. See **Startup & Splash Screen**. |
| `auth/auth.py` | REST client for the backend (Fastify API at `API_URL = http://localhost:3000`): `login`, `signup`, `get_me`, `save_token`/`load_token`/`clear_token`. Token persisted to `auth/session.json`. |
| `auth/login_window.py` | `LoginWindow` `QDialog` (Login / Sign Up tabs) shown when no valid saved token exists. Background `QThread` workers call the auth functions; emits `login_successful(token, user_data)`. |
| `vector/app.py` | Thin shell: `DARK_STYLESHEET`, `LIGHT_STYLESHEET`, `MainShell`, `VectorMainWindow`, `_ShortcutsDialog`, `main()` — all page classes live in `vector/pages/` |
| `vector/scale.py` | **Width-driven UI scaling** (see **UI Scaling** below). `init_scale(app)` sets a single global factor = `available_screen_width / UI_BASE_WIDTH` (clamped to `[UI_SCALE_MIN, UI_SCALE_MAX]`), or a fixed `DEBUG_SCREEN_SCALE` override. Helpers: `sc(px)` scales a pixel dimension (int), `scf(px)` returns a float, `scpt(pt)` scales a font point size (floored at `UI_MIN_POINT_SIZE`), `scale_factor()` returns the raw factor. Used **app-wide** — every page, widget, dialog, and the shell chrome routes its sizes/fonts through these. |
| `vector/notifications.py` | `NotificationManager` + `NotificationToast` — top-right slide-in toast stack. `window.notifications` is the live instance; repositioned on window resize. |
| `vector/version_check.py` | `check_version(parent, token)` — background `QThread` that GETs `http://localhost:3000/version`; if the latest differs from `APP_VERSION`, shows an "out of date" toast. Never crashes the app on failure. |
| `vector/yfinance_counter.py` | `yf_count()` / `get_count()` — running tally of yfinance API calls, rendered in-place to stderr only when it's a TTY (silent in release builds). |
| `vector/pages/dashboard.py` | `DashboardPage`, `DashboardGrid`, `WidgetPickerDialog`, grid constants (`_UNIT`, `_GAP`, `_CELL`, `_CONTENT_W`) |
| `vector/pages/lens_page.py` | `VectorLensPage`, `_GraphCard`, `_PieCard`, `_CTAReportCard`, `_CautionCard`, `_MCContextCard`, `_LensHistoryDialog`, `_LensHistoryCard`, `_CautionBadge` |
| `vector/pages/onboarding.py` | `OnboardingPage`, `PositionDialog`, `EditPositionDialog` (edit an existing holding's share count — also used by Settings), `PositionCard`, `_RiskTierCard` |
| `vector/pages/profile.py` | `ProfilePage` — renders the authenticated account (username, email, plan, member-since, beta, downloads) from `window.user_data`; has a Logout button (clears `session.json`, returns to login). |
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
| `vector/lens/_templates.py` | Loads `sentences.json` via `resource_path()` with a package-local fallback, so templates resolve in dev, PyInstaller, and Nuitka builds. |
| `vector/lens/debug_runner.py` | Synthetic-portfolio harness for exercising the Lens engine offline. Passes `save_history=False` so test runs do not pollute `lens_history.json`. |
| `vector/monte_carlo.py` | `run_projection()`, `build_historical_curve()` — GBM Monte Carlo simulation |
| `vector/widget_base.py` | `VectorWidget` — base `QFrame` for all dashboard widgets; handles edit-mode drag, context menu |
| `vector/widget_registry.py` | `discover_widgets()` / `get_widget_class()` — registry of all concrete widget types |
| `vector/widget_types/` | 8 concrete widget implementations + `LensDisplay` |
| `vector/widgets.py` | Shared UI primitives: `CardFrame`, `GradientBorderFrame`, `GradientLine`, `BlurrableStack`, `DimOverlay`, `EmptyState`, `LoadingButton`, `OutlineButton` (transparent fill + custom-painted rounded border; `gradient=True` for the Vector brand outline or a solid `color`) |
| `vector/constants.py` | File paths, TTL constants, default settings values, threshold maps, `APP_VERSION` |
| `vector/paths.py` | `resource_path()` (PyInstaller + Nuitka-aware asset lookup), `user_data_dir()`, `user_file()` |

### Pages subpackage (`vector/pages/`)

All page-level QWidget classes live here. `vector/app.py` imports from this subpackage — do not put new page classes directly in `app.py`.

- `_CONTENT_W()` is a **function** in `pages/dashboard.py` (base 1090 px → `sc(1090)`) imported by `pages/lens_page.py`, `pages/settings.py`, and `pages/onboarding.py` (`_PANEL_W()` mirrors the pattern). It is a function, not a constant, so it is evaluated *after* `init_scale()` runs. Call it: `_CONTENT_W()`.
- All three scrollable pages (Dashboard, Lens, Settings) use `setWidgetResizable(False)`/fixed-width `container.setFixedWidth(_CONTENT_W())` so content width is stable on window resize and the scrollbar sits at the window edge. Because `_CONTENT_W()` tracks the UI scale, the content fills the window at any resolution instead of leaving a blank band on the right.

### UI Scaling (read before touching any size or font)

The entire UI scales by **one global, width-driven factor** so it fits the screen at any resolution. `vector/scale.py` computes `scale = available_screen_width / UI_BASE_WIDTH` (constants in `constants.py`: `UI_BASE_WIDTH=1422`, clamped `[0.70, 3.00]`; `UI_MIN_POINT_SIZE=7`). On a 1080p panel at 150% Windows scaling (logical viewport ~1280 px) this lands at **~0.9** (the verified "perfect fit"); on a logical-1920 viewport it is ~1.35; on 4K@100% (logical 3840) ~2.7. `DEBUG_SCREEN_SCALE` in `constants.py` forces a fixed factor for testing. Lower `UI_BASE_WIDTH` ⇒ larger UI; it is the single calibration knob.

**The invariant:** every pixel dimension goes through `sc(...)` and every font point size through `scpt(...)`. This keeps the cell-to-content ratio **constant across resolutions** — which is what prevents text clipping. (The old system scaled only the dashboard grid by `devicePixelRatio` while fonts stayed fixed, so cells grew on 4K but text didn't, fitting on 4K yet clipping at base scale. Don't reintroduce a raw-pixel size or a bare `Npt` font on a visible widget — it will clip at small scales and look tiny at large ones.)

Rules when adding/editing GUI:
- Sizes: `setFixedWidth(sc(220))`, `setContentsMargins(sc(16), sc(12), …)`, `setSpacing(sc(8))`, `setMinimumHeight(sc(200))`, painter geometry via `scf(...)`.
- Fonts: `setPointSize(scpt(16))` **and** stylesheet `f'font-size: {scpt(16)}pt;'` (set both when both are present, as the existing widgets do). Inline-HTML/`px` font sizes scale too: `f'font-size: {sc(13)}px;'`.
- The global `DARK/LIGHT_STYLESHEET` base `font-size: 13px` is scaled at apply time in `VectorMainWindow.apply_theme()` via a `.replace(...)`; structural px in those sheets (border-radius, padding) are intentionally left unscaled (low impact).
- The window minimum (`sc(1360) × sc(860)`) is **clamped to the available screen** in `VectorMainWindow.__init__` so large scales never demand a window taller/wider than the monitor.
- `LensDisplay._fit_pt` and `_MCContextCard._fit_pt` auto-fit the brief text to the available box (search bounds are `scpt(...)`-scaled); leave that self-fitting logic in place.
- Module-level geometry that other code reads (e.g. `_CONTENT_W`, `_PANEL_W`) must be a **function** returning `sc(...)`, never a module constant (the scale isn't known at import time).
- Not yet scaled (acceptable, low-impact follow-ups): `notifications.py` toast geometry, the onboarding `_*_BTN_QSS` module-constant button stylesheets, and a few painter-internal arrow/gauge constants that are already proportional to their (scaled) widget.

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

### Authentication

Vector is gated behind a login. `auth/auth.py` talks to a backend REST API (Fastify) at `API_URL = http://localhost:3000` — swapping deployments only requires changing that constant. The token is saved to `auth/session.json` next to the module.

- On launch `main.py` calls `_run_auth_gate()`: tries `load_token()` → `get_me(token)`; on success it proceeds, otherwise it shows `LoginWindow` (Login / Sign Up tabs). If the user closes the dialog without authenticating, the process exits cleanly (status 0).
- The resolved `(token, user_data)` is threaded into `VectorMainWindow`; `ProfilePage` displays it (username, email, plan, member-since, beta flag, downloads) and offers **Logout** (clears the session and returns to login).
- `version_check.check_version()` reuses the same backend host for the update check.

### Startup & Splash Screen

`main.py` is the bootstrapper; `vector.app.main()` finishes the sequence. The auth gate runs **before** the splash, and heavy imports (`vector.app`, yfinance, numpy, all pages/widgets) happen **after** the splash is already painted:

1. `main.py:_create_app()` creates the `QApplication` using only PyQt6 (fast — the `vector` package is not imported yet).
2. `main.py:_run_auth_gate(app)` resolves `(token, user_data)` — saved session or `LoginWindow`. Exits if the user cancels.
3. `main.py:_show_splash(app)` loads `assets/splashboard.png` and displays it as an always-on-top `QSplashScreen`, then calls `app.processEvents()` to force the OS to paint it before any heavy work. The splash is **responsive-sized**, not fixed: width = `min(screen_width × 0.55, 900)`, height keeps the source 1400:800 ratio, centred on the primary screen.
4. `from vector.app import main` (the heavy import chain runs here, splash already visible), then `main(app, splash, t_start, token=…, user_data=…)`.
5. `init_scale(app)` initialises the global width-driven UI scale factor (see **UI Scaling**), then the taskbar icon is set.
6. `VectorMainWindow(token, user_data)` is constructed (loads data, builds UI). A daemon thread prefetches prices for `COMMON_TICKERS` so Add Position shows instant estimates.
7. The splash is shown for a **minimum of 2 seconds** total (measured from `t_start`); a `QTimer` waits out any remainder, then `window.show()` + `splash.finish(window)`.

`vector.app.main()` also has a self-contained fallback (auth gate + splash) for when it's invoked directly without going through `main.py` (e.g. during development).

### Data Flow

1. `VectorMainWindow` owns `DataStore`, all settings/state, the auth `token`/`user_data`, a `NotificationManager` (`self.notifications`), and the `QTimer` for auto-refresh. ~1.5 s after launch it kicks off `check_version()` (background thread → update toast if out of date).
2. On startup: load JSON state → show `OnboardingPage` (first run) or `MainShell` (returning).
3. `MainShell` hosts an `sc(220)` px sidebar + `QStackedWidget` with `DashboardPage`, `VectorLensPage`, `ProfilePage`, `SettingsPage` (all base sizes scaled — see **UI Scaling**). Header contains a "?" icon button (`sc(48)`², rounded) that opens the keyboard-shortcuts modal. On window resize, `self.notifications.reposition_all()` keeps the toast stack pinned to the top-right.
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
| **?** / **Shift+/** | Open Keyboard Shortcuts modal (`_ShortcutsDialog`) — both sequences are registered |
| **Esc** | Close any open modal |
| **Space** | Advance to next onboarding step (widget-scoped on `OnboardingPage`; ignored if focus is a `QLineEdit`) |

The "?" button in the MainShell header also opens the shortcuts modal. Button is `sc(48)`² with radius `sc(24)` and `padding: 0`, glyph at `scpt(16)` — its size/glyph scale together, so do not hardcode it back to raw pixels (a raw 48 px box with scaled text clips the glyph at large scales).

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

### Swapping in an updated Lens engine from `lens_standalone/`

`lens_standalone/lens/` is a self-contained copy of the engine used for offline testing (`python -m lens_standalone`). When you've iterated on it and want to promote those changes back into the app, the process is:

1. **Copy `vector/lens/debug_runner.py` into `lens_standalone/lens/`** — it's the only file the standalone tree is missing. The app's Settings page imports it via `from vector.lens.debug_runner import run_debug_tests` (see `vector/pages/settings.py`), so without it the debug-tests button breaks. You can either:
   - Rewire its imports (`from vector.lens.lens_output` → `from .lens_output`, `from vector.paths` → `..paths`), or
   - Leave it untouched — after the move, `vector.lens.lens_output` resolves to the new code anyway.
2. **Replace `vector/lens/` with the contents of `lens_standalone/lens/`** (the `lens/` subfolder only — not `runner.py`, `data_shim.py`, `__main__.py`, `debug_test.json`, `constants.py`, `analytics.py`, or `paths.py` — those are standalone-only shims).
3. **No app code changes needed.** The standalone files use relative imports (`..constants`, `..analytics`, `..paths`) which resolve to `vector.constants` / `vector.analytics` / `vector.paths` once moved. All symbols Lens reads from those modules (`INDEX_ETFS`, `LOW_BETA_BY_SECTOR`, `SECTOR_SUGGESTIONS`, `DEFAULT_RISK_PROFILES`, `INDEX_FUND_TYPES`, `linear_regression_slope_percent`, `portfolio_daily_returns`, `portfolio_beta`, `resource_path`) already exist in the app.

Signature compatibility: `build_lens_output()` and `run_analysis()` in the standalone copy add an optional `progress_cb` kwarg (default `None`) used by the CLI runner — the app's existing call sites pass nothing and behave identically. The lazy `from vector.paths import user_file` inside `_save_snapshot()` is the intentional hook: it stays inert in standalone mode (which passes `save_history=False`) and works normally inside the app.

Behavioral diff to be aware of: two `print('[lens DEBUG] ...')` calls (winner-drift in `cta_engine.py`, weight-sum warning in `analysis_pool.py`) were converted to `_log.debug(...)` in the standalone copy, so stdout is quieter unless DEBUG logging is enabled. Engine output is unchanged.

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
      ├─ tag QLabel    (AlignBottom | AlignLeft, fixed height from its OWN scaled font)
      └─ text QLabel   (word-wrap, AlignTop | AlignLeft, Expanding × Minimum)
```

**Stylesheets must use class selectors** (`QFrame { … }` / `QLabel { … }`) to avoid Qt's "Could not parse stylesheet" warnings. Only supported properties: `background-color`, `border`, `border-left`, `border-radius`, `color`, `font-size`, `font-weight`, `background: transparent`. **No `padding` or `margin` in stylesheets** — use `setContentsMargins` in Python instead. No `box-shadow`, `calc()`, `gap`, `transform`, `::before/::after`.

**Why each piece matters:**
- The tag gets an explicit `QFont(pointSize=scpt(10), bold)` via `setFont` **before** measuring, because a stylesheet `font-size` does not update `QLabel.font()` — measuring the default font there clipped the BUY/SELL text's top at larger scales. Height is `fm.ascent() + fm.descent() + sc(3)` from that font (`AlignBottom` on tag + `AlignTop` on text keeps the gap to the description tight). Do not revert to `QFontMetrics(tag.font())` or `ascent()`-only.
- `text` is `scpt(15)` white (`#e7ebf3`); `tag` is `scpt(10)` in the action's color. All sizes/margins in this card are scaled — see **UI Scaling**.
- Trailing `addStretch(1)` in `_items_layout` absorbs any surplus space so individual cards are not stretched beyond their `sizeHint` (cards have `Minimum` vpolicy which CAN grow without the stretch).
- `addWidget(card, 0)` sets stretch factor 0 on each card so only the stretch grows.

**Measure-don't-guess sizing (`_resize_for_cards`):**
```python
MAX_HEIGHT = sc(750)   # scaled — see UI Scaling
PADDING = sc(24)
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
| Investment Style | Static card | Risk tier selection (Conservative/Moderate/Aggressive) — immediate save on click. **Pro-gated:** blurred + "Get Vector Professional" lock overlay on free accounts (see below). |
| Data & Refresh | Accordion | Auto-refresh interval, clear cache, reset all data, **Export Positions to CSV** |
| Portfolio Direction Thresholds | Accordion | Strong/steady/neutral/weak/depreciating slope cutoffs |
| Volatility | Accordion | Lookback period, low/high vol cutoffs |
| Lens Signal Thresholds | Accordion | Stock/sector concentration %, steep downtrend %, high beta, vol %, dead weight %, loss alert %, winner drift multiple. Shows active risk tier note. |
| Monte Carlo | Accordion | Projection period combo, simulation count combo |
| Positions | Static card | Holdings list, then three buttons below it (in order): **Add New Position** (`OutlineButton`, Vector gradient outline), **Remove Selected Position** (`OutlineButton`, red outline), **Edit Selected Holding** (plain `LoadingButton`). Edit opens `EditPositionDialog` for the selected ticker. |
| About | Static card | Version, brand, credits |

**Export Positions to CSV:** `SettingsPage._export_to_csv()` opens a `QFileDialog.getSaveFileName` and writes 11 columns: `ticker, name, sector, shares, entry_price, current_price, cost_basis, current_value, unrealized_pnl_dollar, unrealized_pnl_pct, added_at`.

**Investment Style pro-gate:** `SettingsPage.apply_risk_gate(gated)` mirrors `DashboardPage.apply_lens_gate` exactly — the Investment Style card is wrapped in a `QStackedLayout` (`StackAll`); on free accounts it applies `QGraphicsBlurEffect(radius=50)` to the card's child widgets and shows a `StackAll` "🔒 Get Vector Professional" `QLabel` overlay on top (which also blocks clicks). The plan is read via `SettingsPage._is_gated()` (same `user_data['user']['plan'] != 'pro'` check as `MainShell._is_gated`, defaulting to gated if `user_data` is absent). Called once during `_build_ui`.

**Edit a holding:** `SettingsPage.edit_selected_position()` reads the selected `remove_list` item, finds the matching position, and opens `EditPositionDialog` (asks "How many total shares of `<ticker>` do you own?", prefilled with the current count, live equity preview). On save it updates `position['shares']` and calls `refresh_data()`, which recomputes `equity = shares × current_price` for every position. Add and remove keep their existing handlers (`window.add_position_from_settings`, `remove_selected_position`).

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
