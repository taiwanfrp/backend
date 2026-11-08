"""add status_reason and status_until to users

Revision ID: c3e8a1f45d20
Revises: 61b97dc324e4
Create Date: 2026-11-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e8a1f45d20"
down_revision: str | Sequence[str] | None = "61b97dc324e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("status_reason", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("status_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "status_until")
    op.drop_column("users", "status_reason")
