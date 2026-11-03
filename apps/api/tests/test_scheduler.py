import uuid
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.entities import CheckResult, Monitor, Project, User
from app.worker.scheduler import process_due_monitors


def test_scheduler_skips_monitor_locked_by_another_session(
    test_db_engine,
):
    SessionFactory = sessionmaker(
        bind=test_db_engine,
        expire_on_commit=False,
    )

    setup_session = SessionFactory()

    user_id = None
    project_id = None
    monitor_id = None

    try:
        user = User(
            email=f"scheduler-lock-{uuid.uuid4()}@example.test"
        )
        setup_session.add(user)
        setup_session.flush()

        project = Project(
            owner_id=user.id,
            name="Scheduler Lock Test",
            plan="free",
        )
        setup_session.add(project)
        setup_session.flush()

        monitor = Monitor(
            project_id=project.id,
            name="Locked Scheduler Monitor",
            url="https://example.test",
            interval_seconds=1,
            enabled=True,
        )
        setup_session.add(monitor)
        setup_session.commit()

        user_id = user.id
        project_id = project.id
        monitor_id = monitor.id

    except Exception:
        setup_session.rollback()
        raise
    finally:
        setup_session.close()

    lock_session = SessionFactory()
    scheduler_session = SessionFactory()

    try:
        # Session 1 holds the monitor row lock.
        locked_monitor = lock_session.scalar(
            select(Monitor)
            .where(Monitor.id == monitor_id)
            .with_for_update()
        )

        assert locked_monitor is not None

        # Session 2 must skip the locked monitor instead of waiting.
        with patch(
            "app.worker.scheduler.run_monitor_check"
        ) as mock_run_check:
            process_due_monitors(scheduler_session)

            assert all(
                call.args[0].id != monitor_id
                for call in mock_run_check.call_args_list
            ), "Scheduler must skip the monitor locked by another session."

        # No check result should have been created for the locked monitor.
        check_count = scheduler_session.query(CheckResult).filter_by(
            monitor_id=monitor_id
        ).count()

        assert check_count == 0

    finally:
        scheduler_session.rollback()
        lock_session.rollback()

        scheduler_session.close()
        lock_session.close()

        cleanup_session = SessionFactory()

        try:
            cleanup_session.query(CheckResult).filter_by(
                monitor_id=monitor_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Monitor).filter_by(
                id=monitor_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Project).filter_by(
                id=project_id
            ).delete(synchronize_session=False)

            cleanup_session.query(User).filter_by(
                id=user_id
            ).delete(synchronize_session=False)

            cleanup_session.commit()

        except Exception:
            cleanup_session.rollback()
            raise
        finally:
            cleanup_session.close()


def test_manual_check_waits_for_scheduler_monitor_lock(
    test_db_engine,
):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import event

    from app.services.check_runner import run_monitor_check

    SessionFactory = sessionmaker(
        bind=test_db_engine,
        expire_on_commit=False,
    )

    setup_session = SessionFactory()
    user_id = None
    project_id = None
    monitor_id = None

    try:
        user = User(
            email=f"manual-lock-{uuid.uuid4()}@example.test"
        )
        setup_session.add(user)
        setup_session.flush()

        project = Project(
            owner_id=user.id,
            name="Manual Lock Test",
            plan="free",
        )
        setup_session.add(project)
        setup_session.flush()

        monitor = Monitor(
            project_id=project.id,
            name="Manual Lock Monitor",
            url="https://example.test",
            interval_seconds=60,
            enabled=True,
        )
        setup_session.add(monitor)
        setup_session.commit()

        user_id = user.id
        project_id = project.id
        monitor_id = monitor.id

    finally:
        setup_session.close()

    lock_session = SessionFactory()
    manual_started = threading.Event()
    http_check_started = threading.Event()
    lock_attempted = threading.Event()

    def observe_lock_query(
        conn, cursor, statement, parameters, context, executemany
    ):
        if "FOR UPDATE" in statement.upper():
            lock_attempted.set()

    try:
        # Simulate scheduler holding the monitor lock.
        locked_monitor = lock_session.scalar(
            select(Monitor)
            .where(Monitor.id == monitor_id)
            .with_for_update()
        )
        assert locked_monitor is not None

        # Observe only the manual session's subsequent lock query.
        event.listen(
            test_db_engine,
            "before_cursor_execute",
            observe_lock_query,
        )

        def fake_http_check(monitor):
            http_check_started.set()
            return {
                "status": "up",
                "status_code": 200,
                "latency_ms": 10,
                "error_code": None,
            }

        def execute_manual_check():
            manual_session = SessionFactory()
            try:
                manual_started.set()
                with patch(
                    "app.services.check_runner.perform_http_check",
                    side_effect=fake_http_check,
                ):
                    return run_monitor_check(
                        Monitor(id=monitor_id),
                        manual_session,
                    )
            finally:
                manual_session.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(execute_manual_check)

            assert manual_started.wait(timeout=5)

            # Confirm that the manual session actually issued its lock query.
            assert lock_attempted.wait(timeout=5)

            # Manual check must not reach HTTP while the row is locked.
            assert not http_check_started.is_set()

            # Release the scheduler's row lock.
            lock_session.rollback()

            assert http_check_started.wait(timeout=5)
            result = future.result(timeout=10)

            assert result.monitor_id == monitor_id
            assert result.status == "up"

    finally:
        event.remove(
            test_db_engine,
            "before_cursor_execute",
            observe_lock_query,
        )
        lock_session.rollback()
        lock_session.close()

        cleanup_session = SessionFactory()
        try:
            cleanup_session.query(CheckResult).filter_by(
                monitor_id=monitor_id
            ).delete(synchronize_session=False)
            cleanup_session.query(Monitor).filter_by(
                id=monitor_id
            ).delete(synchronize_session=False)
            cleanup_session.query(Project).filter_by(
                id=project_id
            ).delete(synchronize_session=False)
            cleanup_session.query(User).filter_by(
                id=user_id
            ).delete(synchronize_session=False)
            cleanup_session.commit()
        except Exception:
            cleanup_session.rollback()
            raise
        finally:
            cleanup_session.close()
