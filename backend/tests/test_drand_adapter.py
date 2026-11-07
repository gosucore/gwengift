import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.services.drand import QUICKNET
from app.services.drand_adapter import (
    BeaconNotAvailableError,
    DrandAdapter,
    DrandVerificationError,
    round_available_at,
    select_future_round,
)

SIGNATURE = (
    "b55e7cb2d5c613ee0b2e28d6750aabbb78c39dcc96bd9d38c2c2e12198df95571d"
    "e8e8e402a0cc48871c7089a2b3af4b"
)
RANDOMNESS = "1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a"
BEACON = {"round": 1, "signature": SIGNATURE, "randomness": RANDOMNESS}
INFO = {
    "public_key": QUICKNET.public_key,
    "period": 3,
    "genesis_time": 1692803367,
    "hash": QUICKNET.chain_hash,
    "groupHash": "f477d5c89f21a17c863a7f937c6a6d15859414d2be09cd448d4279af331c5d3e",
    "schemeID": "bls-unchained-g1-rfc9380",
    "metadata": {"beaconID": "quicknet"},
}


def test_future_round_and_acceptance_cutoff_follow_genesis_and_period() -> None:
    now = datetime.fromtimestamp(QUICKNET.genesis_time, UTC).replace(tzinfo=None)

    target = select_future_round(now, minimum_delay_seconds=6, acceptance_margin_seconds=1)

    assert target.round_number == 3
    assert target.available_at == now + timedelta(seconds=6)
    assert target.acceptance_cutoff == now + timedelta(seconds=5)
    assert target.acceptance_cutoff < target.available_at


def test_future_round_rejects_insufficient_safety_delay() -> None:
    now = datetime.fromtimestamp(QUICKNET.genesis_time, UTC).replace(tzinfo=None)

    with pytest.raises(ValueError, match="must exceed"):
        select_future_round(now, minimum_delay_seconds=1, acceptance_margin_seconds=1)


def test_already_unresolved_round_is_not_requested_from_relays() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=BEACON)

    adapter = DrandAdapter(
        relays=("https://one.invalid", "https://two.invalid"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(BeaconNotAvailableError):
        adapter.fetch_verified_beacon(1, now=round_available_at(1) - timedelta(seconds=1))
    assert calls == []


def test_valid_beacon_is_verified_and_returned_with_network_evidence() -> None:
    adapter = DrandAdapter(
        relays=("https://one.invalid",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=BEACON)),
    )

    result = adapter.fetch_verified_beacon(1, now=round_available_at(1))

    assert result.network == QUICKNET
    assert result.round_number == 1
    assert result.signature == SIGNATURE
    assert result.randomness == RANDOMNESS
    assert result.relay == "https://one.invalid"
    assert json.loads(result.response_json) == BEACON


def test_invalid_first_relay_fails_over_to_valid_second_relay() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "one.invalid":
            return httpx.Response(200, json={**BEACON, "randomness": "00" * 32})
        return httpx.Response(200, json=BEACON)

    adapter = DrandAdapter(
        relays=("https://one.invalid", "https://two.invalid"),
        transport=httpx.MockTransport(handler),
    )

    result = adapter.fetch_verified_beacon(1, now=round_available_at(1))

    assert result.relay == "https://two.invalid"
    assert len(calls) == 2


def test_all_unverified_or_wrong_round_responses_are_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "one.invalid":
            return httpx.Response(200, json={**BEACON, "round": 2})
        return httpx.Response(200, json={**BEACON, "signature": "00" * 48})

    adapter = DrandAdapter(
        relays=("https://one.invalid", "https://two.invalid"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DrandVerificationError, match="locally verified"):
        adapter.fetch_verified_beacon(1, now=round_available_at(1))


def test_http_failure_can_use_another_relay() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "one.invalid":
            return httpx.Response(503)
        return httpx.Response(200, json=BEACON)

    adapter = DrandAdapter(
        relays=("https://one.invalid", "https://two.invalid"),
        transport=httpx.MockTransport(handler),
    )

    assert adapter.fetch_verified_beacon(1, now=round_available_at(1)).round_number == 1


def test_network_metadata_must_match_all_pinned_fields() -> None:
    adapter = DrandAdapter(
        relays=("https://one.invalid", "https://two.invalid"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={**INFO, "period": 30} if request.url.host == "one.invalid" else INFO,
            )
        ),
    )

    assert adapter.fetch_network_metadata() == QUICKNET


def test_no_valid_network_metadata_is_an_error() -> None:
    adapter = DrandAdapter(
        relays=("https://one.invalid",),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={**INFO, "hash": "00" * 32})
        ),
    )

    with pytest.raises(DrandVerificationError, match="pinned network metadata"):
        adapter.fetch_network_metadata()
