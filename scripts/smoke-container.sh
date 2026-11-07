#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
suffix="$$"
image="gwengift:smoke"
container="gwengift-smoke-${suffix}"
volume="gwengift-smoke-data-${suffix}"
base=""

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
  "$image" >/dev/null

mapping=$(docker port "$container" 8000/tcp)
port=${mapping##*:}
base="http://127.0.0.1:${port}"

wait_for_health() {
  python3 - "$base" <<'PY'
import sys
import time
import urllib.request

url = sys.argv[1] + "/api/health"
for _ in range(90):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
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

audit_round=$(docker exec -i "$container" python - <<'PY'
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Round, VirtualGift
from app.services.disclosures import disclose_round
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version

now = datetime.now(UTC).replace(tzinfo=None)
settings = get_settings()
with SessionLocal() as session:
    for collection_id in ("plush-pepe", "durovs-cap"):
        gifts = list(
            session.scalars(
                select(VirtualGift)
                .where(VirtualGift.collection_id == collection_id)
                .order_by(VirtualGift.number)
            ).all()
        )
        floor = min(gift.player_sale_estimate for gift in gifts)
        session.commit()
        manual = {
            "schema_version": 1,
            "collection_id": collection_id,
            "observed_at": now.isoformat(),
            "liquidity_discount": "0",
            "gifts": [
                {
                    "number": gift.number,
                    "floor_stars": gift.player_sale_estimate,
                    "evidence_url": f"https://evidence.example/{collection_id}/{gift.number}",
                }
                for gift in gifts
            ],
        }
        external = {
            "source": "TG Gifts (tggifts.com)",
            "license": "CC BY 4.0",
            "generated": now.isoformat(),
            "collections": {
                collection_id: {
                    "name": collection_id,
                    "days": [[now.date().isoformat(), floor, 5]],
                }
            },
        }
        snapshot = import_market_snapshot(
            session,
            collection_id,
            manual,
            external,
            stars_per_gram=Decimal(1),
            settings=settings,
            now=now,
        )
        session.commit()
        round_ = session.scalar(select(Round).where(Round.collection_id == collection_id))
        assert round_ is not None
        session.commit()
        create_pool_version(session, round_.id, snapshot.id, settings=settings, now=now)
        if collection_id == "durovs-cap":
            audit_round_id = round_.id
            round_.disclosure_deadline = now - timedelta(seconds=1)
            session.commit()
            disclose_round(session, audit_round_id, now=now)
print(audit_round_id)
PY
)

bet_id=$(python3 - "$base" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
headers = {"X-Dev-Telegram-User-Id": "1001", "X-Dev-Username": "smoke"}
with urllib.request.urlopen(urllib.request.Request(base + "/api/account", headers=headers)) as response:
    assert json.load(response)["demo_balance"] == 10000
with urllib.request.urlopen(urllib.request.Request(base + "/api/collections/plush-pepe", headers=headers)) as response:
    detail = json.load(response)
pool_id = detail["pool"]["id"]
body = json.dumps(
    {
        "collection_id": "plush-pepe",
        "pool_version_id": pool_id,
        "idempotency_key": "container-restart-smoke-v1",
    }
).encode()
request = urllib.request.Request(
    base + "/api/bets",
    data=body,
    headers={**headers, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request) as response:
    bet = json.load(response)
assert bet["state"] == "PENDING_RANDOMNESS"
assert bet["gift"] is None
print(bet["id"])
PY
)

docker restart "$container" >/dev/null
mapping=$(docker port "$container" 8000/tcp)
port=${mapping##*:}
base="http://127.0.0.1:${port}"
if ! wait_for_health; then
  docker logs "$container"
  exit 1
fi

python3 - "$base" "$bet_id" "$audit_round" <<'PY'
import hashlib
import json
import sys
import urllib.request

base, bet_id, round_id = sys.argv[1:]
headers = {"X-Dev-Telegram-User-Id": "1001", "X-Dev-Username": "smoke"}
with urllib.request.urlopen(urllib.request.Request(base + "/api/bets/" + bet_id, headers=headers)) as response:
    bet = json.load(response)
assert bet["id"] == bet_id and bet["price"] == 144
assert bet["state"] in {"PENDING_RANDOMNESS", "RESOLVING", "COMPLETED"}
with urllib.request.urlopen(base + "/api/rounds/" + round_id + "/disclosure") as response:
    package_bytes = response.read()
    package = json.loads(package_bytes)
    assert response.headers["X-Disclosure-SHA256"] == hashlib.sha256(package_bytes).hexdigest()
assert package["round"]["id"] == round_id
assert package["round"]["status"] == "DISCLOSED"
with urllib.request.urlopen(base + "/collections/plush-pepe") as response:
    html = response.read().decode()
assert '<div id="root"></div>' in html
print(json.dumps({"restart": "ok", "bet_id": bet_id, "bet_state": bet["state"], "disclosure": "ok", "spa": "ok"}, sort_keys=True))
PY
