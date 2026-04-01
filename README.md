# Vector — by Protonyx

**Vector answers the questions most portfolio trackers don't.**

Not just *what is my portfolio worth*, but *where is it going*, *how much risk am I carrying*, and *what should I actually do about it*. Every metric on the dashboard exists to give you a clear, actionable answer — not another number to interpret yourself.

---

## What it does

Vector is a desktop portfolio analytics app built with PyQt6. It pulls live market data via Yahoo Finance, runs it through a local analytics engine, and surfaces clear verdicts on your portfolio's health — no accounts, no cloud, no subscription.

### The dashboard answers six questions

| Widget | The question it answers |
|---|---|
| **Total Equity** | What is my portfolio worth right now, and how has it moved this week? |
| **Portfolio Direction** | Is my portfolio trending up, down, or sideways — and how strong is that trend? |
| **Volatility** | How rough is the ride? Am I taking on more risk than my returns justify? |
| **Diversification** | Am I overexposed to one sector, and what am I missing? |
| **Sharpe Ratio** | Am I being compensated for the risk I'm taking? |
| **Beta** | How much does my portfolio move relative to the market? |
| **Vector Lens** | What is the single most important thing I should do with my portfolio right now? |

The Vector Lens generates a three-sentence verdict: one that explains the outlook, and one that tells you what to do — specific to your tickers, your sector exposure, and your current direction and volatility profile.

---

## Features

- **Customisable dashboard** — add, remove, and drag widgets to build the layout that matters to you
- **Onboarding** — guided first-run setup with live ticker validation
- **Direction tracking** — 6-month linear regression slope, classified as Strong / Steady / Neutral / Depreciating / Weak
- **Volatility scoring** — annualised volatility scaled 1–100 with configurable low/high thresholds
- **Sharpe ratio & beta** — portfolio-level risk-adjusted return metrics
- **Dividend calendar** — upcoming dividend dates across all held positions
- **Sector allocation** — pie breakdown of equity by sector with diversification suggestions
- **Smart caching** — market data is cached locally with per-type TTLs; no redundant fetches
- **Dark & light themes** — full stylesheet toggle in Settings
- **Fully local** — all data stored on your machine, no accounts or internet required beyond market fetches

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

**Requirements:** Python 3.11+, Windows (primary target)

---

## Data storage

All files are stored in `%LOCALAPPDATA%\Protonyx\Vector\` (falls back to `~/Vector/data/` if `LOCALAPPDATA` is not set).

| File | Contents |
|---|---|
| `positions.json` | Your holdings — ticker, shares, equity, sector |
| `settings.json` | Theme, refresh interval, thresholds, volatility config |
| `app_state.json` | Onboarding state, first launch date |
| `market_data.json` | Cached quotes, price history, meta, dividends, earnings |
| `dashboard_layout.json` | Your saved widget layout |

Nothing is sent externally. Market data is fetched from Yahoo Finance on demand and cached locally.

---

## Assets

Place logo files at:

- `assets/vector_full.png` — full wordmark, shown on the onboarding screen
- `assets/vector_taskbar.png` — icon, shown in the window title bar

If either file is missing, Vector renders a generated placeholder automatically and launches normally.

---

## Built with

- [PyQt6](https://pypi.org/project/PyQt6/) — UI framework
- [yfinance](https://pypi.org/project/yfinance/) — Yahoo Finance market data
- [NumPy](https://numpy.org/) — analytics engine
- [pandas](https://pandas.pydata.org/) — yfinance data handling

---

## A note on how this was built

Vector was developed with the assistance of [Claude Code](https://claude.ai/code), Anthropic's AI coding tool. Most of my projects are not built this way — but part of being a good developer is staying curious and actually trying the tools that are changing the industry, not just reading about them. This project was an experiment in that spirit. The goal was to understand where AI-assisted development genuinely adds value, where it doesn't, and what that means for how I work going forward.