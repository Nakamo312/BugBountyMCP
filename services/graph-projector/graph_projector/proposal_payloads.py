from __future__ import annotations

from dataclasses import dataclass
from time import sleep as default_sleep
from typing import Any, Callable
from uuid import UUID


@dataclass(frozen=True)
class ActionExperienceProposalWorkerResult:
    scanned: int = 0
    proposal_runs: int = 0
    proposals: int = 0
    no_candidates: int = 0
    failed: int = 0


@dataclass(frozen=True)
class ActionExperienceProposalLoopResult:
    scanned: int = 0
    proposal_runs: int = 0
    proposals: int = 0
    no_candidates: int = 0
    failed: int = 0
    empty: int = 0
    iterations: int = 0

    @staticmethod
    def run(
        worker: Any,
        *,
        limit: int,
        program_id: UUID | str | None = None,
        max_iterations: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
    ) -> "ActionExperienceProposalLoopResult":
        if limit <= 0:
            raise ValueError("limit must be positive")
        if max_iterations is not None and max_iterations <= 0:
            raise ValueError("max_iterations must be positive when provided")
        if idle_exit_after is not None and idle_exit_after <= 0:
            raise ValueError("idle_exit_after must be positive when provided")
        if poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")

        scanned = proposal_runs = proposals = no_candidates = failed = empty = iterations = 0
        consecutive_empty = 0
        while max_iterations is None or iterations < max_iterations:
            result = worker.propose_once(limit=limit, program_id=program_id)
            iterations += 1
            scanned += result.scanned
            proposal_runs += result.proposal_runs
            proposals += result.proposals
            no_candidates += result.no_candidates
            failed += result.failed
            if result.scanned == 0:
                empty += 1
                consecutive_empty += 1
                if idle_exit_after is not None and consecutive_empty >= idle_exit_after:
                    break
                if poll_seconds > 0:
                    sleep(poll_seconds)
            else:
                consecutive_empty = 0
        return ActionExperienceProposalLoopResult(
            scanned=scanned,
            proposal_runs=proposal_runs,
            proposals=proposals,
            no_candidates=no_candidates,
            failed=failed,
            empty=empty,
            iterations=iterations,
        )

@dataclass(frozen=True)
class ActionExperienceProposalReviewResult:
    proposal_id: UUID
    previous_status: str
    status: str
    capability_id: str
    profile_id: str
    review_source: str
