"""add host_id to findings table

Revision ID: add_host_id_to_findings
Revises: add_dns_analysis_views
Create Date: 2026-01-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'add_host_id_to_findings'
down_revision: Union[str, None] = 'add_dns_analysis_views'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('findings', sa.Column('host_id', UUID(), nullable=True))
    op.create_foreign_key(
        'fk_findings_host_id',
        'findings', 'hosts',
        ['host_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('idx_findings_host', 'findings', ['host_id'])


def downgrade() -> None:
    op.drop_index('idx_findings_host', table_name='findings')
    op.drop_constraint('fk_findings_host_id', 'findings', type_='foreignkey')
    op.drop_column('findings', 'host_id')
