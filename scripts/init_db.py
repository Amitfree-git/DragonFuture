from __future__ import annotations

import argparse

from dragonboat_ai.futures_agent.infrastructure.database.schema import create_schema


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default="sqlite:///data/futures_agent.db")
    args = parser.parse_args()
    create_schema(args.database_url)
    print(f"Initialized {args.database_url}")


if __name__ == "__main__":
    main()
