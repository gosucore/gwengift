import logging
import signal
import threading
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import Round, utc_now
from app.services.disclosures import disclose_round
from app.services.drand_adapter import DrandAdapter
from app.services.draws import recover_pending_bets

logger = logging.getLogger("gwengift.worker")


def run_worker_pass(
    session: Session,
    *,
    adapter: DrandAdapter,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    current_time = utc_now() if now is None else now
    recovered = recover_pending_bets(
        session,
        adapter=adapter,
        settings=settings,
        now=current_time,
    )
    with session.begin():
        expired_round_ids = list(
            session.scalars(
                select(Round.id)
                .where(
                    Round.status != "DISCLOSED",
                    Round.disclosure_deadline <= current_time,
                )
                .order_by(Round.disclosure_deadline, Round.id)
            ).all()
        )
    disclosed = 0
    for round_id in expired_round_ids:
        try:
            disclose_round(session, round_id, now=current_time)
        except ValueError as exc:
            if "Pending attempts" not in str(exc):
                raise
            continue
        disclosed += 1
    return {"recovered_bets": len(recovered), "disclosed_rounds": disclosed}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    adapter = DrandAdapter()
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("Draw recovery worker started")
    while not stopped.is_set():
        try:
            with SessionLocal() as session:
                result = run_worker_pass(session, adapter=adapter, settings=settings)
            if result["recovered_bets"] or result["disclosed_rounds"]:
                logger.info("Worker pass completed: %s", result)
        except Exception:
            logger.exception("Worker pass failed; persisted state will be retried")
        stopped.wait(settings.worker_poll_interval_seconds)
    logger.info("Draw recovery worker stopped")


if __name__ == "__main__":
    main()
