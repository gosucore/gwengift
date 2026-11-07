#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
suffix="$$"
image="gwengift:smoke"
container="gwengift-live-smoke-${suffix}"
volume="gwengift-live-smoke-data-${suffix}"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker build -t "$image" .
docker run --detach \
  --name "$container" \
  --volume "$volume:/data" \
  --publish 127.0.0.1::8000 \
  --env GWENGIFT_ENVIRONMENT=development \
  --env GWENGIFT_DEV_IDENTITY_ENABLED=true \
  --env GWENGIFT_TELEGRAM_BOT_TOKEN=local-smoke-token \
  "$image" >/dev/null

mapping=$(docker port "$container" 8000/tcp)
base="http://127.0.0.1:${mapping##*:}"

wait_for_health() {
  python3 - "$base" <<'PY'
import sys
import time
import urllib.request

for _ in range(90):
    try:
        with urllib.request.urlopen(sys.argv[1] + "/api/health", timeout=2) as response:
            if response.status == 200:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit("Container did not become healthy")
PY
}

if ! wait_for_health; then
  docker logs "$container"
  exit 1
fi

docker exec -i "$container" python - <<'PY'
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Round, VirtualGift
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version

now = datetime.now(UTC).replace(tzinfo=None)
settings = get_settings()
with SessionLocal() as session:
    gifts = list(
        session.scalars(
            select(VirtualGift)
            .where(VirtualGift.collection_id == "plush-pepe")
            .order_by(VirtualGift.number)
        ).all()
    )
    floor = min(gift.player_sale_estimate for gift in gifts)
    session.commit()
    manual = {
        "schema_version": 1,
        "collection_id": "plush-pepe",
        "observed_at": now.isoformat(),
        "liquidity_discount": "0",
        "gifts": [
            {
                "number": gift.number,
                "floor_stars": gift.player_sale_estimate,
                "evidence_url": f"https://evidence.example/plush-pepe/{gift.number}",
            }
            for gift in gifts
        ],
    }
    external = {
        "source": "TG Gifts (tggifts.com)",
        "license": "CC BY 4.0",
        "generated": now.isoformat(),
        "collections": {
            "plush-pepe": {
                "name": "Plush Pepe",
                "days": [[now.date().isoformat(), floor, 5]],
            }
        },
    }
    snapshot = import_market_snapshot(
        session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=settings,
        now=now,
    )
    session.commit()
    round_ = session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    session.commit()
    create_pool_version(session, round_.id, snapshot.id, settings=settings, now=now)
PY

python3 - "$base" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1]
dev_headers = {"X-Dev-Telegram-User-Id": "1001", "X-Dev-Username": "live-smoke"}
chain = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"


def request(path, *, headers=None, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    return urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            **(headers or {}),
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )


try:
    urllib.request.urlopen(
        request(
            "/api/account/reset",
            method="POST",
            headers={
                **dev_headers,
                "X-Telegram-Init-Data": "auth_date=1&user=invalid&hash=invalid",
            },
        )
    )
except urllib.error.HTTPError as exc:
    assert exc.code == 401
else:
    raise AssertionError("Invalid Telegram launch data unexpectedly mutated state")

with urllib.request.urlopen(request("/api/account", headers=dev_headers)) as response:
    account = json.load(response)
assert account["demo_balance"] == 10000 and account["active_epoch"] == 1
with urllib.request.urlopen(request("/api/collections/plush-pepe", headers=dev_headers)) as response:
    pool_id = json.load(response)["pool"]["id"]
with urllib.request.urlopen(
    request(
        "/api/bets",
        method="POST",
        headers=dev_headers,
        body={
            "collection_id": "plush-pepe",
            "pool_version_id": pool_id,
            "idempotency_key": "live-drand-container-smoke-v1",
        },
    )
) as response:
    bet = json.load(response)
assert bet["state"] == "PENDING_RANDOMNESS"
bet_id = bet["id"]
target_round = bet["future_beacon_round"]

for _ in range(90):
    with urllib.request.urlopen(request("/api/bets/" + bet_id, headers=dev_headers)) as response:
        bet = json.load(response)
    if bet["state"] == "COMPLETED":
        break
    if bet["state"] == "CANCELLED":
        raise AssertionError("Live draw cancelled: " + str(bet["cancellation_reason"]))
    time.sleep(1)
else:
    raise AssertionError("Live draw did not resolve before its deadline")

assert bet["gift"] is not None
assert bet["beacon"]["round"] == target_round
assert len(bet["beacon"]["signature"]) == 96
assert len(bet["beacon"]["randomness"]) == 64
with urllib.request.urlopen(
    f"https://api.drand.sh/{chain}/public/{target_round}", timeout=10
) as response:
    official = json.load(response)
assert official["round"] == target_round
assert official["signature"] == bet["beacon"]["signature"]
assert official["randomness"] == bet["beacon"]["randomness"]
with urllib.request.urlopen(request("/api/account/inventory", headers=dev_headers)) as response:
    inventory = json.load(response)
assert [item["id"] for item in inventory["gifts"]] == [bet["gift"]["id"]]
with urllib.request.urlopen(request("/api/account", headers=dev_headers)) as response:
    account = json.load(response)
assert account["demo_balance"] == 9856 and account["active_epoch"] == 1
print(
    json.dumps(
        {
            "live_drand": "verified",
            "beacon_round": target_round,
            "bet_id": bet_id,
            "gift_id": bet["gift"]["id"],
            "invalid_init_data_mutation": "rejected",
        },
        sort_keys=True,
    )
)
PY
