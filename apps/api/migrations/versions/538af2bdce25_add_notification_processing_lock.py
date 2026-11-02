"""add notification processing lock

Revision ID: 538af2bdce25
Revises: 3b3ad88bf14a
"""

from alembic import op
import sqlalchemy as sa


revision = "538af2bdce25"
down_revision = "3b3ad88bf14a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_events",
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_notification_events_locked_at",
        "notification_events",
        ["locked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_events_locked_at",
        table_name="notification_events",
    )

    op.drop_column(
        "notification_events",
        "locked_at",
    )
