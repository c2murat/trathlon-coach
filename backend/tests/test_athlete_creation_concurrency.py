import os
from contextlib import contextmanager
from threading import Barrier, Thread
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.application.athletes import AthleteApplication
from app.core.settings import get_settings
from app.db.models import AthleteProfile, User, UserAthleteMembership


@contextmanager
def temporary_postgres(monkeypatch):
    base = make_url(get_settings().database_url)
    name = f"tricoach_athlete_creation_{uuid4().hex}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name)
    previous = os.environ.get("TC_DATABASE_URL")
    monkeypatch.setenv("TC_DATABASE_URL", url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.attributes["skip_logging_config"] = True
    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()
        if previous is None:
            monkeypatch.delenv("TC_DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("TC_DATABASE_URL", previous)
        with admin.connect() as connection:
            connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"), {"name": name})
            connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


def test_concurrent_first_athlete_creations_have_exactly_one_default(monkeypatch):
    with temporary_postgres(monkeypatch) as engine:
        user_id = uuid4()
        with Session(engine) as session:
            session.add(User(id=user_id, email="concurrent@example.test", normalized_email="concurrent@example.test", auth_subject="concurrent-subject"))
            session.commit()
        barrier = Barrier(2)
        errors = []

        def create(name: str) -> None:
            try:
                with Session(engine) as session:
                    barrier.wait()
                    AthleteApplication(session).create_owned_athlete(user_id, display_name=name, timezone="UTC", unit_system="metric")
                    session.commit()
            except Exception as exc:
                errors.append(exc)

        threads = [Thread(target=create, args=(name,)) for name in ("First", "Second")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 2
            memberships = list(session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id == user_id, UserAthleteMembership.is_active.is_(True))))
            assert len(memberships) == 2
            assert sum(item.is_default for item in memberships) == 1
            assert all(item.role == "owner" for item in memberships)
