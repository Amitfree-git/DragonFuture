from __future__ import annotations

from dragonboat_ai.futures_agent.domain.enums import Stance
from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis, NarrativeOutput


class TemplateNarrativeGenerator:
    """Deterministic fallback narrative. It never changes model outputs."""

    def generate(self, core_result: FuturesMarketAnalysis) -> NarrativeOutput:
        bullish = [
            f"{item.claim} [evidence_id={item.evidence_id}]"
            for item in core_result.evidence
            if item.stance is Stance.BULLISH
        ]
        bearish = [
            f"{item.claim} [evidence_id={item.evidence_id}]"
            for item in core_result.evidence
            if item.stance is Stance.BEARISH
        ]
        conflicts = self._conflicts(core_result)
        risk_items = [
            item.description
            for item in sorted(core_result.risk.items, key=lambda risk: risk.severity, reverse=True)
            if item.severity >= 30.0 or item.hard_gate
        ]
        invalidations = [item.description for item in core_result.invalidation_conditions]
        direction = core_result.direction.label.value
        action = core_result.opportunity.action.value
        executive_summary = (
            f"{core_result.request.symbol}/{core_result.selected_contract}："
            f"方向={direction}，机会={action}，"
            f"置信度={core_result.confidence.score:.1f}，风险={core_result.risk.level.value}。"
        )
        market_structure = (
            f"主要状态为 {core_result.regime.primary}；"
            f"次级状态为 {', '.join(core_result.regime.secondary) or 'none'}；"
            f"波动率状态为 {core_result.regime.volatility_regime}。"
        )
        final_conclusion = (
            f"方向判断为 {direction}，但应独立服从机会与风险门槛；"
            f"当前研究动作是 {action}，不构成直接下单指令。"
        )
        return NarrativeOutput(
            executive_summary=executive_summary,
            market_structure=market_structure,
            bullish_case=bullish[:5],
            bearish_case=bearish[:5],
            conflict_analysis=conflicts,
            risk_summary=risk_items[:5],
            invalidation_summary=invalidations,
            final_conclusion=final_conclusion,
        )

    @staticmethod
    def _conflicts(result: FuturesMarketAnalysis) -> list[str]:
        if result.direction.score is None:
            return ["方向数据不足，未进行因子一致性解释。"]
        direction_sign = 1 if result.direction.score > 0 else -1
        conflicts: list[str] = []
        for factor in result.factors:
            if factor.score is None or abs(factor.score) < 20:
                continue
            if factor.score * direction_sign < 0:
                conflicts.append(
                    f"{factor.factor.value} 分数 {factor.score:.1f} 与综合方向相反。"
                )
        return conflicts or ["未发现达到阈值的实质性方向冲突。"]
