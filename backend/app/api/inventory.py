from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.bets import BetResponse, bet_response
from app.api.dependencies import DbSession, get_current_account
from app.models import Bet, DrandProof, User, VirtualGift
from app.services.accounts import list_active_inventory, list_attempt_history

router = APIRouter(prefix="/api/account", tags=["inventory"])
CurrentAccount = Annotated[User, Depends(get_current_account)]


class InventoryGift(BaseModel):
    id: str
    bet_id: str
    collection_id: str
    round_id: str
    model: str
    backdrop: str
    symbol: str
    rarity: str
    number: int
    player_sale_estimate: int
    ticket_price: int
    value_minus_ticket: int
    awarded_at: datetime


class InventoryResponse(BaseModel):
    gifts: list[InventoryGift]
    asset_mode: Literal["simulated"] = "simulated"


class AttemptHistoryResponse(BaseModel):
    attempts: list[BetResponse]
    asset_mode: Literal["simulated"] = "simulated"


@router.get(
    "/inventory",
    response_model=InventoryResponse,
    summary="List active-epoch virtual gifts",
    description="Returns only simulated gifts awarded to the authenticated caller.",
)
def read_inventory(account: CurrentAccount, db: DbSession) -> InventoryResponse:
    gifts = list_active_inventory(db, account.id)
    items: list[InventoryGift] = []
    for gift in gifts:
        bet = db.scalar(select(Bet).where(Bet.selected_gift_id == gift.id))
        if bet is None or bet.resolved_at is None:
            raise HTTPException(status_code=500, detail="Awarded gift has no resolved draw")
        items.append(
            InventoryGift(
                id=gift.id,
                bet_id=bet.id,
                collection_id=gift.collection_id,
                round_id=gift.round_id,
                model=gift.model,
                backdrop=gift.backdrop,
                symbol=gift.symbol,
                rarity=gift.rarity,
                number=gift.number,
                player_sale_estimate=gift.player_sale_estimate,
                ticket_price=bet.price,
                value_minus_ticket=gift.player_sale_estimate - bet.price,
                awarded_at=bet.resolved_at,
            )
        )
    return InventoryResponse(gifts=items)


@router.get(
    "/attempts",
    response_model=AttemptHistoryResponse,
    summary="List active-epoch demo attempts",
    description="Returns pending, cancelled, and completed attempts for the authenticated caller.",
)
def read_attempt_history(account: CurrentAccount, db: DbSession) -> AttemptHistoryResponse:
    attempts = list_attempt_history(db, account.id)
    responses: list[BetResponse] = []
    for bet in attempts:
        gift = db.get(VirtualGift, bet.selected_gift_id) if bet.selected_gift_id else None
        proof = db.scalar(select(DrandProof).where(DrandProof.bet_id == bet.id))
        responses.append(bet_response(bet, gift, proof))
    return AttemptHistoryResponse(attempts=responses)
