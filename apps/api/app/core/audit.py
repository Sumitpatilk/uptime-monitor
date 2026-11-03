from uuid import UUID

from sqlalchemy.orm import Session

from app.models.entities import AuditEvent


def log_audit_event(
    db: Session,
    project_id: UUID,
    actor_id: UUID,
    action: str,
) -> None:
    """Add an audit event to the current database transaction."""
    db.add(
        AuditEvent(
            project_id=project_id,
            actor_id=actor_id,
            action=action,
        )
    )
