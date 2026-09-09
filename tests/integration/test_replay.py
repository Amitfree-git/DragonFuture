from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.market_data import DailyBar
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.research.evaluation import summarize_direction_buckets
from dragonboat_ai.futures_agent.research.replay import (
    attach_research_labels,
    next_session_label,
    purge_overlapping_labels,
    replay,
    walk_forward_splits,
)

from tests.support import seed_reference_market


def test_next_session_label_does_not_use_signal_close() -> None:
    dates = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)]
    index = {day: Decimal(str(100 + i * 10)) for i, day in enumerate(dates)}
    # If signal close were used, 9/1 -> 9/2 would be 10%. Executable starts 9/2 -> 9/3 = 110/120?
    # start is next session (9/2=110), horizon 1 ends 9/3=120 -> 120/110-1
    label = next_session_label(index, dates, date(2026, 9, 1), 1)
    assert label == float(Decimal("120") / Decimal("110") - 1)
    naive = float(Decimal("110") / Decimal("100") - 1)
    assert label != naive


def test_purge_overlapping_labels_clears_horizon_overlap() -> None:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(10)]
    kept = purge_overlapping_labels(days, horizon=3)
    gaps = [(kept[i] - kept[i - 1]).days for i in range(1, len(kept))]
    assert all(gap > 3 for gap in gaps)


def test_walk_forward_keeps_train_validate_test_apart() -> None:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(40)]
    splits = walk_forward_splits(days, train_days=10, validate_days=5, test_days=5, embargo_days=5,max_label_horizon=5)
    assert splits
    train, validate, test = splits[0]
    assert train[-1] < validate[0] < test[0]
    assert (test[0] - validate[-1]).days > 1


@pytest.mark.integration
def test_replay_matches_online_and_ignores_future_bars(database) -> None:
    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
    )
    as_of = fixture["as_of"]
    online = analyst.analyze(
        AnalysisRequest(symbol="RB", exchange="SHFE", as_of=as_of, include_narrative=False)
    )
    records = replay(
        analyst,
        symbol="RB",
        exchange="SHFE",
        as_of_sequence=[as_of],
        include_narrative=False,
    )
    assert records[0].analysis.core_result_hash == online.core_result_hash

    future_bar_date = as_of.date() + timedelta(days=3)
    market_repo.add_daily_bar(
        DailyBar(
            contract_id=fixture["rb2701"].contract_id,
            contract="RB2701",
            trading_date=future_bar_date,
            open=Decimal("9999"),
            high=Decimal("9999"),
            low=Decimal("9999"),
            close=Decimal("9999"),
            settlement=Decimal("9999"),
            previous_settlement=None,
            volume=1,
            turnover=None,
            open_interest=1,
            upper_limit=None,
            lower_limit=None,
            revision_no=1,
            available_at=datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
            source="future-perturbation",
            payload_hash="future-perturbation",
        )
    )
    replayed = analyst.analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=as_of,
            include_narrative=False,
            force_refresh=True,
        )
    )
    assert replayed.core_result_hash == online.core_result_hash
    buckets = summarize_direction_buckets(records, "research_return_5d")
    assert buckets
    labelled = attach_research_labels(
        records,
        [(as_of.date(), "RB2701", Decimal("3500")), (as_of.date() + timedelta(days=1), "RB2701", Decimal("3510"))],
    )
    assert "research_return_5d" in labelled[0].labels
