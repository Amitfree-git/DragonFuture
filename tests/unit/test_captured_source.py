from pathlib import Path

from dragonboat_ai.futures_agent.infrastructure.ingestion.captured import CapturedFuturesSource


def test_captured_source_filters_product_and_date_window(tmp_path: Path) -> None:
    root = tmp_path / "capture"
    root.mkdir()
    (root / "fut_basic.json").write_text(
        """[
          {"ts_code":"RB2701.SHF","symbol":"RB2701","exchange":"SHFE","fut_code":"RB","name":"螺纹钢2701","list_date":"20260116","delist_date":"20270115","d_month":"202701"},
          {"ts_code":"AU2412.SHF","symbol":"AU2412","exchange":"SHFE","fut_code":"AU","name":"黄金2412","list_date":"20240116","delist_date":"20241216","d_month":"202412"}
        ]""",
        encoding="utf-8",
    )
    (root / "fut_daily.json").write_text(
        """{
          "RB2701.SHF": [
            {"ts_code":"RB2701.SHF","trade_date":"20260901","settle":3175,"vol":1,"oi":1,"open":3175,"high":3175,"low":3175,"close":3175},
            {"ts_code":"RB2701.SHF","trade_date":"20260904","settle":3160,"vol":1,"oi":1,"open":3160,"high":3160,"low":3160,"close":3160}
          ]
        }""",
        encoding="utf-8",
    )
    source = CapturedFuturesSource(root)
    contracts = source.list_contracts(product="RB", exchange="SHFE")
    assert [row["ts_code"] for row in contracts] == ["RB2701.SHF"]
    bars = source.fetch_daily_bars(ts_code="RB2701.SHF", start="20260902", end="20260904")
    assert [row["trade_date"] for row in bars] == ["20260904"]
