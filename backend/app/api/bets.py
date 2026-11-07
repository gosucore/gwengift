from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import AppSettings, DbSession, get_current_account
from app.models import Bet, DrandProof, User, VirtualGift
from app.services.accounts import InsufficientDemoBalanceError
from app.services.bets import (
    BetCreationError,
    CollectionBusyError,
    IdempotencyConflictError,
    StalePoolVersionError,
    create_bet,
)

router = APIRouter(prefix="/api/bets", tags=["bets"])
CurrentAccount = Annotated[User, Depends(get_current_account)]


class CreateBetRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=64)
    pool_version_id: str = Field(min_length=1, max_length=36)
    idempotency_key: str = Field(min_length=1, max_length=128)


class GiftResult(BaseModel):
    id: str
    model: str
    backdrop: str
    symbol: str
    rarity: str
    number: int
    player_sale_estimate: int
    ticket_price: int
    value_minus_ticket: int


class BeaconEvidence(BaseModel):
    network: str
    round: int
    signature: str
    randomness: str
    verified_at: datetime


class BetResponse(BaseModel):
    id: str
    collection_id: str
    round_id: str
    pool_version_id: str
    pool_version_hash: str
    state: Literal["PENDING_RANDOMNESS", "RESOLVING", "COMPLETED", "CANCELLED"]
    price: int
    remaining_count: int
    future_beacon_round: int
    acceptance_cutoff: datetime
    resolution_deadline: datetime
    created_at: datetime
    resolved_at: datetime | None
    cancellation_reason: str | None
    gift: GiftResult | None
    beacon: BeaconEvidence | None
    asset_mode: Literal["simulated"] = "simulated"


def bet_response(bet: Bet, gift: VirtualGift | None, proof: DrandProof | None) -> BetResponse:
    gift_result = None
    if gift is not None:
        gift_result = GiftResult(
            id=gift.id,
            model=gift.model,
            backdrop=gift.backdrop,
            symbol=gift.symbol,
            rarity=gift.rarity,
            number=gift.number,
            player_sale_estimate=gift.player_sale_estimate,
            ticket_price=bet.price,
            value_minus_ticket=gift.player_sale_estimate - bet.price,
        )
    evidence = None
    if proof is not None:
        evidence = BeaconEvidence(
            network=proof.network,
            round=proof.beacon_round,
            signature=proof.signature,
            randomness=proof.randomness,
            verified_at=proof.verified_at,
        )
    return BetResponse(
        id=bet.id,
        collection_id=bet.collection_id,
        round_id=bet.round_id,
        pool_version_id=bet.pool_version_id,
        pool_version_hash=bet.pool_version_hash,
        state=bet.state,
        price=bet.price,
        remaining_count=bet.remaining_count,
        future_beacon_round=bet.future_beacon_round,
        acceptance_cutoff=bet.acceptance_cutoff,
        resolution_deadline=bet.resolution_deadline,
        created_at=bet.created_at,
        resolved_at=bet.resolved_at,
        cancellation_reason=bet.cancellation_reason,
        gift=gift_result,
        beacon=evidence,
    )


@router.post(
    "",
    response_model=BetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or retry a demo draw",
    description=(
        "Binds the confirmed pool quote to future drand randomness; retries are idempotent."
    ),
)
def create_bet_endpoint(
    request: CreateBetRequest,
    account: CurrentAccount,
    db: DbSession,
    settings: AppSettings,
) -> BetResponse:
    try:
        bet = create_bet(
            db,
            user_id=account.id,
            collection_id=request.collection_id,
            idempotency_key=request.idempotency_key,
            expected_pool_version_id=request.pool_version_id,
            settings=settings,
        )
    except InsufficientDemoBalanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CollectionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers={"Retry-After": "1"}) from exc
    except (StalePoolVersionError, IdempotencyConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BetCreationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    gift = db.get(VirtualGift, bet.selected_gift_id) if bet.selected_gift_id is not None else None
    proof = db.scalar(select(DrandProof).where(DrandProof.bet_id == bet.id))
    return bet_response(bet, gift, proof)


@router.get(
    "/{bet_id}",
    response_model=BetResponse,
    summary="Poll an owned demo draw",
    description="Returns pending state or the completed gift and locally verified beacon evidence.",
)
def get_bet_endpoint(bet_id: str, account: CurrentAccount, db: DbSession) -> BetResponse:
    bet = db.get(Bet, bet_id)
    if bet is None or bet.user_id != account.id:
        raise HTTPException(status_code=404, detail="Bet not found")
    gift = db.get(VirtualGift, bet.selected_gift_id) if bet.selected_gift_id is not None else None
    proof = db.scalar(select(DrandProof).where(DrandProof.bet_id == bet.id))
    return bet_response(bet, gift, proof)
