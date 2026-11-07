from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import TelegramIdentity
from app.models import Bet, DrawLease, LedgerEntry, User, VirtualGift, utc_now


class InsufficientDemoBalanceError(ValueError):
    pass


def _get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Demo account does not exist")
    return user


def get_or_create_account(
    session: Session,
    identity: TelegramIdentity,
    starting_balance: int,
) -> User:
    with session.begin():
        user = session.scalar(
            select(User).where(User.telegram_user_id == identity.telegram_user_id)
        )
        if user is not None:
            user.username = identity.username
            return user

        user = User(
            telegram_user_id=identity.telegram_user_id,
            username=identity.username,
            active_epoch=1,
            demo_balance=starting_balance,
        )
        session.add(user)
        session.flush()
        session.add(
            LedgerEntry(
                user_id=user.id,
                user_epoch=user.active_epoch,
                kind="RESET",
                amount=starting_balance,
                balance_after=starting_balance,
            )
        )
        return user


def apply_demo_debit(
    session: Session,
    user: User,
    amount: int,
    *,
    bet_id: str | None = None,
) -> LedgerEntry:
    """Apply a debit inside the caller's transaction."""
    if amount <= 0:
        raise ValueError("Debit amount must be positive")
    if user.demo_balance < amount:
        raise InsufficientDemoBalanceError("Insufficient demo Stars balance")
    user.demo_balance -= amount
    entry = LedgerEntry(
        user_id=user.id,
        user_epoch=user.active_epoch,
        bet_id=bet_id,
        kind="DEBIT",
        amount=-amount,
        balance_after=user.demo_balance,
    )
    session.add(entry)
    session.flush()
    return entry


def debit_demo_balance(
    session: Session,
    user_id: str,
    amount: int,
    *,
    bet_id: str | None = None,
) -> LedgerEntry:
    if amount <= 0:
        raise ValueError("Debit amount must be positive")

    with session.begin():
        user = _get_user(session, user_id)
        return apply_demo_debit(session, user, amount, bet_id=bet_id)


def reset_demo_account(
    session: Session,
    user_id: str,
    starting_balance: int,
) -> User:
    if starting_balance < 0:
        raise ValueError("Starting balance cannot be negative")

    with session.begin():
        user = _get_user(session, user_id)
        current_time = utc_now()
        pending_bets = list(
            session.scalars(
                select(Bet).where(
                    Bet.user_id == user.id,
                    Bet.user_epoch == user.active_epoch,
                    Bet.state.in_(["PENDING_RANDOMNESS", "RESOLVING"]),
                )
            ).all()
        )
        for bet in pending_bets:
            user.demo_balance += bet.price
            session.add(
                LedgerEntry(
                    user_id=user.id,
                    user_epoch=user.active_epoch,
                    bet_id=bet.id,
                    kind="RESTORATION",
                    amount=bet.price,
                    balance_after=user.demo_balance,
                    created_at=current_time,
                )
            )
            bet.state = "CANCELLED"
            bet.cancellation_reason = "demo_account_reset"
            bet.resolved_at = current_time
            bet.updated_at = current_time
            lease = session.get(DrawLease, bet.collection_id)
            if lease is not None and lease.bet_id == bet.id:
                session.delete(lease)
        session.flush()
        user.active_epoch += 1
        user.demo_balance = starting_balance
        session.add(
            LedgerEntry(
                user_id=user.id,
                user_epoch=user.active_epoch,
                kind="RESET",
                amount=starting_balance,
                balance_after=starting_balance,
            )
        )
        session.flush()
        return user


def list_active_inventory(session: Session, user_id: str) -> list[VirtualGift]:
    with session.begin():
        user = _get_user(session, user_id)
        return list(
            session.scalars(
                select(VirtualGift)
                .where(
                    VirtualGift.owner_user_id == user.id,
                    VirtualGift.owner_epoch == user.active_epoch,
                    VirtualGift.lifecycle == "AWARDED",
                )
                .order_by(VirtualGift.created_at.desc())
            ).all()
        )


def list_attempt_history(session: Session, user_id: str) -> list[Bet]:
    with session.begin():
        user = _get_user(session, user_id)
        return list(
            session.scalars(
                select(Bet)
                .where(Bet.user_id == user.id, Bet.user_epoch == user.active_epoch)
                .order_by(Bet.created_at.desc())
            ).all()
        )
