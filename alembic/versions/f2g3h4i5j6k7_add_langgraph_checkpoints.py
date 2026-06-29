"""add LangGraph PostgreSQL checkpoint tables

Revision ID: f2g3h4i5j6k7
Revises: e1f2g3h4i5j6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f2g3h4i5j6k7'
down_revision = 'e1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('checkpoint_migrations',
        sa.Column('v', sa.Integer(), primary_key=True),
    )
    op.create_table('checkpoints',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('checkpoint_ns', sa.Text(), nullable=False, server_default=''),
        sa.Column('checkpoint_id', sa.Text(), nullable=False),
        sa.Column('parent_checkpoint_id', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('checkpoint', postgresql.JSONB(), nullable=False),
        sa.Column(
            'metadata',
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id'),
    )
    op.create_table('checkpoint_blobs',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('checkpoint_ns', sa.Text(), nullable=False, server_default=''),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('version', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('blob', sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint(
            'thread_id',
            'checkpoint_ns',
            'channel',
            'version',
        ),
    )
    op.create_table('checkpoint_writes',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('checkpoint_ns', sa.Text(), nullable=False, server_default=''),
        sa.Column('checkpoint_id', sa.Text(), nullable=False),
        sa.Column('task_id', sa.Text(), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('blob', sa.LargeBinary(), nullable=False),
        sa.Column('task_path', sa.Text(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint(
            'thread_id',
            'checkpoint_ns',
            'checkpoint_id',
            'task_id',
            'idx',
        ),
    )
    op.create_index('checkpoints_thread_id_idx', 'checkpoints', ['thread_id'])
    op.create_index(
        'checkpoint_blobs_thread_id_idx',
        'checkpoint_blobs',
        ['thread_id'],
    )
    op.create_index(
        'checkpoint_writes_thread_id_idx',
        'checkpoint_writes',
        ['thread_id'],
    )
    for version in range(10):
        op.execute(
            sa.text(
                "INSERT INTO checkpoint_migrations (v) VALUES (:version)"
            ).bindparams(version=version)
        )


def downgrade() -> None:
    op.drop_index('checkpoint_writes_thread_id_idx', table_name='checkpoint_writes')
    op.drop_index('checkpoint_blobs_thread_id_idx', table_name='checkpoint_blobs')
    op.drop_index('checkpoints_thread_id_idx', table_name='checkpoints')
    op.drop_table('checkpoint_writes')
    op.drop_table('checkpoint_blobs')
    op.drop_table('checkpoints')
    op.drop_table('checkpoint_migrations')
