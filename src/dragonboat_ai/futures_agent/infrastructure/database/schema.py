from __future__ import annotations

import argparse

from .base import Base
from .session import create_sqlite_engine


def create_schema(database_url: str) -> None:
    # Import model metadata before create_all.
    from . import models as _models  # noqa: F401

    engine = create_sqlite_engine(database_url)
    Base.metadata.create_all(engine)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the futures-agent SQLite schema")
    parser.add_argument(
        "--database-url",
        default="sqlite:///data/futures_agent.db",
    )
    args = parser.parse_args()
    create_schema(args.database_url)


if __name__ == "__main__":
    main()
