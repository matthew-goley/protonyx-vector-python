# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Keeping This File Current (read first)

**Whenever you add or materially change something important — a new module, a new page/widget, a new dependency, a startup-sequence change, a new storage file, a non-obvious invariant, or anything else a future contributor would need to know — update this CLAUDE.md in the same change.** Treat the documentation as part of the work, not an afterthought. If you introduce a file that isn't in the Module Responsibilities table, add a row. If you change a documented behaviour, fix the description. Out-of-date guidance here is worse than none.

## Project Overview

**Vector** is a PyQt6 desktop portfolio analytics app for stock investors. It tracks positions, fetches market data via Yahoo Finance (yfinance), and displays analytics (trend direction, volatility, sector allocation, Sharpe ratio, beta, dividends) in a customisable dark/light themed dashboard. Data is persisted locally in `%LOCALAPPDATA%/Protonyx/Vector/` (falls back to `~/Vector/data/`) as JSON files.

Current version: **0.4.8**

## Debug / Development Helpers

### Demo Login Bypass (`auth/login_window.py`)

A temporary backend bypass lives at the **top of `auth/login_window.py`** (clearly marked with `# DEMO BYPASS` / `# END DEMO BYPASS` comments). When `_DEMO_BYPASS_ENABLED = True`, typing `demo` as the username and clicking Login (any password, including blank) skips the Fastify backend entirely and signs in as a local Pro demo account. No token is saved to disk.

**To remove before shipping:** delete the two `# DEMO BYPASS` blocks — the module-level constants block (`_DEMO_BYPASS_ENABLED`, `_DEMO_BYPASS_TRIGGER`, `_DEMO_TOKEN`, `_DEMO_USER_DATA`) and the 3-line guard inside `_on_login_clicked`. The surrounding code is untouched and will work normally.

**To disable without deleting:** set `_DEMO_BYPASS_ENABLED = False`.

---

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
  --output-filename="Vector-v0.4.8.exe" ^
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
| `auth/auth.py` | REST client for the backend (Fastify API at `API_URL = http://localhost:3000`): `login`, `signup`, `get_me`, `save_token`/`load_token`/`clear_token`, plus the legal-gate calls `check_eula_status` (GET `/legal/status`, returns both `tos_accepted`/`eula_accepted`) and `accept_legal_document(token, document)` (POST `/legal/accept`) with thin `accept_eula`/`accept_tos` wrappers - all return `dict` or `None` on any failure, never raise - and the private `_legal_status_code` helper (GET `/legal/status`, returns the HTTP status code, used to classify a 401 vs a transient failure). Token persisted to `auth/session.json`. |
| `auth/login_window.py` | `LoginWindow` `QDialog` (Login / Sign Up tabs) shown when no valid saved token exists. Background `QThread` workers call the auth functions; emits `login_successful(token, user_data)`. |
| `vector/eula_gate.py` | `LegalGateOverlay` `QWidget` (+ `_AcceptWorker`) - parameterized full-window legal acceptance gate for TOS and EULA (`EulaGateOverlay` is a back-compat alias). See **Legal Acceptance Gate (TOS + EULA)**. |
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
| `vector/constants.py` | File paths, TTL constants, default settings values, threshold maps, `APP_VERSION`, `BASE_URL` (host for web redirects) + the derived `FORGOT_PASSWORD_URL`/`EULA_URL`/`TOS_URL` (each is `f'{BASE_URL}/<path>'`, so changing `BASE_URL` repoints all three). Also `TICKER_SECTOR` (static ticker→sector fallback) + `sector_for()` / `normalize_sector()` — see **Sector resolution**. |
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

### Legal Acceptance Gate (TOS + EULA)

Terms of Service and EULA acceptance are tracked **server side only** (no local JSON, no flag in `app_state.json`). The check runs once at launch and, if needed, blocks the app behind a full-window overlay until the user accepts. **Both documents share one parameterized overlay class** (`LegalGateOverlay`); when both are unaccepted they are shown **sequentially, TOS first then EULA, never both at once**.

- **Backend endpoints** (already exist, do not modify): `GET /legal/status` (authenticated) returns `{success, tos_accepted, eula_accepted, current_tos_version, current_eula_version}`; `POST /legal/accept` (authenticated) with body `{"document": "tos"}` or `{"document": "eula"}` records acceptance. Both live at the same `API_URL` as `auth/auth.py`.
- **Launch wiring:** `vector.app._maybe_show_legal_gates(window, token)` runs inside the splash `_finish()` callback, right after `window.showMaximized()` + `splash.finish(window)`. It calls `check_eula_status(token)` (one lightweight synchronous GET returning both flags) and:
  - **`None` (network/parse failure):** logs a warning via `_log` and does **not** block. **Fails open** by design.
  - **`tos_accepted is False`:** constructs the TOS gate; its accept callback (`on_accepted`) then shows the EULA gate **only if** `eula_accepted is False`. So both-unaccepted yields TOS then EULA; TOS-only shows just TOS.
  - **`tos_accepted` truthy but `eula_accepted is False`:** shows the EULA gate directly (unchanged prior behavior).
  - **both truthy:** does nothing, the app proceeds normally.
  - The live gate is stored on `window._legal_gate` (reassigned when the flow advances from TOS to EULA).
- **Demo bypass:** `_maybe_show_legal_gates` imports `_DEMO_BYPASS_ENABLED` / `_DEMO_TOKEN` from `auth/login_window.py`; when the bypass is active and `token == _DEMO_TOKEN`, the whole check is skipped (the demo session has no real backend token, so it would always fail).
- **`LegalGateOverlay` (`vector/eula_gate.py`):** a `QWidget` child of the main window, constructed as `LegalGateOverlay(parent, token, document_type='tos'|'eula', on_accepted=None)`. `EulaGateOverlay` is a module-level alias (defaults to `'eula'`). The per-document title/message/link-text/URL live in the `_LEGAL_DOCS` dict (`EULA_URL` / `TOS_URL`); everything else is identical for both. It:
  - On construction applies `QGraphicsBlurEffect(blurRadius=50)` to the parent's central widget (same pattern as the dashboard/settings pro-gate), then paints a semi-transparent dark backdrop and `grabKeyboard()`s so the blurred app cannot be reached (key events are swallowed in `keyPressEvent`, blocking the app-wide R/L/D/S shortcuts; backdrop clicks are consumed).
  - Centres a card (`#1e2030`, `sc(16)` radius, `sc(32)` padding, `sc(500)` max width) with the title, the explanatory message, a teal text link that opens the document URL via `QDesktopServices.openUrl`, an **I Accept** gradient (`accent`) button, and a **Decline** button.
  - **Always fills the parent:** an event filter on the parent re-fits geometry on every window resize (`resizeEvent` re-asserts the same, guarded against recursion).
  - **I Accept** disables the button, then runs `_AcceptWorker(token, document)` (a `QThread` mirroring the login workers) which calls `accept_legal_document(token, document)`. On `'ok'` it removes the blur, calls the optional `on_accepted` callback (this is how the TOS gate chains to the EULA gate), emits `accepted`, and deletes the overlay. On `'failed'` it shows an inline "Unable to connect..." error and re-enables the button to retry. On `'unauthorized'` (the worker classifies a failed accept by probing `_legal_status_code`; a follow-up 401 means the session died) it calls `clear_token()` and `QApplication.quit()` so the user re-logs-in next launch.
  - **Decline** tears down (releases the keyboard grab) and calls `QApplication.quit()` for a clean exit. All sizes go through `sc()` / fonts through `scpt()`; stylesheets use class/id selectors only (no `padding`/`margin` on frames - layout margins instead).

### Startup & Splash Screen

`main.py` is the bootstrapper; `vector.app.main()` finishes the sequence. The auth gate runs **before** the splash, and heavy imports (`vector.app`, yfinance, numpy, all pages/widgets) happen **after** the splash is already painted:

1. `main.py:_create_app()` creates the `QApplication` using only PyQt6 (fast — the `vector` package is not imported yet).
2. `main.py:_run_auth_gate(app)` resolves `(token, user_data)` — saved session or `LoginWindow`. Exits if the user cancels.
3. `main.py:_show_splash(app)` loads `assets/splashboard.png` and displays it as an always-on-top `QSplashScreen`, then calls `app.processEvents()` to force the OS to paint it before any heavy work. The splash is **responsive-sized**, not fixed: width = `min(screen_width × 0.55, 900)`, height keeps the source 1400:800 ratio, centred on the primary screen.
4. `from vector.app import main` (the heavy import chain runs here, splash already visible), then `main(app, splash, t_start, token=…, user_data=…)`.
5. `init_scale(app)` initialises the global width-driven UI scale factor (see **UI Scaling**), then the taskbar icon is set.
6. `VectorMainWindow(token, user_data)` is constructed (loads data, builds UI). A daemon thread prefetches prices for `COMMON_TICKERS` so Add Position shows instant estimates.
7. The splash is shown for a **minimum of 2 seconds** total (measured from `t_start`); a `QTimer` waits out any remainder, then `window.show()` + `splash.finish(window)`. Immediately after, `_maybe_show_legal_gates(window, token)` runs the TOS + EULA acceptance check (see **Legal Acceptance Gate (TOS + EULA)**).

`vector.app.main()` also has a self-contained fallback (auth gate + splash) for when it's invoked directly without going through `main.py` (e.g. during development).

### Data Flow

1. `VectorMainWindow` owns `DataStore`, all settings/state, the auth `token`/`user_data`, a `NotificationManager` (`self.notifications`), and the `QTimer` for auto-refresh. ~1.5 s after launch it kicks off `check_version()` (background thread → update toast if out of date).
2. On startup: load JSON state → show `OnboardingPage` (first run) or `MainShell` (returning).
3. `MainShell` hosts an `sc(220)` px sidebar + `QStackedWidget` with `DashboardPage`, `VectorLensPage`, `ProfilePage`, `SettingsPage` (all base sizes scaled — see **UI Scaling**). Header contains a "?" icon button (`sc(48)`², rounded) that opens the keyboard-shortcuts modal. On window resize, `self.notifications.reposition_all()` keeps the toast stack pinned to the top-right.
4. `DashboardPage` has a permanent `LensDisplay` at the top, followed by a free-form grid of `VectorWidget` instances; grid layout is loaded from / saved to `dashboard_layout.json`. Beneath the grid, a muted "Last updated N minutes ago" label updates every 30 s from a second `QTimer`.
5. `DashboardPage.update_dashboard()` calls `compute_portfolio_analytics()` → refreshes the lens, calls `widget.refresh()` on each placed widget, and stamps `_last_refresh` (used by `_update_refresh_label()`).
6. Edit mode (Edit button) enables drag-to-reposition and right-click delete on grid widgets (the lens is not affected). A separate **Delete button** (trash icon, third in the col-0 button stack below Add/Edit) toggles **delete mode**: every grid widget gets a red outline (mirroring edit mode's teal outline via `QFrame#vectorWidget[deleting="true"]`) and a single left-click on a widget pops the "Delete Widget" confirm menu. Edit and delete modes are **mutually exclusive** — entering one leaves the other. Both modes are driven by `VectorWidget.set_edit_mode`/`set_delete_mode` (and `DashboardGrid`'s same-named fan-out methods); the shared `_show_delete_menu()` backs both the delete-mode click and the edit-mode right-click.
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

**Lens Engine Version — `LENS_VERSION` in `constants.py` (currently `0.1.3`).** This is a **chronological change counter** for the Lens engine, independent of `APP_VERSION` and not shown in the UI. **Rule: ANY time you change Lens logic — anything under `vector/lens/` (analyzers, `analysis_pool`, `cta_engine`, the sentence composers, `lens_output`/caution score, `risk_profile`), the Lens-affecting parts of `constants.py` (risk profiles, sector maps, `SECTOR_SUGGESTIONS`, `LOW_BETA_BY_SECTOR`, `TICKER_SECTOR`), or `templates/sentences.json` in a way that changes output — bump `LENS_VERSION` by one in the SAME change.** It is a simple monotonic counter, not semver: tick the last number each time (`0.1.0 → 0.1.1 → 0.1.2 → …`; roll `0.1.9 → 0.2.0` when the patch digit would exceed 9). Do this even for small tweaks. Pure non-logic edits (comments, docs, formatting that can't change output) don't require a bump.

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
7. `sentence3.py` composes a CTA sentence — **the largest `rebalance` (trim) headlines the brief if one exists**, otherwise it prefers diversification CTAs (`reduce_concentration`, `sector_underweight`), then the highest-priority CTA
8. `lens_output.py` joins the 3 sentences, computes caution score, applies all CTAs to build `projected_positions`, writes a history snapshot, and returns the full result dict

**Analyzer interface:** Every analyzer exposes `analyze(positions, store, settings, risk_profile) → dict` with `ticker_results` (per-ticker) and `portfolio_result` (aggregate). Each result has `value`, `severity` (`none`/`low`/`moderate`/`high`/`critical`), `flag` (bool), `weight`, and `details`.

**CTA priorities (11 levels, 1 = highest):**
1. Steep decline (sell)
2. Excessive volatility (sell)
3. Winner drift (rebalance)
4. Index fund informational (hold)
5. High portfolio beta (buy) — prefers low-beta tickers from underweight sectors (reason string is `reduce_beta`; `LOW_BETA_BY_SECTOR['Technology']` lists genuinely lower-beta names like IBM/CSCO/ACN, **not** AAPL/MSFT)
6. Single-stock concentration (buy — up to 3 CTAs across underweight sectors, excludes the concentrated ticker's sector). **Exception:** a single position over **50%** of the book is **trimmed** via a `rebalance`/`reduce_concentration` CTA (all tiers), not diluted with deposits — see **>50% single-stock trim**.
7. Sector over-concentration (buy — up to 3 CTAs, always excludes the overweight sector)
8. Dead weight (sell)
9. Underrepresented sector (buy — up to 3 CTAs, one per thin sector <10%; **only fires for books holding 3–5 sectors** — a book already spread across `_DIVERSIFIED_SECTOR_COUNT` (6+) sectors is diversified enough that filling a slightly-light sector is noise, which is why near-perfect 10-sector books no longer get told to deposit)
10. Unrealized loss (hold)
11. Portfolio healthy (hold)

**Buy amount caps:** `_cap_buy_amount()` is applied to every buy-type priority (5, 6, 7, 9) so diversification deltas remain proportional to portfolio size. After `_dedupe_ctas()`, three passes run: `_drop_tiny_buys()` removes any buy below `max($200, 1% of equity)` (sub-1% "deposit $30 into KO" suggestions are noise), then `_cap_total_buys(ctas, equity, max_fraction)` scales **all** remaining buy CTAs down proportionally so their combined dollars stay within `max_fraction` of total equity (a fraction of 0 drops every buy), then **`_drop_tiny_buys()` runs again** — `_cap_total_buys` scales buys *down*, which can push one back below the floor, so a scaled-down "deposit $80" must not survive. Don't drop this second pass.

**Danger-aware buy budget (don't regress):** the `max_fraction` passed to `_cap_total_buys` is **tier-aware AND danger-aware**: `base = _MAX_TOTAL_BUY_FRACTION_BY_TIER[tier]` (`high 0.35 / regular 0.30 / low 0.20`), then `max_fraction = base × (1 − danger_weight)`. `danger_weight` (`_danger_weight` in `cta_engine.py`) is the share of the book in **critical** positions at full weight **plus half the share in `high` (non-critical) positions** (signals: volatility / performance / slope / concentration) — i.e. `crit_weight + 0.5·high_weight`. The `high` term matters because at the aggressive tier the performance `critical` threshold is -60%, so -40..-55% losers register as `high`; a critical-only throttle let a loser-heavy book still be told to deposit fresh capital (e.g. Deep-Losers-Club aggressive netted **+$6,880**). With the half-weight `high` term the buy budget shrinks on those books too, so the net CTA delta goes negative (de-risk) instead. `danger_weight` is 0 for any healthy/mild book, so normal dilution-buy advice is unaffected. (Mirrors the breadth lift in `lens_output._risk_floor`.)

**Proceeds-aware buy discipline / no deposit into a fire (don't regress):** after the danger-budget cap, `compute_ctas` applies, in order:
1. **Trim redistribution (rebalance only).** `rebalance_total = Σ|dollars|` over `rebalance` CTAs; if any, cap the combined buys to it (`_cap_total_buys` + `_drop_tiny_buys`) so a concentration/winner-drift trim **redistributes** rather than nets positive. **A plain risk `sell` does NOT cap diversification buys** — an earlier version capped buys to *all* sell+rebalance proceeds, which let a small volatility trim on one rising name silently wipe the legitimate "diversify your over-concentrated book" advice at the moderate tier while both neighbouring tiers gave it (All-Tech #29: cons/agg diversified, moderate dropped to a lone ORCL sell). Dangerous books are handled by step 2 instead, not by a sell-proceeds cap.
2. **Loss / danger gate (only when no rebalance is present).** Drop **all** buy CTAs when either `danger_weight ≥ _NO_DEPOSIT_DANGER_WEIGHT` (0.30) **or** `_loss_weight(...) ≥ _NO_DEPOSIT_LOSS_WEIGHT` (0.20). `_loss_weight` is the share of the book in positions with **realized weakness** — high/critical `performance` (unrealized loss) or `slope` (steep decline) — and explicitly **excludes volatility / beta / concentration**, because diversification/stabilization buys genuinely *do* remedy those structural risks (a 55% rising winner or a high-beta book should still be allowed to diversify) but do **not** remedy a realized loss. `_loss_weight` reads analyzer severities directly, so it is **tier-independent** and also catches the conservative tier whose protective sells are blocked (fixes the "deposit while holding speculative losers" case). The 0.20 floor is set above a single ~15% decliner so one declining name inside an otherwise concentration-driven book (e.g. AVGO in a 55%-tech book) does **not** wipe diversification advice.
3. **Concentration informational (`_add_concentration_informational`).** If a flagged single-stock concentration (`stock_concentration`, weight ≥ the tier `moderate` trigger) had its dilution buys dropped/capped above and has no other CTA (no CTA on it, and it is not the `heavy_ticker` behind a surviving buy), append an informational `hold` with reason `concentration_informational` so a dominant holding (e.g. 49% of the book) never vanishes from the readout.
4. **Never-empty fallback.** If the list ends empty (all buys dropped, nothing else), append a closing `hold` — `portfolio_caution` (severity high) when the book is dangerous (`danger_weight` or `_loss_weight` elevated), else `portfolio_healthy` — so the readout always has a card.

A healthy-but-concentrated book has `danger_weight ≈ 0` and `_loss_weight ≈ 0`, so steps 1–2 don't fire and its diversification advice is preserved (all-energy, all-tech-rising, mild-tilt books still get their dilution buys). `_cap_total_buys` now **floors** scaled buys (`_floor10`) so a capped redistribution can't round to a marginally net-positive +$10. Don't reintroduce the sell-proceeds cap, and don't drop the loss-weight half of the gate.

**Buy-CTA severity is display-capped (don't regress):** as the final step before returning, `compute_ctas` caps every `buy_new`/`buy_more` CTA's `severity` at `moderate` (a `critical`/`high` problem severity on a routine "deposit into a sector / low-beta name" overstated the urgency of the *buy itself*). Buy templates in `sentences.json` key only on `default`, so this changes the displayed severity label/colour only, not the rendered sentence.

**Concentration dilution target (don't regress):** Priorities 6 (single-stock) and 7 (sector) compute "buy elsewhere to dilute" dollars by solving `v_total_new = over_value / target_weight`. The dilution `target_weight` must sit **below** the flag trigger, never equal to it — a holding sitting right at the trigger would otherwise need ≈$0 to "dilute" back to the same number (this produced the $70-on-a-$17k-portfolio bug). The target is `trigger × _CONCENTRATION_DILUTION_FACTOR` (0.75) in `cta_engine.py`; the single-stock trigger is `risk_profile['concentration']['moderate']` (defaults to the `stock_concentration_pct` lens-signal, 35), the sector trigger is `['sector_moderate']` (50). Do not set the target back to the raw trigger.

**Sell gates / dead weight (don't regress):** Priority 8 (dead weight) is a *cleanup* suggestion — sell a sub-2% odd-lot — so it is **exempt from the `_sell_too_small` / `_MIN_POSITION_VALUE_FOR_SELL` ($1,000) floors**. Those floors would otherwise reject every sub-2% position, which made the priority dead code (zero `dead_weight` CTAs across 150 test runs). It uses its own tiny floor `_MIN_DEAD_WEIGHT_VALUE` ($25) to skip literal penny stubs. **It is gated on weight + dollar value ALONE — there is no slope gate.** (The old `ann <= 2.0` near-flat-slope condition kept it dead code: real odd-lots are rarely flat. Don't reintroduce a slope gate.) It also skips a ticker that already has a sell/rebalance from a stronger signal. Still suppressed entirely for the conservative tier. **Priority 9 interaction (don't regress):** a thin sector whose only representation is a sub-2% odd-lot is **excluded** from the priority-9 underweight buys. `dead_weight_sectors` is computed **directly from the holdings** (`sector_for(t)` for any `ticker_weights[t] < 0.02` not in `INDEX_ETFS`), **not** from emitted `dead_weight` CTAs — so the exclusion **also applies to the conservative tier**, which suppresses `dead_weight` sells and would otherwise be told to deposit into the very sector holding the odd-lot it can't sell (e.g. conservative SELL-suppressed T + BUY GOOGL). The engine never recommends buying into a sector while that sector's only holding is an odd-lot.

**SELL+HOLD de-duplication (don't regress):** Priority 10 (unrealized-loss HOLD) **skips any ticker that already carries a `sell`/`rebalance` CTA**. The informational "underwater, holding the rest" line is redundant next to an active sell and reads as a contradiction (`SELL PLUG` + `HOLD PLUG`). The sell already conveys intent; gate this at generation time (`_dedupe_ctas` deliberately allows sell+hold to coexist for partial trims).

**>50% single-stock trim (don't regress):** in priority 6, a single position **over 50% of the book** is handled by emitting a `rebalance` CTA (`reason='reduce_concentration'`, trims toward `trigger × _CONCENTRATION_DILUTION_FACTOR`, capped at 35% of the position) for **every tier**, then `continue` — it never falls through to the buy-to-dilute path. Telling someone with 60%+ in one name to *deposit* fresh cash into other sectors is unactionable; mirror the >50% sell exceptions elsewhere and trim. Renders via the `rebalance.reduce_concentration` templates in `sentences.json`. Two precedence rules: (a) if the name **already has a winner-drift `rebalance`** (priority 3), leave it — that narrative is more informative; (b) the trim **supersedes a SMALLER same-direction risk `sell`** (the prior `sell`s on that ticker are removed and replaced by the trim when `trim ≥ sell_max`) — otherwise a tier-scaled vol/decline sell (conservative `sell_scale 0.10`) left a 76% TSLA reduced by only ~$880 at conservative vs a ~$6k trim at moderate. If an existing risk sell is *larger* than the trim, it's kept.

**Sector awareness:** `_get_ticker_sector()` in `cta_engine.py` looks up a ticker's sector via `SECTOR_SUGGESTIONS`. Every buy CTA verifies the suggested ticker is NOT in the problem sector. `_underweight_sectors_sorted()` returns all sectors sorted lightest-first, with an `exclude_sectors` parameter to skip problem sectors. `_split_dollars_by_underweight()` allocates dollars proportionally to how underweight each target sector is. `SECTOR_SUGGESTIONS` / `LOW_BETA_BY_SECTOR` use the **canonical yfinance taxonomy** — there is **no** duplicate `'Financials'` key (it never matched a held `'Financial Services'` name, so it was a phantom perpetually-underweight sector → constant spurious V/JPM buys). Don't reintroduce it; `normalize_sector` folds `'Financials'` onto `'Financial Services'`.

**Sector resolution (don't regress):** every place that buckets a position by sector — `analysis_pool._build_positions_summary`, `concentration.analyze`, `lens_output._apply_all_ctas` — resolves it through `sector_for(ticker, live_sector)` (`constants.py`), which trusts a valid live sector, else falls back to the static `TICKER_SECTOR` map, else `'Unknown'`. **Why this matters:** when a live yfinance sector lookup fails/returns empty (common under bulk rate-limiting), the held name would otherwise vanish into an `'Unknown'` bucket — the diversification math then reports its real sector as 0% (telling the user to buy a sector they already hold, e.g. UNH while holding JNJ) and `sector_count` collapses to ≤1, fabricating a high-severity sector-concentration flag (which pinned caution to 62 on near-perfect books). Correspondingly, `concentration.analyze` now treats the `'Unknown'` bucket as **missing data, not a real sector**: it derives `sector_count`/`heaviest_sector` from KNOWN sectors only, never reports `'Unknown'` as the over-concentrated sector, and applies the COUNT-based escalation (`≤1 ⇒ high`, `≤2 ⇒ moderate`) **only when `unknown_pct ≤ 20%`** (otherwise it escalates solely on a known sector's own weight). Genuinely ambiguous tickers omitted from `TICKER_SECTOR` fall through to `'Unknown'` and are handled gracefully.

**Risk profiles:** Three tiers (`high`/`regular`/`low`) with different severity thresholds per analyzer. Stored in `constants.py` as `DEFAULT_RISK_PROFILES`. User overrides from `settings.json` → `lens_signals` take precedence **only when the user has changed a value away from the shipped `DEFAULT_SETTINGS['lens_signals']` default** (see `risk_profile.py :: _changed`). This is deliberate: applying the shipped defaults unconditionally (the old behaviour) overwrote the per-tier thresholds with a single cross-tier value, flattening the tiers and even inverting their ordering (Conservative concentration `moderate`=35 **>** `high`=30, so a 34% holding skipped straight to `high`). With the gate, an untouched setting defers to the tier, so the risk-tier selection is meaningful and monotonic; a deliberately-changed value still overrides. Risk tier stored in `settings.json` → `risk_tier` (default `"regular"`), selectable during onboarding and in Settings → Investment Style.

**Sell aggressiveness:** `sell_scale` controls the fraction of the calculated sell amount recommended: `high` = 0.25, `regular` = 0.50, `low` = 0.10 (see `DEFAULT_RISK_PROFILES`). Conservative tier (`low`) additional gates via `_conservative_sell_blocked()`:
- **Priorities 1 & 2:** Only fire on `critical` severity (`high` suppressed), and large-/unknown-cap names are blocked.
- **Market-cap handling (don't regress):** when a name's market cap is unknown, assume large-cap (block) **only for non-critical signals**. A `critical`-severity position with unknown cap is treated as a speculative small-cap and is **NOT** blocked — otherwise the conservative tier went fully silent (all HOLDs) on max-caution small-cap disasters whose caps come back empty under rate-limiting. (Note: a separate `_MIN_SELL_DOLLARS` $500 floor can still suppress a *tiny* conservative sell on a small position — that floor is intentional.)
- **Priority 3:** Converted to informational `hold` with `winner_drift_informational` reason — **except** a drifted winner that dominates the book (>50% weight), which is still trimmed via a `rebalance` CTA (mirrors the >50% sell exception; a low-risk investor should be able to trim a holding that is over half the portfolio rather than be told to deposit fresh capital to dilute it).
- **Priority 8:** Suppressed entirely.

**Conservative concentration thresholds (don't regress):** `DEFAULT_RISK_PROFILES['low']['concentration']` is `{moderate:25, high:35, critical:45}` — the `moderate` trigger is **25%, not 20%**. A 20–25% single position is normal; the old 20% trigger made conservative alarmist (flagging any one-fifth holding into multi-thousand-$ buy-to-dilute deposits and a 90s caution on otherwise-healthy books). Still tighter than `regular` (30/40/50), so the tier stays cautious.

**P&L-aware sentence1:** `sentence1.py` selects the highlighted ticker by preferring alignment between unrealized loss and negative slope (and the inverse). Sentences route to `combined.position_loss_with_volatility` templates when a losing position also has high volatility. The brief **leads with loss/decline signals** (those are the dominant risk) but deliberately does **not** lead by praising the most volatile *rising* holding — the old `high_vol_rising` lead foregrounded the very position a risk-conscious reader should be wary of and surfaced the clamped (non-credible) momentum figure. A purely-rising high-vol book falls through to the neutral portfolio-state sentence instead.

Two further guards keep the lead honest (don't regress): (1) a **deep-loss lead** (step "1b") fires for any position ≥25% underwater OR carrying `critical` performance severity **regardless of volatility**, using `combined.position_loss_only` — without it, an underwater book whose names recently bounced reads as a "broad uptrend" and the brief leads with momentum/strength. (2) the `broad_uptrend` slope framing is **demoted to `portfolio_mixed`** when a single position is >50% of the book AND **not every name is rising** (`up_count < total_count`, not `down_count ≥ 1`) — "strength across holdings" must not headline a concentration disaster, and the gate must catch a "3 up, 1 **flat**" book (a flat position is not a decline). The dominant-position risk is surfaced by the CTA sentence.

**Slope display clamp:** `slope.py` clamps the annualized slope to `[-80, +60]`. Positive slopes carry no severity, so the `+60` ceiling only bounds the **displayed** figure — and it IS surfaced by the portfolio-state sentence, so it must stay *believable* (the old `+150` ceiling read as a bug when it appeared verbatim in the brief). Don't raise it back.

**Sentence templates:** All templates live in `vector/lens/templates/sentences.json`. Selection is deterministic (SHA-256 hash of portfolio state). All language is observational — no directives.

**Healthy-vs-caution reconciliation (don't regress):** the caution score is computed **before** sentence 3 and passed into `compose_s3(cta_list, pool_results, caution_score)`. When the only posture is `portfolio_healthy` (or the CTA list filtered to empty) but `caution_score ≥ 45`, the brief uses the `hold.portfolio_caution` templates ("risk is elevated, but no trade clears your current risk setting") instead of `portfolio_healthy` ("all within normal bounds"). This prevents the contradiction of a 97/99 caution score paired with "everything is normal" when a tier has suppressed all trades.

**Color mapping:** `sell` → `#ff4d4d`, `rebalance` → `#ff9f43`, `buy_new`/`buy_more` → `#38bdf8`, `hold` → `#8d98af`.

**Caution score:** 1–99, the **greater** of (a) a trade-flow score (`(Σ sell$ + 0.30·Σ buy$) / total equity × 100`) and (b) an **exposure-weighted risk floor** (`_risk_floor`). The floor maps analyzer severities through `_SEVERITY_CAUTION_POINTS` (`none 0 / low 10 / moderate 35 / high 62 / critical 90`) into three continuous components — `pos_pts` (weight-averaged per-position danger), `single_pts` (the worst single position, **damped by its weight** `× min(1, w/0.45)`), and `port_pts` (sector over-concentration, plus aggregate volatility/beta only once *elevated* to high/critical — a ~1.0 beta is normal market exposure, not caution) — takes their `max` as `base`. **Concentration is discounted by `_CONCENTRATION_CAUTION_DISCOUNT` (0.7) everywhere it contributes** (per-position `single_pts`/`pos_pts` *and* `port_pts`): concentration is structural exposure, not realized danger, so a 55%-of-book *rising* winner must not score like a 55% *crashing* position. Without the discount a 2-stock rising book out-scored a five-deep-loser book (#38=96 > #36=95); with it, pure-concentration books land in the high-70s/low-80s while loss/vol-driven disasters stay in the mid-90s. A concentrated position that is **also** losing or volatile still scores high via its *undiscounted* performance/volatility severity, and concentration still counts at **full weight** in the breadth lift (only its point value is discounted). Then applies a **breadth-of-danger lift** toward the 99 ceiling: `base + (99 − base) · danger · 0.65`, where `danger = min(1, crit_weight + 0.5·high_weight)` — `crit_weight` is the share of the book in positions with any critical signal (full weight) and `high_weight` the share in `high` (non-critical) positions (half weight). The floor exists so a genuinely dangerous book still scores high in tiers that suppress sells; the breadth lift spreads the worst books across the upper band (a single dominant critical position lands low-90s; a wholly-critical book approaches high-90s) **and spreads `high`-severity books above a lone-`high` book instead of every one snapping to the discrete `high`=62 bucket** (the `high_weight` term — don't drop it). **Don't regress to a flat max-of-severities or a hard `critical=88` ceiling:** the old flat version counted the worst single ticker at full weight (one 41%-vol satellite at 20% weight pinned a "near-perfect" portfolio to 60/99) and capped every disaster at 88, collapsing the score into ~5 buckets (8/30/60/88) and leaving the 89–99 band dead. The weight-aware floor + breadth lift restores granularity (healthy ≈ single digits, distinct disasters across the low-to-high 90s). The lift multiplier is **0.65** (lowered from 0.8) to widen the gap in the 90s so a single-issue book — one drifted winner — no longer pins to the same 94–97 as a five-alarm book; a wholly-critical book still lands ~95. See `_compute_caution_score` / `_risk_floor` in `lens_output.py`.

**Winner-drift requires real appreciation (don't regress):** `concentration.py` only sets the `winner_drift` sub-signal when `weight_pct > 30 and drift_multiple > 2.0 **and current_value > cost_equity**`. Without the last clause, a position that merely fell *less* than its peers (so its current-value weight exceeds its cost-basis weight) gets mislabeled a "winner that drifted" — producing "price appreciation pushed…" text and contradictory SELL+HOLD CTAs on an underwater holding. Additionally, the priority-3 winner-drift loop in `cta_engine.py` **skips any ticker that already has a `sell` CTA** (from priority 1/2): a position can't simultaneously be a runaway winner to rebalance/hold and a steep-decline/high-vol position to sell. The risk sell wins (this is what removed the `SELL FCEL` + `HOLD FCEL winner_drift` contradiction). `_dedupe_ctas` permits a sell and a hold on the same ticker, so this must be gated at generation time, not in dedup.

**Conservative can trim a dominant position (don't regress):** `_conservative_sell_blocked` in `cta_engine.py` normally blocks large-/unknown-cap sells, but has an explicit exception for any position **> 50% of the book** — even a conservative investor should be allowed to trim a holding that is more than half the portfolio. Without it, a 78%-in-one-leveraged-ETF book had its sell suppressed and was instead told to *deposit* tens of thousands to dilute it (unactionable). The **same >50% exception applies to winner-drift (priority 3)**: a drifted winner over half the book is trimmed (`rebalance`) for the conservative tier rather than left as an informational hold.

**Index-dominated sector downgrade (don't regress):** index ETFs are excluded from the per-sector tally, so a heavily-index portfolio otherwise shows `sector_count ≤ 1/2` → false `high`/`moderate` sector-concentration flag → spurious "buy individual stocks to diversify" CTAs. `concentration.py` computes `index_weight_pct` and, when it's ≥ 50%, downgrades `sector_sev` from moderate/high to `low` (the index *is* the diversification). This keeps all-index/index-core portfolios out of the sector-underweight CTA path.

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

**Steps:** the flow is a 3-step `QStackedWidget` - **EULA**, **Risk Profile**, **Portfolio Setup** (in that order). Step bookkeeping is derived from `self._stack.count()` rather than hardcoded indices (`_go_to` clamp, `_refresh_nav` button labels, `_on_next`, the `A`-key guard in `keyPressEvent`, and `refresh_cards`), so adding or removing a step does not break navigation. The next-button label is "I Accept" on the EULA step, "Skip for now" on any other non-final/non-penultimate step, "Continue" on the second-to-last, and "Launch Portfolio" (enabled only when at least one position exists) on the last.

**EULA step (step 1):** the first step is a functional EULA acceptance gate (it replaced an "Account" placeholder; **TOS is still handled by the launch-time gate** — see **Legal Acceptance Gate (TOS + EULA)**). It shows the title "End User License Agreement", a concise message, and a teal text link that opens `EULA_URL` (from `constants.py`) in the system browser via `QDesktopServices.openUrl(QUrl(...))`. Acceptance flow:
- On `OnboardingPage.__init__`, `_check_eula_required()` runs a synchronous `check_eula_status(token)` (from `auth/auth.py`) and sets `self._eula_required`. It **fails open** (returns `False`, so onboarding starts on the Risk Profile step) for the demo bypass, a missing `window.token`, or any network/parse failure (`status is None`). It returns `True` only when the backend explicitly reports `eula_accepted is False`.
- `self._min_step` is `0` when the EULA is required, else `1`. `_go_to` clamps its lower bound to `_min_step` and the Back button is hidden at `_min_step`, so an already-accepted (skipped) EULA step can never be navigated back to. The EULA step always exists in the stack; it is just never shown when not required.
- Clicking **I Accept** (or pressing Space on the step) calls `_accept_eula()`, which runs the shared `_AcceptWorker(token, 'eula')` `QThread` (imported from `vector/eula_gate.py`) so the POST `/legal/accept` does not freeze the UI. The button shows a loading state while in flight, and the worker guard prevents a double-click from starting two POSTs. On `'ok'` it sets `_eula_required = False`, raises `_min_step` to `1`, and advances to step 2. On `'unauthorized'` (session expired) it `clear_token()`s and quits (mirrors the legal gate). On `'failed'` it shows an inline error on the step and re-enables the button to retry.
- Because acceptance is recorded server-side, the dashboard's `_maybe_show_legal_gates` (which runs after onboarding completes) sees `eula_accepted: True` and does not re-prompt — no special-case code needed. Returning users who skip onboarding entirely are unaffected; the dashboard gate still handles them. Acceptance is **never** stored locally.

Keyboard shortcuts (widget-scoped with `WidgetWithChildrenShortcut`):
- **A** — opens Add Position dialog
- **Space** — advances to the next step via `_on_next()` (on the EULA step this triggers acceptance). Guarded: if focus is a `QLineEdit`, space types a space character instead of triggering navigation. Shortcut is not exposed in any button label.

**Horizontal position list:** `cards_scroll` has a custom `wheelEvent` that maps vertical wheel delta to its horizontal scrollbar (~80 px per 120-unit notch) so users can scroll the card list with a normal mouse wheel.

**Remove Position toggle (Portfolio Setup step):** next to "Add Position" sits a checkable red `OutlineButton` ("Remove Position"). While toggled ON it shows a translucent-red active fill (via `OutlineButton`'s `isCheckable()`/`isChecked()` paint branch; non-checkable instances like the Settings buttons are unaffected) and every `PositionCard` gets a red border plus a red hover tint and a pointing cursor. Clicking a card while the toggle is ON deletes that position immediately (no confirmation by design, since onboarding is throwaway data): it is removed from `self.pending_positions` and `refresh_cards()` rebuilds the list (which also re-enables/disables the toggle and updates the "Launch Portfolio" button state). The toggle stays ON across deletes so multiple cards can be removed in one pass, and auto-turns OFF (and disables) once the last position is gone. Like the Add flow, deletes operate on the in-memory `pending_positions` only; positions are not persisted to disk until `launch()` commits them. Methods: `_on_delete_toggle`, `_set_cards_delete_mode`, `_delete_position`; `PositionCard.set_delete_mode` drives the per-card visual/click behaviour. The toggle does not interfere with the horizontal wheel scrolling (that handler lives on the scroll area, not the cards).

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
