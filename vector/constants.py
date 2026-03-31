from .paths import resource_path, user_data_dir

APP_NAME = 'Vector'
COMPANY_NAME = 'Protonyx'
APP_VERSION = '0.3.6'
DATA_DIR = user_data_dir()
POSITIONS_FILE = DATA_DIR / 'positions.json'
SETTINGS_FILE = DATA_DIR / 'settings.json'
APP_STATE_FILE = DATA_DIR / 'app_state.json'
PRICE_CACHE_FILE = DATA_DIR / 'price_cache.json'  # legacy - superseded by market_data.json
MARKET_DATA_FILE = DATA_DIR / 'market_data.json'
LAYOUT_FILE = DATA_DIR / 'dashboard_layout.json'
LOGO_PATH = resource_path('assets', 'vector_full.png')
TASKBAR_LOGO_PATH = resource_path('assets', 'vector_taskbar.png')

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
    },
    'monte_carlo': {
        'projection_period': '1 year',
        'simulations': 500,
    },
}

DEFAULT_APP_STATE = {
    'onboarding_complete': False,
    'first_launch_date': None,
}

DEFAULT_POSITIONS = []
DEFAULT_PRICE_CACHE = {}
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
    'SPY', 'VOO', 'VTI', 'IVV', 'QQQ', 'VT', 'VXUS', 'ITOT', 'SCHB',
    'VEA', 'VWO', 'SPDW', 'IEFA', 'EFA', 'SCHX', 'SCHD', 'VIG', 'MGK',
    'QUAL', 'MOAT', 'RSP', 'DGRO', 'VYM', 'HDV', 'NOBL',
})

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

# Representative tickers per sector — used for the underrepresented-sector signal.
SECTOR_SUGGESTIONS: dict[str, list[str]] = {
    'Technology':             ['AAPL', 'MSFT', 'GOOGL'],
    'Healthcare':             ['JNJ', 'UNH', 'PFE'],
    'Consumer Defensive':     ['PG', 'KO', 'WMT'],
    'Financial Services':     ['JPM', 'V', 'MA'],
    'Financials':             ['JPM', 'V', 'MA'],
    'Industrials':            ['HON', 'CAT', 'UNP'],
    'Energy':                 ['XOM', 'CVX', 'COP'],
    'Consumer Cyclical':      ['AMZN', 'HD', 'MCD'],
    'Communication Services': ['GOOGL', 'META', 'DIS'],
    'Utilities':              ['NEE', 'SO', 'DUK'],
    'Real Estate':            ['AMT', 'PLD', 'O'],
    'Basic Materials':        ['LIN', 'APD', 'SHW'],
}
