"""Load user risk tier and return threshold overrides for analyzers."""

from __future__ import annotations

from typing import Any

from vector.constants import DEFAULT_RISK_PROFILES, DEFAULT_SETTINGS

# Shipped lens-signal defaults. An override is only applied when the user has
# *changed* a value away from these — otherwise the chosen risk tier drives the
# threshold. Applying the shipped defaults unconditionally (as before) clobbered
# the per-tier thresholds in DEFAULT_RISK_PROFILES with a single cross-tier
# value, flattening Conservative/Moderate/Aggressive and even inverting their
# ordering (e.g. concentration moderate=35 > high=30 on the Conservative tier).
_LENS_SIGNAL_DEFAULTS: dict[str, Any] = DEFAULT_SETTINGS.get('lens_signals', {})


def _changed(ls: dict[str, Any], key: str) -> bool:
    """True when the user set ``key`` to something other than the shipped default."""
    if key not in ls:
        return False
    default = _LENS_SIGNAL_DEFAULTS.get(key)
    if default is None:
        return True
    try:
        return float(ls[key]) != float(default)
    except (TypeError, ValueError):
        return ls[key] != default


def load_risk_profile(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Return a dict of threshold overrides keyed by analyzer name.

    Reads ``risk_tier`` from settings (default ``"regular"``), loads the
    matching profile from ``DEFAULT_RISK_PROFILES``, then applies any
    per-analyzer overrides the user has *deliberately changed* in
    ``settings["lens_signals"]`` (values left at the shipped default defer to
    the tier so the risk-tier selection is meaningful — see ``_changed``).
    """
    tier: str = settings.get('risk_tier', 'regular')
    if tier not in DEFAULT_RISK_PROFILES:
        tier = 'regular'

    profile: dict[str, Any] = {
        'tier': tier,
        **{k: dict(v) if isinstance(v, dict) else v
           for k, v in DEFAULT_RISK_PROFILES[tier].items()},
    }

    # Apply user overrides from Settings → Lens Signal Thresholds, but only when
    # the user has changed them from the shipped defaults (see module docstring).
    ls = settings.get('lens_signals', {})
    if ls:
        # Map settings keys → analyzer threshold overrides
        if _changed(ls, 'stock_concentration_pct'):
            profile.setdefault('concentration', {})
            profile['concentration']['moderate'] = float(ls['stock_concentration_pct'])
        if _changed(ls, 'sector_concentration_pct'):
            profile.setdefault('concentration', {})
            profile['concentration']['sector_moderate'] = float(ls['sector_concentration_pct'])
        if _changed(ls, 'steep_downtrend_pct'):
            profile.setdefault('slope', {})
            profile['slope']['high'] = float(ls['steep_downtrend_pct'])
        if _changed(ls, 'high_beta_threshold'):
            profile.setdefault('beta', {})
            profile['beta']['high'] = float(ls['high_beta_threshold'])
        if _changed(ls, 'stock_vol_threshold_pct'):
            profile.setdefault('volatility', {})
            profile['volatility']['high'] = float(ls['stock_vol_threshold_pct'])
        if _changed(ls, 'dead_weight_pct'):
            profile['dead_weight_pct'] = float(ls['dead_weight_pct'])
        if _changed(ls, 'loss_threshold'):
            profile.setdefault('performance', {})
            profile['performance']['moderate'] = float(ls['loss_threshold'])
        if _changed(ls, 'winner_drift_multiple'):
            profile['winner_drift_multiple'] = float(ls['winner_drift_multiple'])

    return profile
