from datetime import datetime

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Disclosure, Round
from app.seeds import seed_demo_catalog
from app.services.drand_adapter import DrandAdapter
from app.telemetry import configure_tracing, shutdown_tracing
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


def test_failed_worker_pass_is_traced_and_retried_with_disclosure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_demo_catalog(db_session, now=NOW)
    round_ = db_session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    round_.disclosure_deadline = NOW
    db_session.commit()
    exporter = InMemorySpanExporter()
    settings = Settings(
        _env_file=None,
        environment="test",
        tracing_enabled=True,
        otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
    )
    adapter = DrandAdapter(relays=("https://test.invalid",))

    def fail_recovery(*args: object, **kwargs: object) -> None:
        raise RuntimeError("temporary-worker-failure")

    try:
        assert configure_tracing(settings, "gwengift-worker", exporter=exporter)
        monkeypatch.setattr("app.worker.recover_pending_bets", fail_recovery)
        with pytest.raises(RuntimeError, match="temporary-worker-failure"):
            run_worker_pass(db_session, adapter=adapter, settings=settings, now=NOW)
        monkeypatch.undo()
        result = run_worker_pass(db_session, adapter=adapter, settings=settings, now=NOW)
    finally:
        shutdown_tracing()

    assert result == {"recovered_bets": 0, "disclosed_rounds": 1}
    spans = exporter.get_finished_spans()
    passes = [span for span in spans if span.name == "worker.pass"]
    assert len(passes) == 2
    assert passes[0].status.status_code == StatusCode.ERROR
    assert (passes[0].attributes or {})["error.type"] == "RuntimeError"
    assert passes[0].events == ()
    disclosure = next(span for span in spans if span.name == "round.disclose")
    disclosure_attributes = disclosure.attributes or {}
    assert disclosure_attributes["gwengift.round_id"] == round_.id
    assert disclosure_attributes["gwengift.outcome"] == "DISCLOSED"
