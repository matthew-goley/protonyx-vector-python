"""Load user risk tier and return threshold overrides for analyzers."""

from __future__ import annotations

from typing import Any

from vector.constants import DEFAULT_RISK_PROFILES


def load_risk_profile(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Return a dict of threshold overrides keyed by analyzer name.

    Reads ``risk_tier`` from settings (default ``"regular"``), loads the
    matching profile from ``DEFAULT_RISK_PROFILES``, then applies any
    per-analyzer overrides the user has set in ``settings["lens_signals"]``.
    """
    tier: str = settings.get('risk_tier', 'regular')
    if tier not in DEFAULT_RISK_PROFILES:
        tier = 'regular'

    profile: dict[str, Any] = {
        'tier': tier,
        **{k: dict(v) if isinstance(v, dict) else v
           for k, v in DEFAULT_RISK_PROFILES[tier].items()},
    }

    # Apply user overrides from Settings → Lens Signal Thresholds
    ls = settings.get('lens_signals', {})
    if ls:
        # Map settings keys → analyzer threshold overrides
        if 'stock_concentration_pct' in ls:
            profile.setdefault('concentration', {})
            profile['concentration']['moderate'] = float(ls['stock_concentration_pct'])
        if 'sector_concentration_pct' in ls:
            profile.setdefault('concentration', {})
            profile['concentration']['sector_moderate'] = float(ls['sector_concentration_pct'])
        if 'steep_downtrend_pct' in ls:
            profile.setdefault('slope', {})
            profile['slope']['high'] = float(ls['steep_downtrend_pct'])
        if 'high_beta_threshold' in ls:
            profile.setdefault('beta', {})
            profile['beta']['high'] = float(ls['high_beta_threshold'])
        if 'stock_vol_threshold_pct' in ls:
            profile.setdefault('volatility', {})
            profile['volatility']['high'] = float(ls['stock_vol_threshold_pct'])
        if 'dead_weight_pct' in ls:
            profile['dead_weight_pct'] = float(ls['dead_weight_pct'])
        if 'loss_threshold' in ls:
            profile.setdefault('performance', {})
            profile['performance']['moderate'] = float(ls['loss_threshold'])
        if 'winner_drift_multiple' in ls:
            profile['winner_drift_multiple'] = float(ls['winner_drift_multiple'])

    return profile
