from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from dragonboat_ai.futures_agent.infrastructure.database.base import to_db_datetime
from dragonboat_ai.futures_agent.infrastructure.database.models import FutCalendarDayORM


class SqlAlchemyCalendarStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def add_day(
        self,
        *,
        exchange: str,
        version: str,
        trading_date: date,
        is_trading_day: bool,
        available_at: datetime,
        revision_no: int,
        published_at: datetime | None = None,
        source: str | None = None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.add(
                FutCalendarDayORM(
                    exchange=exchange.upper(),
                    version=version,
                    trading_date=trading_date,
                    is_trading_day=is_trading_day,
                    available_at=to_db_datetime(available_at),
                    revision_no=revision_no,
                    published_at=to_db_datetime(published_at) if published_at else None,
                    source=source,
                )
            )

    def is_trading_day(
        self,
        *,
        exchange: str,
        trading_date: date,
        as_of: datetime,
    ) -> bool | None:
        cutoff = to_db_datetime(as_of)
        ranked = (
            select(
                FutCalendarDayORM.day_id.label("day_id"),
                func.row_number()
                .over(
                    partition_by=(FutCalendarDayORM.exchange, FutCalendarDayORM.trading_date),
                    order_by=(
                        FutCalendarDayORM.available_at.desc(),
                        FutCalendarDayORM.revision_no.desc(),
                    ),
                )
                .label("revision_rank"),
            )
            .where(
                FutCalendarDayORM.exchange == exchange.upper(),
                FutCalendarDayORM.trading_date == trading_date,
                FutCalendarDayORM.available_at <= cutoff,
            )
            .subquery()
        )
        stmt = (
            select(FutCalendarDayORM.is_trading_day)
            .join(ranked, FutCalendarDayORM.day_id == ranked.c.day_id)
            .where(ranked.c.revision_rank == 1)
        )
        with self.session_factory() as session:
            return session.scalar(stmt)
