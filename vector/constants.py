from .paths import resource_path, user_data_dir

# Debug: override the global UI scale factor used for window/UI sizing.
# None = use the width-driven scale computed in vector/scale.py (normal behaviour).
# Set to a float to force a fixed factor, e.g.:
#   0.9  → the "perfect fit" 1080p feel   1.35 → a roomy 1080p@100% feel
DEBUG_SCREEN_SCALE: float | None = None

# UI scaling (see vector/scale.py). The dashboard is authored for UI_BASE_WIDTH
# logical px of horizontal space — the 220 px sidebar, 2×24 px content margins,
# and the 11-column, 1090 px grid (~1358 px) plus breathing room for window
# borders and the scrollbar. The runtime scale = available_screen_width /
# UI_BASE_WIDTH, clamped to [UI_SCALE_MIN, UI_SCALE_MAX], so the layout fills the
# screen on any resolution instead of leaving a blank band on the right. Lower
# UI_BASE_WIDTH ⇒ larger UI. On a logical-1280 viewport (1080p @ 150%) this lands
# at ~0.9; tune UI_BASE_WIDTH to shift that calibration.
UI_BASE_WIDTH: float = 1422.0
UI_SCALE_MIN: float = 0.70
UI_SCALE_MAX: float = 3.00
UI_MIN_POINT_SIZE: int = 7

APP_NAME = 'Vector'
COMPANY_NAME = 'Protonyx'
APP_VERSION = '0.4.9'
# Chronological version of the Lens engine (vector/lens/*). This is a simple
# monotonic change counter, NOT app/semver — bump the last number by one on ANY
# change to Lens logic (analyzers, CTA engine, sentence composers, caution
# score, risk profiles, sector resolution, templates that alter output). It is
# not shown in the UI. See CLAUDE.md → "Lens Engine Version".
LENS_VERSION = '0.1.3'
# Base URL for all web redirects (forgot password, EULA, TOS). Change this single
# value to repoint every web link at a different host — each redirect below just
# appends its path. e.g. BASE_URL = 'protonyxdata.com' makes FORGOT_PASSWORD_URL
# 'protonyxdata.com/forgot-password'.
BASE_URL = 'https://protonyxdata.com'
FORGOT_PASSWORD_URL = f'{BASE_URL}/forgot-password'
EULA_URL = f'{BASE_URL}/eula'
TOS_URL = f'{BASE_URL}/tos'
DATA_DIR = user_data_dir()
POSITIONS_FILE = DATA_DIR / 'positions.json'
SETTINGS_FILE = DATA_DIR / 'settings.json'
APP_STATE_FILE = DATA_DIR / 'app_state.json'
MARKET_DATA_FILE = DATA_DIR / 'market_data.json'
LAYOUT_FILE = DATA_DIR / 'dashboard_layout.json'
LOGO_PATH = resource_path('assets', 'vector_full.png')
TASKBAR_LOGO_PATH = resource_path('assets', 'vector.ico')

DEFAULT_SETTINGS = {
    'theme': 'Dark',
    'currency': 'USD',
    'date_format': 'MM/DD/YYYY',
    'refresh_interval': '5 min',
    'direction_thresholds': {
        'strong': 0.08,
        'steady': 0.02,
        'neutral_low': -0.02,
        'neutral_high': 0.02,
        'depreciating': -0.08,
    },
    'volatility': {
        'lookback': '6 months',
        'low_cutoff': 30,
        'high_cutoff': 60,
    },
    'lens_signals': {
        'stock_concentration_pct': 35,
        'sector_concentration_pct': 50,
        'steep_downtrend_pct': -20,
        'high_beta_threshold': 1.3,
        'stock_vol_threshold_pct': 35,
        'dead_weight_pct': 2,
        'loss_threshold': -15,
        'winner_drift_multiple': 2.0,
    },
    'monte_carlo': {
        'projection_period': '1 year',
        'simulations': 500,
    },
}

DEFAULT_APP_STATE = {
    'onboarding_complete': False,
    'first_launch_date': None,
    'risk_tier_selected': False,
}

DEFAULT_POSITIONS = []
LENS_SNAPSHOT_FILE = 'lens_snapshot.json'
LENS_HISTORY_MAX = 90
TTL_META_MINUTES         = 1_440   # 24 h — company info rarely changes
TTL_HISTORY_DAILY_MINUTES = 60      # 60 min for 1mo and longer daily bars
TTL_DIVIDENDS_MINUTES    = 1_440   # 24 h
TTL_EARNINGS_MINUTES     = 1_440   # 24 h

REFRESH_INTERVAL_MINUTES = {
    '1 min': 1,
    '5 min': 5,
    '15 min': 15,
    'Manual only': None,
}
VOLATILITY_LOOKBACK_PERIODS = {
    '3 months': '3mo',
    '6 months': '6mo',
    '1 year': '1y',
}

MONTE_CARLO_HORIZON_DAYS: dict[str, int] = {
    '3 months': 63,
    '6 months': 126,
    '1 year': 252,
    '2 years': 504,
}

MONTE_CARLO_SIMULATIONS: list[int] = [100, 200, 500, 1000]

# Broad-market index ETFs — treated as instant diversification, not single-stock concentration.
INDEX_ETFS: frozenset[str] = frozenset({
    'SPY', 'VOO', 'VTI', 'IVV', 'QQQ', 'QQQM', 'VT', 'VXUS', 'ITOT',
    'SCHB', 'VEA', 'VWO', 'SPDW', 'IEFA', 'EFA', 'SCHX', 'SCHD', 'VIG',
    'MGK', 'QUAL', 'MOAT', 'RSP', 'DGRO', 'VYM', 'HDV', 'NOBL',
    'DIA', 'IWM', 'IWF', 'IWD',
})

# Mapping of index ETFs to their type for Lens language
INDEX_FUND_TYPES: dict[str, str] = {
    'SPY': 'broad_market', 'VOO': 'broad_market', 'VTI': 'broad_market',
    'IVV': 'broad_market', 'ITOT': 'broad_market', 'SCHB': 'broad_market',
    'DIA': 'broad_market', 'IWM': 'broad_market', 'IWF': 'broad_market',
    'IWD': 'broad_market', 'RSP': 'broad_market', 'SCHX': 'broad_market',
    'QQQ': 'sector', 'QQQM': 'sector', 'MGK': 'sector',
    'VT': 'international', 'VXUS': 'international', 'VEA': 'international',
    'VWO': 'international', 'SPDW': 'international', 'IEFA': 'international',
    'EFA': 'international',
    'VIG': 'broad_market', 'SCHD': 'broad_market', 'QUAL': 'broad_market',
    'MOAT': 'broad_market', 'DGRO': 'broad_market', 'VYM': 'broad_market',
    'HDV': 'broad_market', 'NOBL': 'broad_market',
}

# Well-known lower-beta names per sector — used to suggest alternatives when portfolio beta is high.
# These are examples of historically lower-beta equities; not investment advice.
LOW_BETA_BY_SECTOR: dict[str, list[str]] = {
    'Technology':             ['IBM', 'CSCO', 'ACN', 'TXN', 'ORCL'],
    'Healthcare':             ['JNJ', 'ABT', 'MDT', 'BMY', 'PFE'],
    'Consumer Defensive':     ['KO', 'PEP', 'WMT', 'PG', 'CL'],
    'Financial Services':     ['BRK-B', 'V', 'MA', 'AXP', 'WFC'],
    'Industrials':            ['HON', 'MMM', 'ITW', 'EMR', 'PH'],
    'Energy':                 ['CVX', 'XOM', 'COP', 'PSX', 'VLO'],
    'Consumer Cyclical':      ['MCD', 'HD', 'LOW', 'TGT', 'YUM'],
    'Communication Services': ['T', 'VZ', 'CMCSA', 'DIS', 'WBD'],
    'Utilities':              ['NEE', 'SO', 'DUK', 'AEP', 'WEC'],
    'Real Estate':            ['O', 'PLD', 'SPG', 'PSA', 'EQR'],
    'Basic Materials':        ['LIN', 'APD', 'SHW', 'ECL', 'NEM'],
}

# ~100 commonly traded tickers — prices are batch-prefetched at startup so
# the Add Position dialog can show an estimated equity instantly (no validation wait).
COMMON_TICKERS: list[str] = [
    # Technology
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC',
    'QCOM', 'AVGO', 'TXN', 'ACN', 'IBM', 'ORCL', 'ADBE', 'CRM', 'NFLX',
    'UBER', 'PYPL',
    # Financial Services
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'V', 'MA', 'AXP', 'BRK-B',
    # Healthcare
    'UNH', 'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'BMY', 'AMGN', 'GILD',
    'ABT', 'MDT', 'TMO', 'DHR', 'ISRG', 'REGN', 'VRTX', 'MRNA',
    # Consumer
    'WMT', 'COST', 'HD', 'LOW', 'MCD', 'SBUX', 'TGT', 'NKE', 'PG',
    'KO', 'PEP', 'CL', 'YUM', 'DIS', 'CMCSA',
    # Energy & Industrials
    'XOM', 'CVX', 'COP', 'VLO', 'PSX', 'HON', 'MMM', 'ITW', 'EMR',
    'BA', 'CAT', 'DE', 'UNP', 'LMT', 'RTX', 'FDX', 'UPS', 'GE',
    # Telecom & Utilities
    'T', 'VZ', 'NEE', 'SO', 'DUK', 'AEP', 'WEC',
    # Real Estate
    'O', 'PLD', 'SPG', 'PSA', 'EQR', 'AMT', 'EQIX',
    # Basic Materials
    'LIN', 'APD', 'SHW', 'ECL', 'NEM',
    # ETFs
    'SPY', 'VOO', 'VTI', 'QQQ', 'IVV',
]

# Representative tickers per sector — ordered by market cap (highest first).
SECTOR_SUGGESTIONS: dict[str, list[str]] = {
    'Technology':             ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AVGO'],
    'Healthcare':             ['UNH', 'JNJ', 'LLY', 'PFE', 'ABT'],
    'Financial Services':     ['JPM', 'V', 'MA', 'BAC', 'GS'],
    'Consumer Defensive':     ['PG', 'KO', 'PEP', 'COST', 'WMT'],
    'Consumer Cyclical':      ['AMZN', 'TSLA', 'MCD', 'NKE', 'HD'],
    'Industrials':            ['GE', 'CAT', 'HON', 'UPS', 'BA'],
    'Energy':                 ['XOM', 'CVX', 'COP', 'SLB', 'EOG'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'T'],
    'Utilities':              ['NEE', 'SO', 'DUK', 'AEP', 'SRE'],
    'Real Estate':            ['PLD', 'AMT', 'EQIX', 'CCI', 'SPG'],
    'Basic Materials':        ['LIN', 'APD', 'SHW', 'FCX', 'NEM'],
}

# Canonical sector for well-known tickers — a deterministic fallback used when
# live metadata (yfinance) does not return a sector (e.g. during rate-limited
# bulk fetches). Without it, a held name with a missing sector falls into an
# "Unknown" bucket: the diversification math then reports its real sector as 0%
# (telling the user to buy a sector they already hold) and can fabricate a
# single-sector concentration flag. Names whose classification is genuinely
# ambiguous (some crypto-miners, a few small caps) are intentionally omitted —
# they fall through to 'Unknown', which the analyzers now treat as "insufficient
# data" rather than a real sector. Sector strings match the yfinance taxonomy.
TICKER_SECTOR: dict[str, str] = {
    # Technology
    'AAPL': 'Technology', 'MSFT': 'Technology', 'NVDA': 'Technology',
    'AVGO': 'Technology', 'ORCL': 'Technology', 'AMD': 'Technology',
    'INTC': 'Technology', 'IBM': 'Technology', 'CSCO': 'Technology',
    'ACN': 'Technology', 'TXN': 'Technology', 'ADBE': 'Technology',
    'CRM': 'Technology', 'QCOM': 'Technology', 'PLTR': 'Technology',
    'UBER': 'Technology', 'MSTR': 'Technology', 'SOUN': 'Technology',
    'BBAI': 'Technology', 'QUBT': 'Technology', 'RGTI': 'Technology',
    'IONQ': 'Technology',
    # Healthcare
    'JNJ': 'Healthcare', 'UNH': 'Healthcare', 'ABBV': 'Healthcare',
    'LLY': 'Healthcare', 'PFE': 'Healthcare', 'ABT': 'Healthcare',
    'MDT': 'Healthcare', 'BMY': 'Healthcare', 'MRK': 'Healthcare',
    'AMGN': 'Healthcare', 'GILD': 'Healthcare', 'TMO': 'Healthcare',
    'DHR': 'Healthcare', 'ISRG': 'Healthcare', 'REGN': 'Healthcare',
    'VRTX': 'Healthcare', 'MRNA': 'Healthcare',
    # Financial Services
    'JPM': 'Financial Services', 'V': 'Financial Services', 'MA': 'Financial Services',
    'BAC': 'Financial Services', 'GS': 'Financial Services', 'MS': 'Financial Services',
    'C': 'Financial Services', 'BLK': 'Financial Services', 'AXP': 'Financial Services',
    'BRK-B': 'Financial Services', 'WFC': 'Financial Services', 'PYPL': 'Financial Services',
    'SOFI': 'Financial Services', 'HOOD': 'Financial Services', 'COIN': 'Financial Services',
    # Consumer Defensive
    'PG': 'Consumer Defensive', 'KO': 'Consumer Defensive', 'PEP': 'Consumer Defensive',
    'COST': 'Consumer Defensive', 'WMT': 'Consumer Defensive', 'CL': 'Consumer Defensive',
    # Consumer Cyclical
    'AMZN': 'Consumer Cyclical', 'TSLA': 'Consumer Cyclical', 'MCD': 'Consumer Cyclical',
    'NKE': 'Consumer Cyclical', 'HD': 'Consumer Cyclical', 'LOW': 'Consumer Cyclical',
    'TGT': 'Consumer Cyclical', 'YUM': 'Consumer Cyclical', 'SBUX': 'Consumer Cyclical',
    'RIVN': 'Consumer Cyclical', 'LCID': 'Consumer Cyclical', 'GME': 'Consumer Cyclical',
    'F': 'Consumer Cyclical',
    # Energy
    'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy', 'SLB': 'Energy',
    'EOG': 'Energy', 'VLO': 'Energy', 'PSX': 'Energy', 'UEC': 'Energy',
    # Industrials
    'HON': 'Industrials', 'MMM': 'Industrials', 'ITW': 'Industrials',
    'EMR': 'Industrials', 'PH': 'Industrials', 'BA': 'Industrials',
    'CAT': 'Industrials', 'DE': 'Industrials', 'UNP': 'Industrials',
    'LMT': 'Industrials', 'RTX': 'Industrials', 'FDX': 'Industrials',
    'UPS': 'Industrials', 'GE': 'Industrials', 'PLUG': 'Industrials',
    'FCEL': 'Industrials', 'SPCE': 'Industrials',
    # Communication Services
    'GOOGL': 'Communication Services', 'META': 'Communication Services',
    'NFLX': 'Communication Services', 'DIS': 'Communication Services',
    'T': 'Communication Services', 'VZ': 'Communication Services',
    'CMCSA': 'Communication Services', 'WBD': 'Communication Services',
    'FUBO': 'Communication Services', 'DJT': 'Communication Services',
    # Utilities
    'NEE': 'Utilities', 'SO': 'Utilities', 'DUK': 'Utilities',
    'AEP': 'Utilities', 'WEC': 'Utilities', 'SRE': 'Utilities',
    # Real Estate
    'O': 'Real Estate', 'PLD': 'Real Estate', 'SPG': 'Real Estate',
    'PSA': 'Real Estate', 'EQR': 'Real Estate', 'AMT': 'Real Estate',
    'EQIX': 'Real Estate', 'CCI': 'Real Estate', 'OPEN': 'Real Estate',
    # Basic Materials
    'LIN': 'Basic Materials', 'APD': 'Basic Materials', 'SHW': 'Basic Materials',
    'ECL': 'Basic Materials', 'NEM': 'Basic Materials', 'FCX': 'Basic Materials',
    'HL': 'Basic Materials', 'CDE': 'Basic Materials',
}

# yfinance occasionally returns alternate sector spellings; fold them onto the
# canonical names used as keys in SECTOR_SUGGESTIONS / TICKER_SECTOR.
_SECTOR_ALIASES: dict[str, str] = {
    'Financials': 'Financial Services',
    'Health Care': 'Healthcare',
}


def normalize_sector(sector: str | None) -> str:
    """Return a cleaned, canonical sector name, or '' for missing/unknown."""
    if not sector:
        return ''
    s = str(sector).strip()
    if not s or s.lower() == 'unknown':
        return ''
    return _SECTOR_ALIASES.get(s, s)


def sector_for(ticker: str, live_sector: str | None = None) -> str:
    """Resolve a position's sector: trust valid live metadata, else fall back to
    the static ``TICKER_SECTOR`` map, else ``'Unknown'``. This keeps a held name
    from vanishing out of the diversification math when a live sector lookup
    fails or returns empty."""
    s = normalize_sector(live_sector)
    if s:
        return s
    return TICKER_SECTOR.get((ticker or '').upper(), 'Unknown')


# ── Lens: Default Risk Profiles ──
DEFAULT_RISK_PROFILES: dict[str, dict] = {
    'high': {
        'slope':         {'critical': -50, 'high': -35, 'moderate': -20},
        'volatility':    {'critical': 80,  'high': 60,  'moderate': 45},
        'concentration': {'critical': 60,  'high': 50,  'moderate': 40},
        'beta':          {'critical': 2.2, 'high': 1.6, 'moderate': 1.2},
        'performance':   {'critical': -60, 'high': -40, 'moderate': -25},
        'sell_scale': 0.25,
    },
    'regular': {
        'slope':         {'critical': -40, 'high': -28, 'moderate': -15},
        'volatility':    {'critical': 65,  'high': 50,  'moderate': 35},
        'concentration': {'critical': 50,  'high': 40,  'moderate': 30},
        'beta':          {'critical': 1.8, 'high': 1.3, 'moderate': 1.0},
        'performance':   {'critical': -50, 'high': -30, 'moderate': -18},
        'sell_scale': 0.50,
    },
    'low': {
        'slope':         {'critical': -35, 'high': -25, 'moderate': -12},
        'volatility':    {'critical': 55,  'high': 42,  'moderate': 30},
        # Concentration moderate=25 (was 20): a 20–25% single position is normal,
        # not a flag. The old 20% trigger made the conservative tier alarmist —
        # flagging any one-fifth holding and turning it into multi-thousand-$
        # buy-to-dilute deposits + a 90s caution on otherwise-healthy books.
        # Still tighter than regular (30/40/50) so the tier stays cautious.
        'concentration': {'critical': 45,  'high': 35,  'moderate': 25},
        'beta':          {'critical': 1.4, 'high': 1.1, 'moderate': 0.8},
        'performance':   {'critical': -40, 'high': -25, 'moderate': -15},
        'sell_scale': 0.10,
    },
}
