"""Macro-derived features from rates and FX data."""
from app.features.base import FeatureSnapshot


def build_macro_features(
    dxy_current: float,
    dxy_previous: float,
    yield_10y_current: float,
    yield_10y_previous: float,
    yield_2y_current: float,
    yield_2y_previous: float,
    real_rate_proxy: float,
) -> dict:
    """
    Compute macro features from FX and rates data.

    Args:
        dxy_current / dxy_previous: Current and prior DXY values.
        yield_*_current / *_previous: Current and prior yields.
        real_rate_proxy: Approximate real interest rate (nominal - inflation expectation).

    Returns:
        Dict of macro feature fields compatible with FeatureSnapshot.
    """
    dxy_change = (dxy_current - dxy_previous) / dxy_previous if dxy_previous else 0.0
    yield_10y_change = (yield_10y_current - yield_10y_previous) * 100  # convert to bp
    yield_curve_slope = yield_10y_current - yield_2y_current

    return {
        "dxy_change": dxy_change,
        "yield_10y_change": yield_10y_change,
        "real_rate_proxy": real_rate_proxy,
        "yield_curve_slope": yield_curve_slope,
    }
