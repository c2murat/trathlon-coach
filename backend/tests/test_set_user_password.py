from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import User
from app.security.passwords import PasswordPolicyError, verify_password
from scripts.set_user_password import UserPasswordBootstrapError, main, set_user_password


def database():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_set_user_password_updates_existing_normalized_user() -> None:
    engine, session = database()
    user = User(email="user@example.test", normalized_email="user@example.test", auth_subject="user")
    session.add(user); session.commit()
    set_user_password(session, email=" USER@EXAMPLE.TEST ", password="a secure bootstrap password")
    session.commit()
    assert verify_password("a secure bootstrap password", user.password_hash)
    session.close(); engine.dispose()


def test_set_user_password_rejects_missing_user_and_short_password() -> None:
    engine, session = database()
    try:
        try:
            set_user_password(session, email="missing@example.test", password="a secure bootstrap password")
            assert False
        except UserPasswordBootstrapError:
            pass
        try:
            set_user_password(session, email="missing@example.test", password="short")
            assert False
        except PasswordPolicyError:
            pass
    finally:
        session.close(); engine.dispose()


def test_script_mismatch_prints_no_secret(monkeypatch, capsys) -> None:
    secrets = iter(["first secret password", "second secret password"])
    monkeypatch.setattr("scripts.set_user_password.getpass.getpass", lambda _: next(secrets))
    assert main(["--email", "user@example.test"]) == 2
    output = capsys.readouterr()
    assert "no coinciden" in output.err
    assert "first secret password" not in output.out + output.err
    assert "second secret password" not in output.out + output.err
