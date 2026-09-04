from __future__ import annotations

from typing import Any

from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis

SYSTEM_PROMPT_ZH = """
你是 DragonBoatAI 的期货市场分析叙事层。你的输入来自已经完成的确定性计算。

职责：
1. 将结构化结果转化为专业、克制、可审计的中文报告；
2. 解释多空证据之间的关系；
3. 明确区分事实、推断和假设；
4. 指出当前机会质量、主要风险和判断失效条件。

硬性规则：
- 输入中的数值、评分、标签、证据和失效条件是唯一事实源；不得自行计算或修改。
- 不得补充输入中不存在的库存、资金、政策、天气、新闻或宏观事实。
- bullish_case 和 bearish_case 的每一条必须包含至少一个形如
  [evidence_id=<输入中的ID>] 的引用。
- inference 必须写成推断；hypothesis 必须使用“可能、或许、倾向于”等不确定表达。
- 不得把持仓变化直接表述成某一方主动开仓，除非输入证据明确支持。
- Direction 与 Opportunity 必须分开表述；偏多或偏空不等于适合立即交易。
- 不得给出直接下单指令、仓位比例、收益承诺或输入外的精确价格。
- 输出只能符合 NarrativeOutput 结构，不得增加评分字段。
""".strip()


def build_narrative_payload(result: FuturesMarketAnalysis) -> dict[str, Any]:
    """Build the bounded payload exposed to an external narrative model.

    Raw bar history is intentionally absent. The model receives only the
    deterministic state, auditable observations and permitted evidence.
    """

    return {
        "analysis_id": result.analysis_id,
        "instrument": {
            "symbol": result.request.symbol,
            "exchange": result.request.exchange,
            "contract": result.selected_contract,
            "as_of": result.request.as_of.isoformat(),
            "horizon": result.request.horizon.value,
        },
        "data_quality": result.data_quality.model_dump(mode="json"),
        "regime": result.regime.model_dump(mode="json"),
        "direction": result.direction.model_dump(mode="json"),
        "confidence": result.confidence.model_dump(mode="json"),
        "opportunity": result.opportunity.model_dump(mode="json"),
        "risk": result.risk.model_dump(mode="json"),
        "factors": [item.model_dump(mode="json") for item in result.factors],
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "invalidation_conditions": [
            item.model_dump(mode="json") for item in result.invalidation_conditions
        ],
    }
