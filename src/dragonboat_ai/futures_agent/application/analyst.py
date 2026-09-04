from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from dragonboat_ai.futures_agent.domain.models import (
    AnalysisRequest,
    AnalysisVersions,
    FuturesMarketAnalysis,
)
from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
from dragonboat_ai.futures_agent.invalidation.engine import InvalidationEngine
from dragonboat_ai.futures_agent.narrative.fallback import TemplateNarrativeGenerator
from dragonboat_ai.futures_agent.ports.repositories import AnalysisRepository
from dragonboat_ai.futures_agent.ports.services import NarrativeGenerator
from dragonboat_ai.futures_agent.regime.classifier import RuleBasedRegimeClassifier
from dragonboat_ai.futures_agent.scoring.confidence_engine import ConfidenceEngine
from dragonboat_ai.futures_agent.scoring.config import ScoringConfig
from dragonboat_ai.futures_agent.scoring.data_quality import DataQualityEvaluator
from dragonboat_ai.futures_agent.scoring.direction_engine import DirectionEngine
from dragonboat_ai.futures_agent.scoring.factor_engine import DeterministicFactorEngine
from dragonboat_ai.futures_agent.scoring.opportunity_engine import OpportunityEngine
from dragonboat_ai.futures_agent.scoring.risk_engine import RiskEngine


class FuturesMarketAnalyst:
    def __init__(
        self,
        *,
        context_builder,
        analysis_repository: AnalysisRepository,
        config: ScoringConfig | None = None,
        feature_engine: ReferenceFeatureEngine | None = None,
        factor_engine: DeterministicFactorEngine | None = None,
        regime_classifier: RuleBasedRegimeClassifier | None = None,
        direction_engine: DirectionEngine | None = None,
        confidence_engine: ConfidenceEngine | None = None,
        risk_engine: RiskEngine | None = None,
        opportunity_engine: OpportunityEngine | None = None,
        invalidation_engine: InvalidationEngine | None = None,
        data_quality_evaluator: DataQualityEvaluator | None = None,
        narrative_generator: NarrativeGenerator | None = None,
        versions: AnalysisVersions | None = None,
    ) -> None:
        self.config = config or ScoringConfig.default()
        self.context_builder = context_builder
        self.analysis_repository = analysis_repository
        self.feature_engine = feature_engine or ReferenceFeatureEngine()
        self.factor_engine = factor_engine or DeterministicFactorEngine()
        self.regime_classifier = regime_classifier or RuleBasedRegimeClassifier(self.config)
        self.direction_engine = direction_engine or DirectionEngine(self.config)
        self.confidence_engine = confidence_engine or ConfidenceEngine(self.config)
        self.risk_engine = risk_engine or RiskEngine(self.config)
        self.opportunity_engine = opportunity_engine or OpportunityEngine(self.config)
        self.invalidation_engine = invalidation_engine or InvalidationEngine()
        self.data_quality_evaluator = data_quality_evaluator or DataQualityEvaluator()
        self.narrative_generator = narrative_generator or TemplateNarrativeGenerator()
        config_hash = self.config.fingerprint()
        base_versions = versions or AnalysisVersions(
            schema_version="1.0.0",
            data_version="point_in_time_v1",
            feature_set_version="futures_features_v1",
            factor_model_version="futures_factors_v1",
            score_config_version="futures_scores_v1",
            score_config_hash=config_hash,
            regime_rule_version="futures_regime_v1",
            prompt_version="template_narrative_v1",
            code_commit=None,
        )
        if base_versions.score_config_hash not in {"", config_hash}:
            raise ValueError(
                "AnalysisVersions.score_config_hash does not match the supplied ScoringConfig"
            )
        self.versions = base_versions.model_copy(
            update={"score_config_hash": config_hash}
        )

    def analyze(self, request: AnalysisRequest) -> FuturesMarketAnalysis:
        # `force_refresh` is an execution-control flag, not part of the
        # persisted analytical information set.
        canonical_request = request.model_copy(update={"force_refresh": False})
        request_hash = self._request_hash(canonical_request)
        version_hash = self._version_hash(self.versions)
        context = self.context_builder.build(canonical_request)

        if not request.force_refresh:
            cached = self.analysis_repository.find_cached(
                request_hash=request_hash,
                input_data_hash=context.input_data_hash,
                version_hash=version_hash,
            )
            if cached is not None:
                return cached

        data_quality = self.data_quality_evaluator.assess(context)
        metrics = self.feature_engine.compute(context)
        factors, evidence = self.factor_engine.score(context, metrics)
        regime = self.regime_classifier.classify(factors, metrics)
        direction = self.direction_engine.assess(canonical_request.horizon, factors)
        confidence = self.confidence_engine.assess(
            as_of=canonical_request.as_of,
            factors=factors,
            direction=direction,
            metrics=metrics,
            data_quality=data_quality,
        )
        risk = self.risk_engine.assess(
            context=context,
            metrics=metrics,
            data_quality=data_quality,
        )
        opportunity = self.opportunity_engine.assess(
            direction=direction,
            regime=regime,
            risk=risk,
            confidence=confidence,
            metrics=metrics,
        )
        invalidation = self.invalidation_engine.build_conditions(
            direction=direction,
            regime=regime,
            metrics=metrics,
        )

        generated_at = datetime.now(timezone.utc)
        core = FuturesMarketAnalysis(
            analysis_id=str(uuid4()),
            request_hash=request_hash,
            input_data_hash=context.input_data_hash,
            request=canonical_request,
            selected_contract=context.selected_contract,
            source_contracts=list(context.source_contracts),
            generated_at=generated_at,
            data_cutoff=canonical_request.as_of,
            data_quality=data_quality,
            factors=factors,
            regime=regime,
            direction=direction,
            confidence=confidence,
            opportunity=opportunity,
            risk=risk,
            metrics=metrics,
            evidence=evidence,
            invalidation_conditions=invalidation,
            versions=self.versions,
            core_result_hash="pending",
            narrative=None,
        )
        core = core.model_copy(update={"core_result_hash": self._core_hash(core)})

        if canonical_request.include_narrative:
            try:
                narrative = self.narrative_generator.generate(core)
            except Exception:
                narrative = TemplateNarrativeGenerator().generate(core)
            core = core.model_copy(update={"narrative": narrative})

        return self.analysis_repository.save(core, version_hash=version_hash)

    @staticmethod
    def _request_hash(request: AnalysisRequest) -> str:
        payload = request.model_dump(
            mode="json",
            exclude={"force_refresh"},
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _version_hash(versions: AnalysisVersions) -> str:
        payload = versions.model_dump(mode="json")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _core_hash(result: FuturesMarketAnalysis) -> str:
        payload = result.model_dump(
            mode="json",
            exclude={"analysis_id", "generated_at", "narrative", "core_result_hash"},
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
