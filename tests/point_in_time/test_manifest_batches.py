from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from dragonboat_ai.futures_agent.domain.market_data import DailyBar
from dragonboat_ai.futures_agent.infrastructure.database.manifest import (
    ManifestStatus,
    SqlAlchemyManifestStore,
)


def _bar(contract_id: int, *, batch_id: str | None) -> DailyBar:
    price = Decimal("3500")
    return DailyBar(
        contract_id=contract_id,
        contract="RB2701",
        trading_date=date(2026, 1, 2),
        open=price,
        high=price,
        low=price,
        close=price,
        settlement=price,
        previous_settlement=None,
        volume=100,
        turnover=None,
        open_interest=200,
        upper_limit=None,
        lower_limit=None,
        revision_no=1,
        available_at=datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc),
        source="tushare",
        payload_hash="payload-1",
        data_batch_id=batch_id,
    )


@pytest.mark.point_in_time
def test_uncommitted_batch_not_readable(database) -> None:
    repo = database["market_repository"]
    manifests = SqlAlchemyManifestStore(database["session_factory"])
    instrument_id = repo.get_or_create_instrument(exchange="SHFE", symbol="RB")
    contract = repo.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2701",
        expiry_date=date(2027, 1, 15),
    )
    pending = manifests.create(
        manifest_id="man-pending",
        source_policy="tushare_only",
        data_mode="final_only",
        status=ManifestStatus.PENDING,
    )
    repo.add_daily_bar(_bar(contract.contract_id, batch_id=pending.batch_id), data_batch_id=pending.batch_id)
    visible = repo.load_contract_bars(
        contract_id=contract.contract_id,
        as_of=datetime(2026, 1, 3, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )
    assert visible == ()


@pytest.mark.point_in_time
def test_committed_batch_is_readable(database) -> None:
    repo = database["market_repository"]
    manifests = SqlAlchemyManifestStore(database["session_factory"])
    instrument_id = repo.get_or_create_instrument(exchange="SHFE", symbol="RB")
    contract = repo.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2701",
        expiry_date=date(2027, 1, 15),
    )
    committed = manifests.create(
        manifest_id="man-ready",
        source_policy="tushare_only",
        data_mode="final_only",
        status=ManifestStatus.PENDING,
    )
    repo.add_daily_bar(_bar(contract.contract_id, batch_id=committed.batch_id), data_batch_id=committed.batch_id)
    manifests.commit(committed.manifest_id)
    visible = repo.load_contract_bars(
        contract_id=contract.contract_id,
        as_of=datetime(2026, 1, 3, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )
    assert len(visible) == 1
    assert visible[0].settlement == Decimal("3500")


@pytest.mark.point_in_time
def test_duplicate_batch_reingest_is_idempotent(database) -> None:
    manifests = SqlAlchemyManifestStore(database["session_factory"])
    first = manifests.archive_raw(
        provider="tushare",
        request_digest="req-1",
        response_hash="resp-1",
        received_at=datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc),
        license_id="tushare-test",
        storage_uri="file:///tmp/raw-1.json",
    )
    second = manifests.archive_raw(
        provider="tushare",
        request_digest="req-1",
        response_hash="resp-1",
        received_at=datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
        license_id="tushare-test",
        storage_uri="file:///tmp/raw-1.json",
    )
    assert first.archive_id == second.archive_id
