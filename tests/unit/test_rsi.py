from dragonboat_ai.futures_agent.features.statistics import rsi


def test_rsi_wilder_initial_13_up_1_down() -> None:
    prices = [100.0]
    for _ in range(13):
        prices.append(prices[-1] + 1)
    prices.append(prices[-1] - 1)
    assert rsi(prices, 14) == 92.85714285714286


def test_rsi_all_gains_is_100() -> None:
    prices = [float(index) for index in range(15)]
    assert rsi(prices, 14) == 100.0


def test_rsi_all_losses_is_0() -> None:
    prices = [float(20 - index) for index in range(15)]
    assert rsi(prices, 14) == 0.0


def test_rsi_all_unchanged_is_50() -> None:
    prices = [100.0] * 15
    assert rsi(prices, 14) == 50.0


def test_rsi_wilder_smoothing_differs_from_last_window_sma() -> None:
    prices = [100.0]
    for _ in range(14):
        prices.append(prices[-1] + 1.0)
    for _ in range(14):
        prices.append(prices[-1] - 1.0)
    ratio = (13.0 / 14.0) ** 14
    expected = 100.0 - 100.0 / (1.0 + ratio / (1.0 - ratio))
    result = rsi(prices, 14)
    assert result is not None
    assert abs(result - expected) <= 1e-9
    assert result != 0.0
