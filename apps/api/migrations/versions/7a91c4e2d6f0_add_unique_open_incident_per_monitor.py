"""ensure only one open incident per monitor

Revision ID: 7a91c4e2d6f0
Revises: cf47b5a2bf29
"""

from alembic import op
import sqlalchemy as sa


revision = "7a91c4e2d6f0"
down_revision = "cf47b5a2bf29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_incidents_one_open_per_monitor",
        "incidents",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("state = 'open'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_incidents_one_open_per_monitor",
        table_name="incidents",
    )
