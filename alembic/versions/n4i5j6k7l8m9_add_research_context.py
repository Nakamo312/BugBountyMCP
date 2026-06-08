"""Add research bounded context tables

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'n4i5j6k7l8m9'
down_revision: Union[str, None] = 'm3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'research_producer_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('producer_name', sa.String(length=100), nullable=False),
        sa.Column('producer_version', sa.String(length=100), nullable=False),
        sa.Column('rule_version', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('input_watermark', sa.Text(), nullable=True),
        sa.Column('stats_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("producer_name != ''", name='ck_research_producer_runs_name_not_empty'),
        sa.CheckConstraint("producer_version != ''", name='ck_research_producer_runs_version_not_empty'),
        sa.CheckConstraint("rule_version != ''", name='ck_research_producer_runs_rule_version_not_empty'),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name='ck_research_producer_runs_status_valid',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_research_producer_runs_producer_name', 'research_producer_runs', ['producer_name'])
    op.create_index('ix_research_producer_runs_status', 'research_producer_runs', ['status'])
    op.create_index(
        'idx_research_producer_runs_status_started',
        'research_producer_runs',
        ['status', 'started_at'],
    )

    op.create_table(
        'research_signals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('producer_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('signal_type', sa.String(length=100), nullable=False),
        sa.Column('signal_version', sa.String(length=100), nullable=False),
        sa.Column('rule_id', sa.String(length=100), nullable=False),
        sa.Column('rule_version', sa.String(length=100), nullable=False),
        sa.Column('asset_type', sa.String(length=50), nullable=True),
        sa.Column('asset_id', sa.Text(), nullable=True),
        sa.Column('observation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('evidence_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("signal_type != ''", name='ck_research_signals_type_not_empty'),
        sa.CheckConstraint("signal_version != ''", name='ck_research_signals_version_not_empty'),
        sa.CheckConstraint("rule_id != ''", name='ck_research_signals_rule_id_not_empty'),
        sa.CheckConstraint("rule_version != ''", name='ck_research_signals_rule_version_not_empty'),
        sa.CheckConstraint("evidence_fingerprint != ''", name='ck_research_signals_fingerprint_not_empty'),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name='ck_research_signals_confidence_range',
        ),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['producer_run_id'], ['research_producer_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['observation_id'], ['http_observations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'program_id',
            'signal_type',
            'signal_version',
            'evidence_fingerprint',
            name='uq_research_signal_fingerprint',
        ),
    )
    op.create_index('ix_research_signals_program_id', 'research_signals', ['program_id'])
    op.create_index('ix_research_signals_producer_run_id', 'research_signals', ['producer_run_id'])
    op.create_index('ix_research_signals_signal_type', 'research_signals', ['signal_type'])
    op.create_index('ix_research_signals_asset_type', 'research_signals', ['asset_type'])
    op.create_index('ix_research_signals_observation_id', 'research_signals', ['observation_id'])
    op.create_index(
        'idx_research_signals_program_type_created',
        'research_signals',
        ['program_id', 'signal_type', 'created_at'],
    )

    op.create_table(
        'research_hypotheses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hypothesis_type', sa.String(length=100), nullable=False),
        sa.Column('hypothesis_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('state_version', sa.Integer(), nullable=False),
        sa.Column('priority_score', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('severity_guess', sa.String(length=20), nullable=True),
        sa.Column('safety_level', sa.String(length=30), nullable=False),
        sa.Column('score_version', sa.String(length=100), nullable=False),
        sa.Column('inputs_hash', sa.String(length=64), nullable=False),
        sa.Column('source_signal_fingerprints', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('duplicate_of_hypothesis_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("hypothesis_type != ''", name='ck_research_hypotheses_type_not_empty'),
        sa.CheckConstraint("hypothesis_fingerprint != ''", name='ck_research_hypotheses_fingerprint_not_empty'),
        sa.CheckConstraint("state_version > 0", name='ck_research_hypotheses_state_version_positive'),
        sa.CheckConstraint(
            "status IN ('new', 'needs_verification', 'reviewing', 'dismissed', 'duplicate', 'promoted', 'stale')",
            name='ck_research_hypotheses_status_valid',
        ),
        sa.CheckConstraint(
            "priority_score >= 0 AND priority_score <= 100",
            name='ck_research_hypotheses_priority_range',
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name='ck_research_hypotheses_confidence_range',
        ),
        sa.CheckConstraint(
            "duplicate_of_hypothesis_id IS NULL OR duplicate_of_hypothesis_id != id",
            name='ck_research_hypotheses_duplicate_not_self',
        ),
        sa.CheckConstraint(
            "status != 'duplicate' OR duplicate_of_hypothesis_id IS NOT NULL",
            name='ck_research_hypotheses_duplicate_status_requires_ref',
        ),
        sa.CheckConstraint(
            "duplicate_of_hypothesis_id IS NULL OR status = 'duplicate'",
            name='ck_research_hypotheses_duplicate_ref_requires_status',
        ),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['duplicate_of_hypothesis_id'], ['research_hypotheses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'program_id',
            'hypothesis_type',
            'hypothesis_fingerprint',
            name='uq_research_hypothesis_fingerprint',
        ),
    )
    op.create_index('ix_research_hypotheses_program_id', 'research_hypotheses', ['program_id'])
    op.create_index('ix_research_hypotheses_hypothesis_type', 'research_hypotheses', ['hypothesis_type'])
    op.create_index('ix_research_hypotheses_status', 'research_hypotheses', ['status'])
    op.create_index('ix_research_hypotheses_severity_guess', 'research_hypotheses', ['severity_guess'])
    op.create_index('ix_research_hypotheses_duplicate_of_hypothesis_id', 'research_hypotheses', ['duplicate_of_hypothesis_id'])
    op.create_index(
        'idx_research_hypotheses_program_status_score',
        'research_hypotheses',
        ['program_id', 'status', 'priority_score'],
    )

    op.create_table(
        'research_hypothesis_evidence',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hypothesis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ref_type', sa.String(length=50), nullable=False),
        sa.Column('ref_id', sa.Text(), nullable=False),
        sa.Column('field_path', sa.Text(), nullable=True),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('claim_type', sa.String(length=100), nullable=False),
        sa.Column('claim', sa.Text(), nullable=False),
        sa.Column('evidence_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('safe_excerpt', sa.Text(), nullable=True),
        sa.Column('safe_excerpt_truncated', sa.Boolean(), nullable=False),
        sa.Column('safe_excerpt_hash', sa.String(length=64), nullable=True),
        sa.Column('evidence_source', sa.String(length=30), nullable=False),
        sa.Column('normalized_content_hash', sa.String(length=64), nullable=True),
        sa.Column('sanitized_content_hash', sa.String(length=64), nullable=True),
        sa.Column('sanitizer_version', sa.String(length=100), nullable=False),
        sa.Column('redaction_policy_version', sa.String(length=100), nullable=False),
        sa.Column('sensitivity_level', sa.String(length=50), nullable=False),
        sa.Column('redaction_rules_triggered', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('safe_for_search', sa.Boolean(), nullable=False),
        sa.Column('safe_for_embedding', sa.Boolean(), nullable=False),
        sa.Column('safe_for_llm', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ref_type != ''", name='ck_research_evidence_ref_type_not_empty'),
        sa.CheckConstraint("ref_id != ''", name='ck_research_evidence_ref_id_not_empty'),
        sa.CheckConstraint("claim_type != ''", name='ck_research_evidence_claim_type_not_empty'),
        sa.CheckConstraint("claim != ''", name='ck_research_evidence_claim_not_empty'),
        sa.CheckConstraint("evidence_fingerprint != ''", name='ck_research_evidence_fingerprint_not_empty'),
        sa.CheckConstraint(
            "role IN ('primary', 'supporting', 'context', 'contradicting')",
            name='ck_research_evidence_role_valid',
        ),
        sa.CheckConstraint(
            "evidence_source IN ('sanitizer', 'metadata_only', 'manual', 'legacy')",
            name='ck_research_evidence_source_valid',
        ),
        sa.CheckConstraint(
            "safe_excerpt IS NULL OR safe_for_search = true",
            name='ck_research_evidence_safe_excerpt_requires_search_safe',
        ),
        sa.ForeignKeyConstraint(['hypothesis_id'], ['research_hypotheses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'hypothesis_id',
            'evidence_fingerprint',
            name='uq_research_hypothesis_evidence_fingerprint',
        ),
    )
    op.create_index('ix_research_hypothesis_evidence_hypothesis_id', 'research_hypothesis_evidence', ['hypothesis_id'])
    op.create_index('ix_research_hypothesis_evidence_ref_type', 'research_hypothesis_evidence', ['ref_type'])
    op.create_index(
        'idx_research_evidence_hypothesis_role',
        'research_hypothesis_evidence',
        ['hypothesis_id', 'role'],
    )

    op.create_table(
        'research_hypothesis_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hypothesis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('aggregate_version', sa.Integer(), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("event_type != ''", name='ck_research_hypothesis_events_type_not_empty'),
        sa.CheckConstraint("actor != ''", name='ck_research_hypothesis_events_actor_not_empty'),
        sa.CheckConstraint(
            "aggregate_version > 0",
            name='ck_research_hypothesis_events_aggregate_version_positive',
        ),
        sa.ForeignKeyConstraint(['hypothesis_id'], ['research_hypotheses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'hypothesis_id',
            'aggregate_version',
            name='uq_research_hypothesis_events_version',
        ),
    )
    op.create_index('ix_research_hypothesis_events_hypothesis_id', 'research_hypothesis_events', ['hypothesis_id'])
    op.create_index('ix_research_hypothesis_events_event_type', 'research_hypothesis_events', ['event_type'])
    op.create_index(
        'idx_research_hypothesis_events_hypothesis_version',
        'research_hypothesis_events',
        ['hypothesis_id', 'aggregate_version'],
    )

    op.create_table(
        'research_hypothesis_score_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('hypothesis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('score_version', sa.String(length=100), nullable=False),
        sa.Column('priority_score', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('severity_guess', sa.String(length=20), nullable=True),
        sa.Column('safety_level', sa.String(length=30), nullable=False),
        sa.Column('inputs_hash', sa.String(length=64), nullable=False),
        sa.Column('factors_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score_version != ''", name='ck_research_score_history_version_not_empty'),
        sa.CheckConstraint("inputs_hash != ''", name='ck_research_score_history_inputs_hash_not_empty'),
        sa.CheckConstraint(
            "priority_score >= 0 AND priority_score <= 100",
            name='ck_research_score_history_priority_range',
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name='ck_research_score_history_confidence_range',
        ),
        sa.ForeignKeyConstraint(['hypothesis_id'], ['research_hypotheses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_research_hypothesis_score_history_hypothesis_id', 'research_hypothesis_score_history', ['hypothesis_id'])
    op.create_index(
        'idx_research_score_history_hypothesis_created',
        'research_hypothesis_score_history',
        ['hypothesis_id', 'created_at'],
    )

    op.create_table(
        'research_suppression_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scope', sa.String(length=50), nullable=False),
        sa.Column('match_type', sa.String(length=50), nullable=False),
        sa.Column('match_value', sa.Text(), nullable=False),
        sa.Column('match_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_from_hypothesis_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope != ''", name='ck_research_suppression_scope_not_empty'),
        sa.CheckConstraint("match_type != ''", name='ck_research_suppression_match_type_not_empty'),
        sa.CheckConstraint("match_value != ''", name='ck_research_suppression_match_value_not_empty'),
        sa.CheckConstraint("match_fingerprint != ''", name='ck_research_suppression_fingerprint_not_empty'),
        sa.CheckConstraint("reason != ''", name='ck_research_suppression_reason_not_empty'),
        sa.CheckConstraint(
            "scope IN ('global', 'program', 'asset', 'hypothesis_type', 'signal_type', 'dedupe_group')",
            name='ck_research_suppression_scope_valid',
        ),
        sa.CheckConstraint(
            "match_type IN ('exact', 'fingerprint', 'prefix', 'regex', 'tag')",
            name='ck_research_suppression_match_type_valid',
        ),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_from_hypothesis_id'], ['research_hypotheses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'program_id',
            'scope',
            'match_type',
            'match_fingerprint',
            name='uq_research_suppression_fingerprint',
        ),
    )
    op.create_index('ix_research_suppression_rules_program_id', 'research_suppression_rules', ['program_id'])
    op.create_index(
        'ix_research_suppression_rules_created_from_hypothesis_id',
        'research_suppression_rules',
        ['created_from_hypothesis_id'],
    )
    op.create_index(
        'idx_research_suppression_program_scope',
        'research_suppression_rules',
        ['program_id', 'scope'],
    )


def downgrade() -> None:
    op.drop_index('idx_research_suppression_program_scope', table_name='research_suppression_rules')
    op.drop_index('ix_research_suppression_rules_created_from_hypothesis_id', table_name='research_suppression_rules')
    op.drop_index('ix_research_suppression_rules_program_id', table_name='research_suppression_rules')
    op.drop_table('research_suppression_rules')

    op.drop_index('idx_research_score_history_hypothesis_created', table_name='research_hypothesis_score_history')
    op.drop_index('ix_research_hypothesis_score_history_hypothesis_id', table_name='research_hypothesis_score_history')
    op.drop_table('research_hypothesis_score_history')

    op.drop_index('idx_research_hypothesis_events_hypothesis_version', table_name='research_hypothesis_events')
    op.drop_index('ix_research_hypothesis_events_event_type', table_name='research_hypothesis_events')
    op.drop_index('ix_research_hypothesis_events_hypothesis_id', table_name='research_hypothesis_events')
    op.drop_table('research_hypothesis_events')

    op.drop_index('idx_research_evidence_hypothesis_role', table_name='research_hypothesis_evidence')
    op.drop_index('ix_research_hypothesis_evidence_ref_type', table_name='research_hypothesis_evidence')
    op.drop_index('ix_research_hypothesis_evidence_hypothesis_id', table_name='research_hypothesis_evidence')
    op.drop_table('research_hypothesis_evidence')

    op.drop_index('idx_research_hypotheses_program_status_score', table_name='research_hypotheses')
    op.drop_index('ix_research_hypotheses_duplicate_of_hypothesis_id', table_name='research_hypotheses')
    op.drop_index('ix_research_hypotheses_severity_guess', table_name='research_hypotheses')
    op.drop_index('ix_research_hypotheses_status', table_name='research_hypotheses')
    op.drop_index('ix_research_hypotheses_hypothesis_type', table_name='research_hypotheses')
    op.drop_index('ix_research_hypotheses_program_id', table_name='research_hypotheses')
    op.drop_table('research_hypotheses')

    op.drop_index('idx_research_signals_program_type_created', table_name='research_signals')
    op.drop_index('ix_research_signals_observation_id', table_name='research_signals')
    op.drop_index('ix_research_signals_asset_type', table_name='research_signals')
    op.drop_index('ix_research_signals_signal_type', table_name='research_signals')
    op.drop_index('ix_research_signals_producer_run_id', table_name='research_signals')
    op.drop_index('ix_research_signals_program_id', table_name='research_signals')
    op.drop_table('research_signals')

    op.drop_index('idx_research_producer_runs_status_started', table_name='research_producer_runs')
    op.drop_index('ix_research_producer_runs_status', table_name='research_producer_runs')
    op.drop_index('ix_research_producer_runs_producer_name', table_name='research_producer_runs')
    op.drop_table('research_producer_runs')
