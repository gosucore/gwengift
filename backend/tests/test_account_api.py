import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_db
from app.main import app
from app.models import User
from app.services.accounts import debit_demo_balance

BOT_TOKEN = "123456789:test-api-token"


def telegram_header(user_id: int, username: str = "api_user") -> dict[str, str]:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "username": username}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(fields)}


def dev_header(user_id: int) -> dict[str, str]:
    return {"X-Dev-Telegram-User-Id": str(user_id), "X-Dev-Username": "local"}


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        environment="test",
        telegram_bot_token=BOT_TOKEN,
        dev_identity_enabled=True,
        starting_demo_balance=10_000,
    )

    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    def override_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_valid_telegram_credentials_load_account(client: TestClient) -> None:
    response = client.get("/api/account", headers=telegram_header(1001))

    assert response.status_code == 200
    assert response.json() == {
        "telegram_user_id": 1001,
        "username": "api_user",
        "demo_balance": 10_000,
        "active_epoch": 1,
        "asset_mode": "simulated",
    }


def test_missing_credentials_are_rejected(client: TestClient) -> None:
    response = client.get("/api/account")

    assert response.status_code == 401
    assert "opened through Telegram" in response.json()["detail"]


def test_reset_restores_starting_balance(client: TestClient, db_session: Session) -> None:
    account = client.get("/api/account", headers=dev_header(2001)).json()
    user = db_session.scalar(select(User).where(User.telegram_user_id == 2001))
    assert user is not None
    db_session.commit()
    debit_demo_balance(db_session, user.id, 500)

    response = client.post("/api/account/reset", headers=dev_header(2001))

    assert response.status_code == 200
    assert account["active_epoch"] == 1
    assert response.json()["active_epoch"] == 2
    assert response.json()["demo_balance"] == 10_000


def test_user_cannot_reset_another_users_state(client: TestClient, db_session: Session) -> None:
    client.get("/api/account", headers=dev_header(3001))
    other_before = client.get("/api/account", headers=dev_header(3002)).json()
    other_user = db_session.scalar(select(User).where(User.telegram_user_id == 3002))
    assert other_user is not None
    db_session.commit()

    response = client.post(
        "/api/account/reset",
        headers=dev_header(3001),
        json={"user_id": other_user.id},
    )
    other_after = client.get("/api/account", headers=dev_header(3002)).json()

    assert response.status_code == 200
    assert response.json()["telegram_user_id"] == 3001
    assert other_after == other_before


def test_invalid_credentials_cannot_mutate_state(client: TestClient, db_session: Session) -> None:
    client.get("/api/account", headers=dev_header(4001))
    user = db_session.scalar(select(User).where(User.telegram_user_id == 4001))
    assert user is not None
    db_session.commit()
    debit_demo_balance(db_session, user.id, 100)

    response = client.post(
        "/api/account/reset",
        headers={"X-Telegram-Init-Data": "invalid", **dev_header(4001)},
    )

    assert response.status_code == 401
    persisted_user = db_session.get(User, user.id)
    assert persisted_user is not None
    assert persisted_user.demo_balance == 9_900


def test_account_endpoints_are_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "200" in schema["paths"]["/api/account"]["get"]["responses"]
    assert "200" in schema["paths"]["/api/account/reset"]["post"]["responses"]
    assert "X-Telegram-Init-Data" in json.dumps(schema)
