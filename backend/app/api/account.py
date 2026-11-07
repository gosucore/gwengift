from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import AppSettings, DbSession, get_current_account
from app.models import User
from app.services.accounts import reset_demo_account

router = APIRouter(prefix="/api/account", tags=["account"])
CurrentAccount = Annotated[User, Depends(get_current_account)]


class AccountResponse(BaseModel):
    telegram_user_id: int
    username: str | None
    demo_balance: int
    active_epoch: int
    asset_mode: Literal["simulated"] = "simulated"


def account_response(user: User) -> AccountResponse:
    return AccountResponse(
        telegram_user_id=user.telegram_user_id,
        username=user.username,
        demo_balance=user.demo_balance,
        active_epoch=user.active_epoch,
    )


@router.get(
    "",
    response_model=AccountResponse,
    summary="Get the authenticated demo account",
    description="Authenticates Telegram initData and returns only the caller's simulated state.",
)
def read_account(account: CurrentAccount) -> AccountResponse:
    return account_response(account)


@router.post(
    "/reset",
    response_model=AccountResponse,
    summary="Reset the authenticated demo account",
    description="Starts a new demo epoch; global audit records are preserved.",
)
def reset_account(
    account: CurrentAccount,
    db: DbSession,
    settings: AppSettings,
) -> AccountResponse:
    return account_response(reset_demo_account(db, account.id, settings.starting_demo_balance))
