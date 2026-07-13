from __future__ import annotations

import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.db.base import Base
from app.db.models import AthleteProfile, User


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _seed_local_athlete(database_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(
            id=LOCAL_MVP_USER_ID,
            email="process@example.test",
            normalized_email="process@example.test",
            auth_subject="real-process-test-athlete",
            timezone="Europe/Madrid",
        )
        session.add(user)
        session.flush()
        session.add(AthleteProfile(user_id=user.id, timezone="Europe/Madrid"))
        session.commit()
    engine.dispose()


def _wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"uvicorn exited early: {stdout} {stderr}")
        try:
            if httpx.get(f"{base_url}/health", timeout=0.25).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.05)
    raise AssertionError("uvicorn did not become ready")


def test_real_process_connect_callback_and_exact_once_consume(tmp_path) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    state_database = (tmp_path / "oauth-state.sqlite3").resolve()
    application_database = (tmp_path / "application.sqlite3").resolve()
    _seed_local_athlete(application_database)
    port = _available_port()
    base_url = f"http://127.0.0.1:{port}"
    authorization_code = "real-process-authorization-code"

    environment = os.environ.copy()
    environment.update(
        {
            "TC_ENVIRONMENT": "test",
            "TC_DATABASE_URL": (
                f"sqlite+pysqlite:///{application_database.as_posix()}"
            ),
            "STRAVA_CLIENT_ID": "12345",
            "STRAVA_CLIENT_SECRET": "real-process-client-secret",
            "STRAVA_REDIRECT_URI": (
                f"{base_url}/integrations/strava/callback"
            ),
            "STRAVA_AUTHORIZATION_URL": "https://www.strava.com/oauth/authorize",
            "STRAVA_TOKEN_URL": "https://www.strava.com/oauth/token",
            "STRAVA_REVOCATION_URL": "https://www.strava.com/oauth/revoke",
            "STRAVA_SCOPES": "read,activity:read_all",
            "OAUTH_STATE_TTL_SECONDS": "600",
            "OAUTH_STATE_SQLITE_PATH": str(state_database),
            "OAUTH_STATE_DIAGNOSTICS": "true",
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.support.real_process_oauth_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=backend_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_for_server(base_url, process)
        connect = httpx.get(
            f"{base_url}/integrations/strava/connect",
            follow_redirects=False,
            timeout=3,
        )
        assert connect.status_code == 307
        state = parse_qs(urlsplit(connect.headers["location"]).query)["state"][0]

        with sqlite3.connect(state_database) as connection:
            rows = connection.execute(
                """
                SELECT state, user_id, created_at, expires_at, consumed_at
                FROM oauth_state
                """
            ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == state
        assert rows[0][1] == str(LOCAL_MVP_USER_ID)
        assert rows[0][2] < rows[0][3]
        assert rows[0][4] is None

        callback = httpx.get(
            f"{base_url}/integrations/strava/callback",
            params={
                "state": state,
                "code": authorization_code,
                "scope": "read,activity:read_all",
            },
            timeout=3,
        )
        assert callback.status_code == 200
        assert callback.json() == {
            "provider": "strava",
            "status": "connected",
        }

        with sqlite3.connect(state_database) as connection:
            consumed_at = connection.execute(
                "SELECT consumed_at FROM oauth_state WHERE state = ?",
                (state,),
            ).fetchone()[0]
        assert consumed_at is not None

        repeated = httpx.get(
            f"{base_url}/integrations/strava/callback",
            params={
                "state": state,
                "code": authorization_code,
                "scope": "read,activity:read_all",
            },
            timeout=3,
        )
        assert repeated.status_code == 400
        assert repeated.json() == {
            "detail": {"code": "oauth_state_invalid"}
        }
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)

    diagnostics = stdout + chr(10) + stderr
    prefix = state[:8]
    assert f"database_path={state_database}" in diagnostics
    assert f"state_prefix={prefix}" in diagnostics
    assert f"callback_state_prefix={prefix}" in diagnostics
    assert "lookup_result=found" in diagnostics
    assert "consume_result=success" in diagnostics
    assert "lookup_result=consumed" in diagnostics
    assert "public_error_code=oauth_state_invalid" in diagnostics
    process_ids = set(re.findall(r"process_id=([0-9]+)", diagnostics))
    assert len(process_ids) == 1
    application_ids = set(
        re.findall(r"application_instance_id=([0-9a-f-]{36})", diagnostics)
    )
    assert len(application_ids) == 1
    save_line = next(
        line
        for line in diagnostics.splitlines()
        if f"state_prefix={prefix}" in line
    )
    assert "stored_row_count=1" in save_line
    assert "created_at=None" not in save_line
    assert "expires_at=None" not in save_line
    assert state not in diagnostics
    assert authorization_code not in diagnostics
    assert "real-process-access-token" not in diagnostics
    assert "real-process-refresh-token" not in diagnostics
    assert "real-process-client-secret" not in diagnostics
