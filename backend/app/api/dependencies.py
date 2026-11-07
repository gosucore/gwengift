from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import IdentityValidationError, resolve_identity
from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.services.accounts import get_or_create_account

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_account(
    db: DbSession,
    settings: AppSettings,
    init_data: Annotated[
        str | None, Header(alias="X-Telegram-Init-Data", description="Telegram Mini App initData")
    ] = None,
    development_user_id: Annotated[
        int | None, Header(alias="X-Dev-Telegram-User-Id", include_in_schema=False)
    ] = None,
    development_username: Annotated[
        str | None, Header(alias="X-Dev-Username", include_in_schema=False)
    ] = None,
) -> User:
    try:
        identity = resolve_identity(
            init_data=init_data,
            settings=settings,
            development_user_id=development_user_id,
            development_username=development_username,
        )
    except IdentityValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return get_or_create_account(db, identity, settings.starting_demo_balance)
