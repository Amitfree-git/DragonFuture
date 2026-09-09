from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


class SeriesTypeMismatchError(ValueError):
    """Raised when a feature is evaluated on an incompatible price series."""


@dataclass(frozen=True, slots=True)
class RegisteredFeature:
    name: str
    formula: str
    unit: str
    window: int
    min_samples: int
    warmup: int
    series_type: str
    price_domain: str
    normalization: str
    dependencies: tuple[str, ...] = ()
    implemented: bool = True


def _feature(**kwargs) -> RegisteredFeature:
    return RegisteredFeature(**kwargs)


BASELINE_FEATURES: tuple[RegisteredFeature, ...] = (
    _feature(name="return_5d", formula="I_t/I_(t-5)-1", unit="ratio", window=5, min_samples=6, warmup=6, series_type="research_index", price_domain="positive", normalization="vol_scaled_tanh"),
    _feature(name="return_20d", formula="I_t/I_(t-20)-1", unit="ratio", window=20, min_samples=21, warmup=21, series_type="research_index", price_domain="positive", normalization="vol_scaled_tanh"),
    _feature(name="return_60d", formula="I_t/I_(t-60)-1", unit="ratio", window=60, min_samples=61, warmup=61, series_type="research_index", price_domain="positive", normalization="vol_scaled_tanh"),
    _feature(name="return_120d", formula="I_t/I_(t-120)-1", unit="ratio", window=120, min_samples=121, warmup=121, series_type="research_index", price_domain="positive", normalization="vol_scaled_tanh"),
    _feature(name="settlement_vs_ma20", formula="P/MA20-1", unit="ratio", window=20, min_samples=20, warmup=20, series_type="position_price", price_domain="positive", normalization="atr_tanh"),
    _feature(name="settlement_vs_ma60", formula="P/MA60-1", unit="ratio", window=60, min_samples=60, warmup=60, series_type="position_price", price_domain="positive", normalization="vol_scaled_tanh"),
    _feature(name="extension_atr", formula="(P-MA20)/ATR20", unit="atr", window=20, min_samples=21, warmup=21, series_type="selected_contract", price_domain="positive", normalization="tanh", dependencies=("settlement_vs_ma20",)),
    _feature(name="ma_structure", formula="price vs MA20/MA60 plus 5d MA slope", unit="score", window=60, min_samples=65, warmup=65, series_type="research_index", price_domain="positive", normalization="structure_score"),
    _feature(name="breakout_position_120d", formula="(I-min)/(max-min) over 120d", unit="ratio", window=120, min_samples=120, warmup=120, series_type="research_index", price_domain="positive", normalization="centered_clip"),
    _feature(name="rsi_14", formula="Wilder RSI(14)", unit="index", window=14, min_samples=15, warmup=15, series_type="research_index", price_domain="positive", normalization="centered_clip"),
    _feature(name="momentum_acceleration", formula="R5-R20/4", unit="ratio", window=20, min_samples=21, warmup=21, series_type="research_index", price_domain="positive", normalization="vol_scaled_tanh", dependencies=("return_5d", "return_20d")),
    _feature(name="contract_return_5d", formula="S_t/S_(t-5)-1", unit="ratio", window=5, min_samples=6, warmup=6, series_type="selected_contract", price_domain="positive", normalization="vol_scaled_tanh"),
    _feature(name="oi_change_5d", formula="OI_t/OI_(t-5)-1", unit="ratio", window=5, min_samples=6, warmup=6, series_type="selected_contract", price_domain="any", normalization="tanh"),
    _feature(name="volume_zscore_20d", formula="robust_z(volume, 20d history)", unit="zscore", window=20, min_samples=21, warmup=21, series_type="selected_contract", price_domain="any", normalization="tanh"),
    _feature(name="positioning_composite", formula="signed blend of contract return and OI change", unit="score", window=5, min_samples=6, warmup=6, series_type="selected_contract", price_domain="positive", normalization="clip", dependencies=("contract_return_5d", "oi_change_5d")),
    _feature(name="curve_slope", formula="log(F_near/F_far)*365/dte_gap", unit="annualized_log_spread", window=1, min_samples=1, warmup=1, series_type="real_contract_curve", price_domain="positive", normalization="tanh"),
    _feature(name="curve_slope_change_20d", formula="slope_t - slope_(t-20) same pair or tenor bucket", unit="annualized_log_spread", window=20, min_samples=20, warmup=20, series_type="real_contract_curve", price_domain="positive", normalization="robust_z_tanh", dependencies=("curve_slope",)),
    _feature(name="curve_curvature", formula="front_slope - back_slope", unit="annualized_log_spread", window=1, min_samples=1, warmup=1, series_type="real_contract_curve", price_domain="positive", normalization="robust_z_tanh"),
    _feature(name="realized_vol_20d", formula="stdev(log returns)*sqrt(252)", unit="annualized_ratio", window=20, min_samples=21, warmup=21, series_type="research_index", price_domain="positive", normalization="none"),
    _feature(name="realized_vol_60d", formula="stdev(log returns)*sqrt(252)", unit="annualized_ratio", window=60, min_samples=61, warmup=61, series_type="research_index", price_domain="positive", normalization="none"),
    _feature(name="volatility_percentile", formula="mid-rank percentile of RV20 vs prior history", unit="percentile", window=20, min_samples=20, warmup=21, series_type="research_index", price_domain="positive", normalization="percentile_signed", dependencies=("realized_vol_20d",)),
    _feature(name="volume_percentile", formula="mid-rank percentile of selected-contract volume", unit="percentile", window=252, min_samples=20, warmup=20, series_type="selected_contract", price_domain="any", normalization="percentile_signed"),
    _feature(name="open_interest_percentile", formula="mid-rank percentile of selected-contract OI", unit="percentile", window=252, min_samples=20, warmup=20, series_type="selected_contract", price_domain="any", normalization="percentile_signed"),
    _feature(name="contract_volume_share", formula="contract volume / eligible curve volume", unit="ratio", window=1, min_samples=1, warmup=1, series_type="real_contract_curve", price_domain="any", normalization="centered_clip"),
    _feature(name="contract_open_interest_share", formula="contract OI / eligible curve OI", unit="ratio", window=1, min_samples=1, warmup=1, series_type="real_contract_curve", price_domain="any", normalization="centered_clip"),
    _feature(name="liquidity_quality_score", formula="mean of volume/OI percentiles and shares", unit="score", window=252, min_samples=20, warmup=20, series_type="selected_contract", price_domain="any", normalization="centered_clip"),
    _feature(name="days_to_expiry", formula="tradable_until - as_of", unit="days", window=1, min_samples=1, warmup=1, series_type="contract_metadata", price_domain="any", normalization="none"),
    _feature(name="roll_risk_score", formula="step function of days_to_expiry", unit="risk_score", window=1, min_samples=1, warmup=1, series_type="contract_metadata", price_domain="any", normalization="risk_clip", dependencies=("days_to_expiry",)),
    _feature(name="price_limit_proximity_risk", formula="distance to exchange limits", unit="risk_score", window=1, min_samples=1, warmup=1, series_type="selected_contract", price_domain="positive", normalization="risk_clip"),
)

DEFERRED_FEATURES: tuple[RegisteredFeature, ...] = (
    _feature(name="adx_14", formula="Wilder ADX(14)", unit="index", window=14, min_samples=28, warmup=28, series_type="research_index", price_domain="positive", normalization="none", implemented=False),
    _feature(name="basis", formula="comparable spot minus selected futures", unit="price", window=1, min_samples=1, warmup=1, series_type="spot_basis", price_domain="any", normalization="none", implemented=False),
)

FEATURES_BY_NAME: dict[str, RegisteredFeature] = {
    item.name: item for item in BASELINE_FEATURES + DEFERRED_FEATURES
}


def available_features() -> tuple[RegisteredFeature, ...]:
    return tuple(item for item in BASELINE_FEATURES if item.implemented)


def available_feature_names() -> frozenset[str]:
    return frozenset(item.name for item in available_features())


def require_compatible_series(feature_name: str, series_type: str) -> RegisteredFeature:
    spec = FEATURES_BY_NAME[feature_name]
    if not spec.implemented:
        raise SeriesTypeMismatchError(f"{feature_name} is not in the current available feature set")
    if spec.series_type != series_type:
        raise SeriesTypeMismatchError(
            f"{feature_name} requires series_type={spec.series_type}, got {series_type}"
        )
    return spec


def registry_fingerprint() -> str:
    payload = [
        {
            "name": item.name,
            "formula": item.formula,
            "unit": item.unit,
            "window": item.window,
            "min_samples": item.min_samples,
            "warmup": item.warmup,
            "series_type": item.series_type,
            "price_domain": item.price_domain,
            "normalization": item.normalization,
            "dependencies": list(item.dependencies),
            "implemented": item.implemented,
        }
        for item in BASELINE_FEATURES + DEFERRED_FEATURES
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_registry() -> str:
    lines = ["# Feature registry", "", "| name | series | window | min_n | formula |", "|---|---|---:|---:|---|"]
    for item in available_features():
        lines.append(
            f"| {item.name} | {item.series_type} | {item.window} | {item.min_samples} | `{item.formula}` |"
        )
    lines.extend(["", "Deferred (not currently available): " + ", ".join(item.name for item in DEFERRED_FEATURES)])
    return "\n".join(lines) + "\n"
