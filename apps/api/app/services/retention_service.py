import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import CheckResult

logger = logging.getLogger("uptime-monitor.retention")


def cleanup_old_check_results(
    db: Session,
    current_time: datetime | None = None,
) -> int:
    """Delete one bounded batch of check results older than the retention period."""

    reference_time = current_time or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    cutoff = reference_time - timedelta(
        days=settings.check_result_retention_days
    )

    expired_ids = (
        select(CheckResult.id)
        .where(CheckResult.checked_at < cutoff)
        .order_by(CheckResult.checked_at.asc())
        .limit(settings.retention_cleanup_batch_size)
        .with_for_update(skip_locked=True)
    )

    try:
        result = db.execute(
            delete(CheckResult).where(CheckResult.id.in_(expired_ids))
        )
        deleted_count = result.rowcount or 0
        db.commit()

        if deleted_count:
            logger.info(
                "Retention cleanup deleted %s check results older than %s",
                deleted_count,
                cutoff.isoformat(),
            )

        return deleted_count

    except Exception:
        db.rollback()
        logger.exception("Check-result retention cleanup failed")
        raise
