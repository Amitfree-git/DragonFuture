from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from dragonboat_ai.futures_agent.contracts.research_returns import same_contract_return_index
from dragonboat_ai.futures_agent.contracts.continuous_series import RawContinuousPoint
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest, FuturesMarketAnalysis


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    as_of: datetime
    analysis: FuturesMarketAnalysis
    labels: dict[str, float | None]


def replay(
    analyst,
    *,
    symbol: str,
    exchange: str,
    as_of_sequence: list[datetime],
    horizon: str = "swing",
    include_narrative: bool = False,
    frozen_model: bool = True,
) -> list[ReplayRecord]:
    """Run the frozen analyst on each as_of independently.

    This is point-in-time replay of the online function, not a trading simulator.
    """
    if not frozen_model:
        raise ValueError("replay requires a frozen model; do not retune during replay")
    records: list[ReplayRecord] = []
    for as_of in as_of_sequence:
        request = AnalysisRequest(
            symbol=symbol,
            exchange=exchange,
            as_of=as_of,
            horizon=horizon,
            include_narrative=include_narrative,
        )
        analysis = analyst.analyze(request)
        records.append(
            ReplayRecord(
                as_of=as_of,
                analysis=analysis,
                labels={},
            )
        )
    return records


def attach_research_labels(
    records: list[ReplayRecord],
    prices: list[tuple[date, str, Decimal]],
    horizons: tuple[int, ...] = (5, 20, 60),
) -> list[ReplayRecord]:
    points = [RawContinuousPoint(day, contract, price) for day, contract, price in prices]
    index = same_contract_return_index(points, [])
    by_date = {item.trading_date: item.index_value for item in index}
    dates = [item.trading_date for item in index]
    labelled: list[ReplayRecord] = []
    for record in records:
        signal_day = record.as_of.date()
        labels: dict[str, float | None] = {}
        for horizon in horizons:
            labels[f"research_return_{horizon}d"] = next_session_label(by_date, dates, signal_day, horizon)
        labelled.append(
            ReplayRecord(as_of=record.as_of, analysis=record.analysis, labels=labels)
        )
    return labelled


def next_session_label(
    index_by_date: dict[date, Decimal],
    ordered_dates: list[date],
    signal_day: date,
    horizon: int,
) -> float | None:
    """Label uses the next session as the earliest executable price, not the signal close."""
    if signal_day not in index_by_date or horizon < 1:
        return None
    try:
        signal_index = ordered_dates.index(signal_day)
    except ValueError:
        return None
    start_index = signal_index + 1
    end_index = start_index + horizon
    if end_index >= len(ordered_dates) or start_index >= len(ordered_dates):
        return None
    window = [index_by_date.get(day) for day in ordered_dates[start_index:end_index+1]]
    if any(value is None or value <= 0 for value in window):
        return None
    start = index_by_date[ordered_dates[start_index]]
    end = index_by_date[ordered_dates[end_index]]
    if start == 0:
        return None
    return float(end / start - 1)


def walk_forward_splits(
    dates: list[date],
    *,
    train_days: int,
    validate_days: int,
    test_days: int,
    embargo_days: int,
    max_label_horizon: int = 60,
) -> list[tuple[list[date], list[date], list[date]]]:
    if min(train_days, validate_days, test_days) <= 0 or embargo_days < 0:
        raise ValueError("positive window lengths and nonnegative embargo required")
    if dates != sorted(set(dates)):
        raise ValueError("dates must be sorted unique trading sessions")
    # Each label starts at t+1 and ends at t+1+h. One additional
    # session separates its end from the next evaluation partition.
    if max_label_horizon < 1:
        raise ValueError("max_label_horizon must be positive")
    gap = max(embargo_days, max_label_horizon) + 1
    splits = []
    start = 0
    width = train_days + validate_days + test_days + 2 * gap
    while start + width <= len(dates):
        train = dates[start:start + train_days]
        val_start = start + train_days + gap
        validate = dates[val_start:val_start + validate_days]
        test_start = val_start + validate_days + gap
        test = dates[test_start:test_start + test_days]
        splits.append((train, validate, test))
        start += test_days
    return splits


def purge_overlapping_labels(
    labelled_dates: list[date],
    *,
    horizon: int,
    ordered_sessions: list[date] | None = None,
    cutoff: date | None = None,
) -> list[date]:
    """Keep only labels ending before cutoff, measured in trading sessions.

    Without a cutoff this only returns disjoint windows for descriptive
    statistics; it is not a substitute for split-boundary purging.
    """
    if horizon < 1:
        raise ValueError("horizon must be positive")
    sessions = ordered_sessions if ordered_sessions is not None else labelled_dates
    if sessions != sorted(set(sessions)):
        raise ValueError("sessions must be sorted and unique")
    positions = {day: i for i, day in enumerate(sessions)}
    kept = []
    previous_end = -1
    for day in sorted(set(labelled_dates)):
        if day not in positions:
            raise ValueError("label date missing from trading sessions")
        start = positions[day] + 1
        end = start + horizon
        if cutoff is not None:
            if end < len(sessions) and sessions[end] < cutoff:
                kept.append(day)
        elif start > previous_end:
            kept.append(day)
            previous_end = end
    return kept


def utc_days_ending(end: datetime, count: int) -> list[datetime]:
    days: list[datetime] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor = cursor - timedelta(days=1)
    return list(reversed(days))
