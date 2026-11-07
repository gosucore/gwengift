from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Disclosure, Round
from app.seeds import seed_demo_catalog
from app.services.drand_adapter import DrandAdapter
from app.worker import run_worker_pass

NOW = datetime(2026, 1, 1, 12, 0, 0)


def test_worker_discloses_due_round_without_pending_attempts(db_session: Session) -> None:
    seed_demo_catalog(db_session, now=NOW)
    round_ = db_session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    round_.disclosure_deadline = NOW
    db_session.commit()
    adapter = DrandAdapter(
        relays=("https://test.invalid",),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "not expected"})
        ),
    )

    result = run_worker_pass(
        db_session,
        adapter=adapter,
        settings=Settings(_env_file=None, environment="test"),
        now=NOW,
    )

    assert result == {"recovered_bets": 0, "disclosed_rounds": 1}
    disclosure = db_session.scalar(select(Disclosure).where(Disclosure.round_id == round_.id))
    assert disclosure is not None
    assert round_.status == "DISCLOSED"
    assert round_.disclosed_at == NOW
    other_round = db_session.scalar(select(Round).where(Round.collection_id == "durovs-cap"))
    assert other_round is not None and other_round.disclosure_deadline > NOW
    assert other_round.status == "DRAFT"
