from datetime import date, datetime
from types import SimpleNamespace

import pytest

from dragonboat_ai.futures_agent.operations.observability import operational_alerts, summarize_journal
from dragonboat_ai.futures_agent.operations.shadow import ShadowFault, ShadowJournal, ShadowRunner
from dragonboat_ai.futures_agent.operations.watermark import SHANGHAI

SESSION = date(2026, 9, 4)
NOW = datetime(2026, 9, 4, 16, 0, tzinfo=SHANGHAI)
SETTLEMENT = datetime(2026, 9, 4, 15, 0, tzinfo=SHANGHAI)


def _analysis(*, action: str = "long_candidate", hard_gate: bool = False):
    return SimpleNamespace(
        input_data_hash="input-hash",
        core_result_hash="core-hash",
        opportunity=SimpleNamespace(action=SimpleNamespace(value=action), hard_gate_reasons=()),
        risk=SimpleNamespace(hard_gate_triggered=hard_gate),
    )


def test_injected_faults_never_emit_candidates() -> None:
    runner = ShadowRunner(ShadowJournal())
    calls = {"n": 0}

    def analyze():
        calls["n"] += 1
        return _analysis()

    network = runner.run_session(
        exchange="SHFE",
        symbol="RB",
        session_date=SESSION,
        now=NOW,
        settlement_available_at=SETTLEMENT,
        analyze=analyze,
        fault=ShadowFault.NETWORK,
    )
    missing = runner.run_session(
        exchange="SHFE",
        symbol="RB",
        session_date=SESSION,
        now=NOW,
        settlement_available_at=SETTLEMENT,
        analyze=analyze,
        fault=ShadowFault.MISSING_FIELD,
    )
    stale = runner.run_session(
        exchange="SHFE",
        symbol="RB",
        session_date=SESSION,
        now=NOW,
        settlement_available_at=SETTLEMENT,
        analyze=analyze,
        fault=ShadowFault.STALE,
    )
    duplicate = runner.run_session(
        exchange="SHFE",
        symbol="RB",
        session_date=SESSION,
        now=NOW,
        settlement_available_at=SETTLEMENT,
        analyze=analyze,
        fault=ShadowFault.DUPLICATE_BATCH,
    )
    with pytest.raises(TimeoutError):
        runner.run_session(
            exchange="SHFE",
            symbol="RB",
            session_date=SESSION,
            now=NOW,
            settlement_available_at=SETTLEMENT,
            analyze=lambda: (_ for _ in ()).throw(TimeoutError("model")),
            fault=ShadowFault.TIMEOUT,
        )

    assert network.candidate_emitted is False and network.gap is True
    assert missing.candidate_emitted is False and missing.gap is True
    assert stale.candidate_emitted is False
    assert stale.watermark_status == "stale"
    assert duplicate.candidate_emitted is True
    assert calls["n"] == 2
    timeout = runner.journal.observations[-1]
    assert timeout.candidate_emitted is False
    assert timeout.gap is True
    assert all(
        not item.candidate_emitted
        for item in runner.journal.observations
        if item.fault in {"network", "missing_field", "stale", "timeout"}
    )
    assert runner.journal.gaps()
    metrics = summarize_journal(runner.journal)
    assert metrics.gaps >= 4
    assert "shadow_gap" in operational_alerts(runner.journal)


def test_too_early_does_not_call_analyze() -> None:
    runner = ShadowRunner()
    called = False

    def analyze():
        nonlocal called
        called = True
        return _analysis()

    observation = runner.run_session(
        exchange="SHFE",
        symbol="RB",
        session_date=SESSION,
        now=datetime(2026, 9, 4, 14, 0, tzinfo=SHANGHAI),
        settlement_available_at=SETTLEMENT,
        analyze=analyze,
    )
    assert called is False
    assert observation.candidate_emitted is False
    assert observation.gap is True
