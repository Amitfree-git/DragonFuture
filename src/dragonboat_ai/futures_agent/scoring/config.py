from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    direction_weights: dict[str, dict[str, float]]
    minimum_available_weight: float
    labels: dict[str, float]
    confidence_weights: dict[str, float]
    opportunity_weights: dict[str, float]
    hard_gates: dict[str, float]
    volatility_thresholds: dict[str, float]
    main_contract: dict[str, float]

    def __post_init__(self) -> None:
        direction_keys = {"trend", "momentum", "positioning", "term_structure"}
        if set(self.direction_weights) != {"swing", "position"}:
            raise ValueError("direction_weights must define swing and position horizons")
        for horizon, weights in self.direction_weights.items():
            self._require_keys(f"direction.{horizon}", weights, direction_keys)
            self._validate_weights(f"direction.{horizon}", weights)

        confidence_keys = {
            "coverage",
            "freshness",
            "agreement",
            "data_quality",
            "historical_calibration",
        }
        self._require_keys("confidence", self.confidence_weights, confidence_keys)
        self._validate_weights("confidence", self.confidence_weights)

        opportunity_keys = {
            "direction_strength",
            "entry_quality",
            "regime_fit",
            "liquidity_quality",
            "risk_penalty",
        }
        self._require_keys("opportunity", self.opportunity_weights, opportunity_keys)
        positive_opportunity = {
            key: value
            for key, value in self.opportunity_weights.items()
            if key != "risk_penalty"
        }
        self._validate_weights("opportunity positive components", positive_opportunity)
        if self.opportunity_weights.get("risk_penalty", 0.0) < 0.0:
            raise ValueError("opportunity.risk_penalty must be non-negative")
        if not 0.0 <= self.minimum_available_weight <= 1.0:
            raise ValueError("minimum_available_weight must be between 0 and 1")

        required_labels = {
            "strong_bullish",
            "bullish",
            "bearish",
            "strong_bearish",
        }
        if set(self.labels) != required_labels:
            raise ValueError(f"labels must contain exactly {sorted(required_labels)}")
        if not (
            self.labels["strong_bearish"]
            < self.labels["bearish"]
            < self.labels["bullish"]
            < self.labels["strong_bullish"]
        ):
            raise ValueError("direction label thresholds must be strictly increasing")

        hard_gate_keys = {
            "risk_score",
            "confidence_score",
            "minimum_days_to_expiry",
            "minimum_direction_abs_score",
            "minimum_data_quality",
            "minimum_liquidity_quality",
        }
        self._require_keys("hard_gates", self.hard_gates, hard_gate_keys)
        if any(not 0.0 <= value <= 100.0 for key, value in self.hard_gates.items() if key != "minimum_days_to_expiry"):
            raise ValueError("score-like hard gates must be between 0 and 100")
        if self.hard_gates["minimum_days_to_expiry"] < 0.0:
            raise ValueError("minimum_days_to_expiry must be non-negative")

        volatility_keys = {"low_percentile", "high_percentile", "extreme_percentile"}
        self._require_keys("volatility", self.volatility_thresholds, volatility_keys)
        low = self.volatility_thresholds["low_percentile"]
        high = self.volatility_thresholds["high_percentile"]
        extreme = self.volatility_thresholds["extreme_percentile"]
        if not 0.0 <= low < high < extreme <= 100.0:
            raise ValueError("volatility percentiles must satisfy 0 <= low < high < extreme <= 100")

        main_contract_keys = {
            "exclude_days_to_expiry_below",
            "confirmation_days",
            "minimum_volume_share",
            "minimum_oi_share",
        }
        self._require_keys("main_contract", self.main_contract, main_contract_keys)
        if self.main_contract["exclude_days_to_expiry_below"] < 0.0:
            raise ValueError("main_contract expiry exclusion must be non-negative")
        confirmation_days = self.main_contract["confirmation_days"]
        if confirmation_days < 1.0 or not float(confirmation_days).is_integer():
            raise ValueError("main_contract.confirmation_days must be a positive integer")
        for key in ("minimum_volume_share", "minimum_oi_share"):
            if not 0.0 <= self.main_contract[key] <= 1.0:
                raise ValueError(f"main_contract.{key} must be between 0 and 1")

    def fingerprint(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _validate_weights(name: str, weights: dict[str, float]) -> None:
        if not weights:
            raise ValueError(f"{name} weights cannot be empty")
        if any(value < 0.0 for value in weights.values()):
            raise ValueError(f"{name} weights must be non-negative")
        if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"{name} weights must sum to 1.0")

    @staticmethod
    def _require_keys(name: str, values: dict[str, float], expected: set[str]) -> None:
        if set(values) != expected:
            raise ValueError(f"{name} must contain exactly {sorted(expected)}")

    @classmethod
    def default(cls) -> "ScoringConfig":
        return cls(
            direction_weights={
                "swing": {
                    "trend": 0.40,
                    "momentum": 0.25,
                    "positioning": 0.15,
                    "term_structure": 0.20,
                },
                "position": {
                    "trend": 0.45,
                    "momentum": 0.15,
                    "positioning": 0.10,
                    "term_structure": 0.30,
                },
            },
            minimum_available_weight=0.70,
            labels={
                "strong_bullish": 60.0,
                "bullish": 25.0,
                "bearish": -25.0,
                "strong_bearish": -60.0,
            },
            confidence_weights={
                "coverage": 0.30,
                "freshness": 0.20,
                "agreement": 0.25,
                "data_quality": 0.15,
                "historical_calibration": 0.10,
            },
            opportunity_weights={
                "direction_strength": 0.45,
                "entry_quality": 0.25,
                "regime_fit": 0.15,
                "liquidity_quality": 0.15,
                "risk_penalty": 0.35,
            },
            hard_gates={
                "risk_score": 80.0,
                "confidence_score": 45.0,
                "minimum_days_to_expiry": 7.0,
                "minimum_direction_abs_score": 25.0,
                "minimum_data_quality": 60.0,
                "minimum_liquidity_quality": 20.0,
            },
            volatility_thresholds={
                "low_percentile": 25.0,
                "high_percentile": 75.0,
                "extreme_percentile": 90.0,
            },
            main_contract={
                "exclude_days_to_expiry_below": 10.0,
                "confirmation_days": 2.0,
                "minimum_volume_share": 0.15,
                "minimum_oi_share": 0.15,
            },
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ScoringConfig":
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        direction = raw["direction"]
        return cls(
            direction_weights={
                "swing": {key: float(value) for key, value in direction["swing"].items()},
                "position": {key: float(value) for key, value in direction["position"].items()},
            },
            minimum_available_weight=float(direction["minimum_available_weight"]),
            labels={key: float(value) for key, value in raw["labels"].items()},
            confidence_weights={key: float(value) for key, value in raw["confidence"].items()},
            opportunity_weights={key: float(value) for key, value in raw["opportunity"].items()},
            hard_gates={key: float(value) for key, value in raw["hard_gates"].items()},
            volatility_thresholds={key: float(value) for key, value in raw["volatility"].items()},
            main_contract={key: float(value) for key, value in raw["main_contract"].items()},
        )
