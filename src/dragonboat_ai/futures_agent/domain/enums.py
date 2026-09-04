from __future__ import annotations

from enum import Enum


class AnalysisHorizon(str, Enum):
    SWING = "swing"
    POSITION = "position"


class FactorName(str, Enum):
    TREND = "trend"
    MOMENTUM = "momentum"
    POSITIONING = "positioning"
    TERM_STRUCTURE = "term_structure"


class ContextName(str, Enum):
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    ROLL_RISK = "roll_risk"
    PRICE_LIMIT_RISK = "price_limit_risk"
    DATA_QUALITY = "data_quality"


class DataStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"
    INSUFFICIENT = "insufficient"


class EvidenceKind(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class Stance(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class DirectionLabel(str, Enum):
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"
    INSUFFICIENT_DATA = "insufficient_data"


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class OpportunityAction(str, Enum):
    LONG_CANDIDATE = "long_candidate"
    SHORT_CANDIDATE = "short_candidate"
    WAIT_FOR_PULLBACK = "wait_for_pullback"
    WAIT_FOR_REBOUND = "wait_for_rebound"
    WAIT_FOR_BREAKOUT = "wait_for_breakout"
    NO_TRADE = "no_trade"
    INSUFFICIENT_DATA = "insufficient_data"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"
