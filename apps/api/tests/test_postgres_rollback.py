from sqlalchemy import select

from app.models.entities import User


def test_database_session_commit_stays_inside_outer_transaction(test_db_session):
    email = "rollback-check@example.test"

    user = User(email=email)
    test_db_session.add(user)
    test_db_session.commit()

    saved_user = test_db_session.scalar(
        select(User).where(User.email == email)
    )

    assert saved_user is not None
    assert saved_user.email == email
    assert test_db_session.connection().in_transaction()
