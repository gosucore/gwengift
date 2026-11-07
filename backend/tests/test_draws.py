from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import TelegramIdentity
from app.config import Settings
from app.models import (
    Bet,
    DrandProof,
    DrawLease,
    LedgerEntry,
    PoolVersion,
    Round,
    User,
    VirtualGift,
)
from app.seeds import seed_demo_catalog
from app.services.accounts import get_or_create_account, reset_demo_account
from app.services.bets import create_bet
from app.services.drand_adapter import DrandAdapter, round_available_at
from app.services.draws import recover_pending_bets, resolve_bet
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version
from app.telemetry import configure_tracing, shutdown_tracing
from app.worker import run_worker_pass

ROUND_TIME = round_available_at(1)
NOW = ROUND_TIME - timedelta(seconds=4)
SIGNATURE = (
    "b55e7cb2d5c613ee0b2e28d6750aabbb78c39dcc96bd9d38c2c2e12198df95571d"
    "e8e8e402a0cc48871c7089a2b3af4b"
)
RANDOMNESS = "1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a"
BEACON = {"round": 1, "signature": SIGNATURE, "randomness": RANDOMNESS}


def settings() -> Settings:
    return Settings(_env_file=None, environment="test")


def adapter_with(response: dict[str, object]) -> DrandAdapter:
    return DrandAdapter(
        relays=("https://test.invalid",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response)),
    )


def prepare_pending_bet(session: Session) -> tuple[str, str, str]:
    seed_demo_catalog(session, now=NOW)
    round_ = session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    session.commit()
    manual = {
        "schema_version": 1,
        "collection_id": "plush-pepe",
        "observed_at": NOW.isoformat(),
        "liquidity_discount": "0",
        "gifts": [
            {
                "number": number,
                "floor_stars": floor,
                "evidence_url": f"https://evidence.example/{number}",
            }
            for number, floor in enumerate((90, 110, 135, 180), start=1)
        ],
    }
    external = {
        "source": "TG Gifts (tggifts.com)",
        "license": "CC BY 4.0",
        "generated": NOW.isoformat(),
        "collections": {
            "plush-pepe": {
                "name": "Plush Pepe",
                "days": [[NOW.date().isoformat(), 90, 5]],
            }
        },
    }
    snapshot = import_market_snapshot(
        session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=settings(),
        now=NOW,
    )
    pool = create_pool_version(session, round_.id, snapshot.id, settings=settings(), now=NOW)
    user = get_or_create_account(
        session, TelegramIdentity(telegram_user_id=1001, username="player"), 10_000
    )
    bet = create_bet(
        session,
        user_id=user.id,
        collection_id="plush-pepe",
        idempotency_key="draw-1",
        expected_pool_version_id=pool.id,
        settings=settings(),
        now=NOW,
    )
    assert bet.future_beacon_round == 1
    return user.id, pool.id, bet.id


def test_verified_resolution_awards_one_gift_and_atomically_updates_pool(
    db_session: Session,
) -> None:
    user_id, pool_id, bet_id = prepare_pending_bet(db_session)

    completed = resolve_bet(
        db_session,
        bet_id,
        adapter=adapter_with(BEACON),
        settings=settings(),
        now=ROUND_TIME,
    )
    replay = resolve_bet(
        db_session,
        bet_id,
        adapter=adapter_with({"round": 1, "signature": "00" * 48, "randomness": "00" * 32}),
        settings=settings(),
        now=ROUND_TIME + timedelta(seconds=1),
    )

    assert completed.state == "COMPLETED"
    assert replay.id == completed.id and replay.selected_gift_id == completed.selected_gift_id
    assert completed.selected_gift_id is not None
    gift = db_session.get(VirtualGift, completed.selected_gift_id)
    proof = db_session.scalar(select(DrandProof).where(DrandProof.bet_id == bet_id))
    assert gift is not None and gift.lifecycle == "AWARDED"
    assert gift.owner_user_id == user_id and gift.owner_epoch == 1
    assert proof is not None and proof.verification_result is True
    assert proof.randomness == RANDOMNESS
    assert db_session.get(DrawLease, "plush-pepe") is None
    second_pool = db_session.scalar(
        select(PoolVersion).where(
            PoolVersion.round_id == completed.round_id, PoolVersion.version == 2
        )
    )
    assert second_pool is not None and second_pool.remaining_count == 3
    assert completed.selected_gift_id not in second_pool.manifest_json
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]
    assert (
        db_session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.bet_id == bet_id, LedgerEntry.kind == "DEBIT"
            )
        )
        == 1
    )
    assert db_session.scalar(select(func.count(DrandProof.id))) == 1


def test_unavailable_then_invalid_randomness_never_selects_and_deadline_restores(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, _, bet_id = prepare_pending_bet(db_session)
    calls: list[str] = []

    def invalid_relay(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={**BEACON, "randomness": "00" * 32})

    adapter = DrandAdapter(
        relays=("https://test.invalid",), transport=httpx.MockTransport(invalid_relay)
    )

    def forbidden_selection(**kwargs: object) -> None:
        raise AssertionError("Selection must not run without verified randomness")

    monkeypatch.setattr("app.services.draws.select_gift", forbidden_selection)
    early = resolve_bet(
        db_session,
        bet_id,
        adapter=adapter,
        settings=settings(),
        now=ROUND_TIME - timedelta(seconds=1),
    )
    assert calls == []  # The early call never reaches a relay.
    invalid = resolve_bet(db_session, bet_id, adapter=adapter, settings=settings(), now=ROUND_TIME)

    assert early.state == "RESOLVING" and invalid.state == "RESOLVING"
    assert len(calls) == 1  # Invalid proof is not accepted or used for selection.
    assert db_session.scalar(select(func.count(DrandProof.id))) == 0
    assert (
        db_session.scalar(
            select(func.count(VirtualGift.id)).where(VirtualGift.lifecycle == "AWARDED")
        )
        == 0
    )

    db_session.commit()
    cancelled = resolve_bet(
        db_session,
        bet_id,
        adapter=adapter,
        settings=settings(),
        now=ROUND_TIME + timedelta(seconds=60),
    )

    assert cancelled.state == "CANCELLED"
    assert cancelled.cancellation_reason == "verified_randomness_unavailable_by_deadline"
    assert cancelled.selected_gift_id is None
    assert db_session.get(DrawLease, "plush-pepe") is None
    assert db_session.get(User, user_id).demo_balance == 10_000  # type: ignore[union-attr]
    entries = list(db_session.scalars(select(LedgerEntry).where(LedgerEntry.bet_id == bet_id)))
    assert [(entry.kind, entry.amount) for entry in entries] == [
        ("DEBIT", -144),
        ("RESTORATION", 144),
    ]


def test_restart_recovers_resolving_bet_from_immutable_binding(db_session: Session) -> None:
    _, _, bet_id = prepare_pending_bet(db_session)
    bet = db_session.get(Bet, bet_id)
    assert bet is not None
    bet.state = "RESOLVING"
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    with factory() as recovered_session:
        recovered = recover_pending_bets(
            recovered_session,
            adapter=adapter_with(BEACON),
            settings=settings(),
            now=ROUND_TIME,
        )

    assert [item.id for item in recovered] == [bet_id]
    assert recovered[0].state == "COMPLETED"
    assert recovered[0].selected_gift_id is not None


def test_reset_cancels_pending_draw_and_restores_before_new_epoch(db_session: Session) -> None:
    user_id, _, bet_id = prepare_pending_bet(db_session)

    user = reset_demo_account(db_session, user_id, 10_000)

    bet = db_session.get(Bet, bet_id)
    assert user.active_epoch == 2 and user.demo_balance == 10_000
    assert bet is not None and bet.state == "CANCELLED"
    assert bet.cancellation_reason == "demo_account_reset"
    assert db_session.get(DrawLease, "plush-pepe") is None
    assert (
        db_session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.bet_id == bet_id, LedgerEntry.kind == "RESTORATION"
            )
        )
        == 1
    )
    db_session.commit()
    recovered = recover_pending_bets(
        db_session,
        adapter=adapter_with(BEACON),
        settings=settings(),
        now=ROUND_TIME,
    )
    assert recovered == []


def tracing_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        tracing_enabled=True,
        otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
    )


def test_api_and_worker_spans_share_bet_and_round_identifiers(db_session: Session) -> None:
    api_exporter = InMemorySpanExporter()
    worker_exporter = InMemorySpanExporter()
    try:
        assert configure_tracing(tracing_settings(), "gwengift-api", exporter=api_exporter)
        _, _, bet_id = prepare_pending_bet(db_session)
        bet = db_session.get(Bet, bet_id)
        assert bet is not None
        round_id = bet.round_id
        db_session.commit()
        shutdown_tracing()

        assert configure_tracing(tracing_settings(), "gwengift-worker", exporter=worker_exporter)
        result = run_worker_pass(
            db_session,
            adapter=adapter_with(BEACON),
            settings=settings(),
            now=ROUND_TIME,
        )
        assert result["recovered_bets"] == 1
    finally:
        shutdown_tracing()

    spans = (
        *api_exporter.get_finished_spans(),
        *worker_exporter.get_finished_spans(),
    )
    created = next(span for span in spans if span.name == "bet.create")
    resolved = next(span for span in spans if span.name == "draw.resolve")
    created_attributes = created.attributes or {}
    resolved_attributes = resolved.attributes or {}
    assert created_attributes["gwengift.bet_id"] == bet_id
    assert resolved_attributes["gwengift.bet_id"] == bet_id
    assert created_attributes["gwengift.round_id"] == round_id
    assert resolved_attributes["gwengift.round_id"] == round_id
    assert created.resource.attributes["service.name"] == "gwengift-api"
    assert resolved.resource.attributes["service.name"] == "gwengift-worker"
    assert resolved_attributes["gwengift.outcome"] == "COMPLETED"
    assert any(span.name == "draw.recovery" for span in spans)
    assert any(span.name == "worker.pass" for span in spans)


def test_cancellation_span_preserves_restoration_outcome(db_session: Session) -> None:
    exporter = InMemorySpanExporter()
    try:
        assert configure_tracing(tracing_settings(), "gwengift-worker", exporter=exporter)
        user_id, _, bet_id = prepare_pending_bet(db_session)
        cancelled = resolve_bet(
            db_session,
            bet_id,
            adapter=adapter_with(BEACON),
            settings=settings(),
            now=ROUND_TIME + timedelta(seconds=60),
        )
    finally:
        shutdown_tracing()

    assert cancelled.state == "CANCELLED"
    assert db_session.get(User, user_id).demo_balance == 10_000  # type: ignore[union-attr]
    cancellation = next(
        span for span in exporter.get_finished_spans() if span.name == "draw.cancel"
    )
    cancellation_attributes = cancellation.attributes or {}
    assert cancellation_attributes["gwengift.bet_id"] == bet_id
    assert cancellation_attributes["gwengift.outcome"] == "CANCELLED"


class FailingSpanExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise ConnectionError("collector-unavailable")


def test_collector_failure_and_disabled_replay_preserve_protocol_outcome(
    db_session: Session,
) -> None:
    try:
        assert configure_tracing(
            tracing_settings(), "gwengift-worker", exporter=FailingSpanExporter()
        )
        user_id, _, bet_id = prepare_pending_bet(db_session)
        completed = resolve_bet(
            db_session,
            bet_id,
            adapter=adapter_with(BEACON),
            settings=settings(),
            now=ROUND_TIME,
        )
    finally:
        shutdown_tracing()

    replay = resolve_bet(
        db_session,
        bet_id,
        adapter=adapter_with(BEACON),
        settings=settings(),
        now=ROUND_TIME + timedelta(seconds=1),
    )
    assert completed.state == replay.state == "COMPLETED"
    assert completed.selected_gift_id is not None
    assert replay.selected_gift_id == completed.selected_gift_id
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]
    assert db_session.scalar(select(func.count(DrandProof.id))) == 1
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.bet_id == bet_id))
        == 1
    )


def test_instrumentation_failure_does_not_trigger_fallback_and_worker_can_retry(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    runtime = configure_tracing(tracing_settings(), "gwengift-worker", exporter=exporter)
    assert runtime is not None
    user_id, _, bet_id = prepare_pending_bet(db_session)

    def broken_tracing(*args: object, **kwargs: object) -> None:
        raise RuntimeError("instrumentation-unavailable")

    def forbidden_selection(**kwargs: object) -> None:
        raise AssertionError("Invalid randomness must never reach selection")

    try:
        monkeypatch.setattr(runtime.tracer, "start_as_current_span", broken_tracing)
        monkeypatch.setattr("app.services.draws.select_gift", forbidden_selection)
        invalid_adapter = DrandAdapter(
            relays=("https://test.invalid",),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={**BEACON, "randomness": "00" * 32})
            ),
        )
        first = run_worker_pass(
            db_session,
            adapter=invalid_adapter,
            settings=settings(),
            now=ROUND_TIME,
        )
        bet = db_session.get(Bet, bet_id)
        assert first["recovered_bets"] == 1
        assert bet is not None and bet.state == "RESOLVING"
        assert db_session.scalar(select(func.count(DrandProof.id))) == 0
        assert (
            db_session.scalar(
                select(func.count(VirtualGift.id)).where(VirtualGift.lifecycle == "AWARDED")
            )
            == 0
        )
        db_session.commit()

        monkeypatch.undo()
        second = run_worker_pass(
            db_session,
            adapter=adapter_with(BEACON),
            settings=settings(),
            now=ROUND_TIME,
        )
    finally:
        shutdown_tracing()

    assert second["recovered_bets"] == 1
    assert db_session.get(Bet, bet_id).state == "COMPLETED"  # type: ignore[union-attr]
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]
    assert db_session.scalar(select(func.count(DrandProof.id))) == 1
