from .paths import resource_path, user_data_dir

# Debug: override the DPI scale factor used for window/UI sizing.
# None = use the real screen devicePixelRatio (normal behaviour).
# Set to a float to simulate a different screen density, e.g.:
#   1.0  → 1080p feel   2.0 → native 4K feel
DEBUG_SCREEN_SCALE: float | None = None

APP_NAME = 'Vector'
COMPANY_NAME = 'Protonyx'
APP_VERSION = '0.4.2'
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
    'Technology':             ['MSFT', 'AAPL', 'ACN', 'IBM', 'TXN'],
    'Healthcare':             ['JNJ', 'ABT', 'MDT', 'BMY', 'PFE'],
    'Consumer Defensive':     ['KO', 'PEP', 'WMT', 'PG', 'CL'],
    'Financial Services':     ['BRK-B', 'V', 'MA', 'AXP', 'WFC'],
    'Financials':             ['BRK-B', 'V', 'MA', 'AXP', 'WFC'],
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
    'Financials':             ['JPM', 'V', 'MA', 'BAC', 'GS'],
    'Consumer Defensive':     ['PG', 'KO', 'PEP', 'COST', 'WMT'],
    'Consumer Cyclical':      ['AMZN', 'TSLA', 'MCD', 'NKE', 'HD'],
    'Industrials':            ['GE', 'CAT', 'HON', 'UPS', 'BA'],
    'Energy':                 ['XOM', 'CVX', 'COP', 'SLB', 'EOG'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'T'],
    'Utilities':              ['NEE', 'SO', 'DUK', 'AEP', 'SRE'],
    'Real Estate':            ['PLD', 'AMT', 'EQIX', 'CCI', 'SPG'],
    'Basic Materials':        ['LIN', 'APD', 'SHW', 'FCX', 'NEM'],
}

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
        'concentration': {'critical': 40,  'high': 30,  'moderate': 20},
        'beta':          {'critical': 1.4, 'high': 1.1, 'moderate': 0.8},
        'performance':   {'critical': -40, 'high': -25, 'moderate': -15},
        'sell_scale': 0.10,
    },
}
