from __future__ import annotations

from pathlib import Path

STORE = Path("src/api/infrastructure/action_experience_proposals.py")
TRANSACTIONS = Path("src/api/infrastructure/action_experience_proposal_transactions.py")
MAPPERS = Path("src/api/infrastructure/action_experience_proposal_mappers.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_action_experience_proposal_store_is_session_boundary_only() -> None:
    source = _read(STORE)

    assert "from sqlalchemy" not in source
    assert "adapters.orm" not in source
    assert "select(" not in source
    assert "update(" not in source
    assert "async def _transition_acceptance" in source
    assert "transition_acceptance_in_session(" in source
    assert "mark_reviewed_in_session(" in source


def test_action_experience_proposal_transactions_own_sql_and_mappers_own_payloads() -> None:
    transaction_source = _read(TRANSACTIONS)
    mapper_source = _read(MAPPERS)

    assert "select(action_experience_proposals)" in transaction_source
    assert "update(action_experience_proposals)" in transaction_source
    assert "def action_experience_proposal_record" in mapper_source
    assert "def acceptance_payload" in mapper_source
    assert "def review_payload" in mapper_source
