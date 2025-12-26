"""user_add_configuration

Revision ID: 5a0957edd67c
Revises: 4948a2b467f4
Create Date: 2025-12-26 12:34:03.381313+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a0957edd67c'
down_revision: Union[str, Sequence[str], None] = '4948a2b467f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user', sa.Column('configuration', sa.JSON(), nullable=True, default=None))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user', 'configuration')
