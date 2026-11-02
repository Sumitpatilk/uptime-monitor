"""add email notification support

Revision ID: b74449e52aae
Revises: 0001_initial
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b74449e52aae"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename existing column without losing its data.
    op.alter_column(
        "alert_channels",
        "destination_secret_ref",
        new_column_name="destination",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    # Store notification delivery error details.
    op.add_column(
        "notification_events",
        sa.Column("last_error", sa.Text(), nullable=True),
    )

    # Prevent duplicate notifications for the same incident,
    # channel and event type.
    op.create_unique_constraint(
        "uq_notification_incident_channel_event",
        "notification_events",
        ["incident_id", "channel_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_notification_incident_channel_event",
        "notification_events",
        type_="unique",
    )

    op.drop_column("notification_events", "last_error")

    # Restore the original column name.
    op.alter_column(
        "alert_channels",
        "destination",
        new_column_name="destination_secret_ref",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
