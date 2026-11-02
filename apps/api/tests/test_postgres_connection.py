from sqlalchemy import text


def test_postgres_connection_uses_test_database(test_db_session):
    database_name = test_db_session.execute(
        text("SELECT current_database()")
    ).scalar_one()

    assert database_name == "uptime_monitor_test"
