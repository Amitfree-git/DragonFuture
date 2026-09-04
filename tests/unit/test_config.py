from dataclasses import replace

import pytest

from dragonboat_ai.futures_agent.scoring.config import ScoringConfig


def test_yaml_configuration_matches_reference_defaults() -> None:
    yaml_config = ScoringConfig.from_yaml("config/futures_v1.yaml")
    default_config = ScoringConfig.default()
    assert yaml_config == default_config
    assert yaml_config.fingerprint() == default_config.fingerprint()


def test_configuration_rejects_direction_weights_that_do_not_sum_to_one() -> None:
    reference = ScoringConfig.default()
    invalid = {
        **reference.direction_weights,
        "swing": {
            "trend": 0.40,
            "momentum": 0.25,
            "positioning": 0.15,
            "term_structure": 0.10,
        },
    }
    with pytest.raises(ValueError, match="sum to 1.0"):
        replace(reference, direction_weights=invalid)
