import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.services.drand import QUICKNET, DrandNetwork, verify_quicknet_beacon

DEFAULT_RELAYS = (
    "https://api.drand.sh",
    "https://api2.drand.sh",
    "https://api3.drand.sh",
    "https://drand.cloudflare.com",
)


class DrandAdapterError(RuntimeError):
    pass


class BeaconNotAvailableError(DrandAdapterError):
    pass


class DrandVerificationError(DrandAdapterError):
    pass


@dataclass(frozen=True)
class BeaconTarget:
    round_number: int
    available_at: datetime
    acceptance_cutoff: datetime


@dataclass(frozen=True)
class VerifiedBeacon:
    network: DrandNetwork
    round_number: int
    signature: str
    randomness: str
    relay: str
    response_json: str


class BeaconResponse(BaseModel):
    round: int
    randomness: str
    signature: str


class InfoResponse(BaseModel):
    public_key: str
    period: int
    genesis_time: int
    hash: str
    schemeID: str
    metadata: dict[str, str]


def _timestamp(value: datetime) -> float:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.timestamp()


def _naive_utc(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)


def round_available_at(round_number: int, network: DrandNetwork = QUICKNET) -> datetime:
    if round_number < 1:
        raise ValueError("Drand rounds start at 1")
    return _naive_utc(network.genesis_time + (round_number - 1) * network.period_seconds)


def select_future_round(
    now: datetime,
    *,
    minimum_delay_seconds: int = 6,
    acceptance_margin_seconds: int = 1,
    network: DrandNetwork = QUICKNET,
) -> BeaconTarget:
    if minimum_delay_seconds <= acceptance_margin_seconds or acceptance_margin_seconds < 0:
        raise ValueError("Future-round delay must exceed the nonnegative acceptance margin")
    now = _naive_utc(_timestamp(now))
    candidate_time = _timestamp(now) + minimum_delay_seconds
    round_number = max(
        1,
        math.floor((candidate_time - network.genesis_time) / network.period_seconds) + 1,
    )
    available_at = round_available_at(round_number, network)
    acceptance_cutoff = _naive_utc(_timestamp(available_at) - acceptance_margin_seconds)
    if acceptance_cutoff <= now:
        raise ValueError("Selected beacon round would already have passed its acceptance cutoff")
    return BeaconTarget(round_number, available_at, acceptance_cutoff)


class DrandAdapter:
    def __init__(
        self,
        *,
        network: DrandNetwork = QUICKNET,
        relays: tuple[str, ...] = DEFAULT_RELAYS,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 5,
    ) -> None:
        if not relays:
            raise ValueError("At least one drand relay is required")
        if network != QUICKNET:
            raise ValueError("Only the pinned quicknet verification scheme is supported")
        self.network = network
        self.relays = tuple(relay.rstrip("/") for relay in relays)
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def _get_json(self, relay: str, path: str) -> dict[str, Any]:
        with httpx.Client(transport=self.transport, timeout=self.timeout_seconds) as client:
            response = client.get(f"{relay}/{self.network.chain_hash}/{path}")
            response.raise_for_status()
            payload: Any = response.json()
        if not isinstance(payload, dict):
            raise DrandAdapterError("Drand response must be a JSON object")
        return payload

    def fetch_network_metadata(self) -> DrandNetwork:
        last_error: Exception | None = None
        for relay in self.relays:
            try:
                info = InfoResponse.model_validate(self._get_json(relay, "info"))
                if (
                    info.public_key != self.network.public_key
                    or info.period != self.network.period_seconds
                    or info.genesis_time != self.network.genesis_time
                    or info.hash != self.network.chain_hash
                    or info.schemeID != self.network.scheme
                    or info.metadata.get("beaconID") != self.network.beacon_id
                ):
                    raise DrandVerificationError("Relay returned different network metadata")
                return self.network
            except (httpx.HTTPError, ValidationError, DrandAdapterError, ValueError) as exc:
                last_error = exc
        raise DrandVerificationError(
            "No relay returned the pinned network metadata"
        ) from last_error

    def fetch_verified_beacon(self, round_number: int, *, now: datetime) -> VerifiedBeacon:
        now = _naive_utc(_timestamp(now))
        if now < round_available_at(round_number, self.network):
            raise BeaconNotAvailableError("Committed drand round has not resolved yet")

        last_error: Exception | None = None
        for relay in self.relays:
            try:
                payload = self._get_json(relay, f"public/{round_number}")
                beacon = BeaconResponse.model_validate(payload)
                if beacon.round != round_number or not verify_quicknet_beacon(
                    beacon.round,
                    beacon.signature,
                    beacon.randomness,
                    public_key_hex=self.network.public_key,
                ):
                    raise DrandVerificationError("Relay returned an invalid drand proof")
                return VerifiedBeacon(
                    network=self.network,
                    round_number=beacon.round,
                    signature=beacon.signature,
                    randomness=beacon.randomness,
                    relay=relay,
                    response_json=json.dumps(
                        beacon.model_dump(), sort_keys=True, separators=(",", ":")
                    ),
                )
            except (httpx.HTTPError, ValidationError, DrandAdapterError, ValueError) as exc:
                last_error = exc
        raise DrandVerificationError(
            "No relay returned a locally verified beacon for the committed round"
        ) from last_error
