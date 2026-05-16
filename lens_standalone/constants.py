"""Constants copied from vector.constants — only what Lens actually needs."""

from __future__ import annotations


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

# Well-known lower-beta names per sector.
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

# Default Risk Profiles for the Lens engine.
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
