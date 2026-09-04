from __future__ import annotations

from dataclasses import dataclass

from dragonboat_ai.futures_agent.domain.exceptions import InsufficientDataError
from dragonboat_ai.futures_agent.domain.market_data import ContractCandidate


@dataclass(frozen=True, slots=True)
class MainContractSelection:
    selected: ContractCandidate
    reason: str
    challenger_confirmed: bool


class LiquidityConfirmedMainContractPolicy:
    """Select a liquid, non-expiring contract without same-day look-ahead switching.

    Candidate history is expected newest first. A challenger must rank first for
    `confirmation_days` consecutive completed snapshots before it replaces the
    prior day's winner.
    """

    def __init__(
        self,
        *,
        exclude_days_to_expiry_below: int = 10,
        confirmation_days: int = 2,
        minimum_volume_share: float = 0.15,
        minimum_oi_share: float = 0.15,
    ) -> None:
        if confirmation_days < 1:
            raise ValueError("confirmation_days must be at least one")
        self.exclude_days_to_expiry_below = exclude_days_to_expiry_below
        self.confirmation_days = confirmation_days
        self.minimum_volume_share = minimum_volume_share
        self.minimum_oi_share = minimum_oi_share

    def select(
        self,
        candidate_history: list[list[ContractCandidate]],
    ) -> MainContractSelection:
        if not candidate_history:
            raise InsufficientDataError("No contract candidates are available.")
        winners: list[ContractCandidate] = []
        for candidates in candidate_history:
            eligible = self._eligible(candidates)
            if eligible:
                winners.append(max(eligible, key=lambda item: (item.open_interest, item.volume, -item.days_to_expiry)))
        if not winners:
            raise InsufficientDataError("All contracts are inside the expiry/liquidity exclusion zone.")

        challenger = winners[0]
        confirmed = (
            len(winners) >= self.confirmation_days
            and all(item.contract.contract_code == challenger.contract.contract_code for item in winners[: self.confirmation_days])
        )
        if confirmed or len(winners) == 1:
            return MainContractSelection(
                selected=challenger,
                reason="highest_open_interest_confirmed_across_completed_snapshots",
                challenger_confirmed=confirmed,
            )

        previous_winner = winners[1]
        current_eligible = {
            item.contract.contract_code: item for item in self._eligible(candidate_history[0])
        }
        selected = current_eligible.get(previous_winner.contract.contract_code, challenger)
        return MainContractSelection(
            selected=selected,
            reason="challenger_not_yet_confirmed_keep_previous_liquid_contract",
            challenger_confirmed=False,
        )

    def _eligible(self, candidates: list[ContractCandidate]) -> list[ContractCandidate]:
        expiry_safe = [
            item for item in candidates if item.days_to_expiry >= self.exclude_days_to_expiry_below
        ]
        if not expiry_safe:
            return []
        share_safe = [
            item
            for item in expiry_safe
            if item.volume_share >= self.minimum_volume_share
            or item.open_interest_share >= self.minimum_oi_share
        ]
        return share_safe or expiry_safe
