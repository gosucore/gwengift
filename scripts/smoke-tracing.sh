#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
project="gwengift-tracing-smoke-$$"
compose=(docker compose --project-name "$project" -f compose.yaml -f compose.tracing.yaml)
export GWENGIFT_BACKEND_HOST_PORT="127.0.0.1:"
export GWENGIFT_JAEGER_HOST_PORT="127.0.0.1:"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    "${compose[@]}" logs --no-color --tail=100 || true
  fi
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${compose[@]}" up --build --detach backend worker jaeger
backend_url="http://$("${compose[@]}" port backend 8000)"
jaeger_url="http://$("${compose[@]}" port jaeger 16686)"

python3 - "$backend_url" "$jaeger_url" <<'PY'
import sys
import time
import urllib.request

backend_url, jaeger_url = sys.argv[1:]
for url in (backend_url + "/api/health", jaeger_url + "/api/services"):
    for _ in range(120):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise SystemExit(f"Service did not become healthy: {url}")
PY

"${compose[@]}" exec -T backend python -m alembic upgrade head
"${compose[@]}" exec -T backend python -m app.seeds

"${compose[@]}" exec -T backend python - <<'PY'
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

bet_id=$(python3 - "$backend_url" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
headers = {"X-Dev-Telegram-User-Id": "1001", "X-Dev-Username": "tracing-smoke"}
with urllib.request.urlopen(urllib.request.Request(base + "/api/account", headers=headers)) as response:
    assert json.load(response)["demo_balance"] == 10000
with urllib.request.urlopen(urllib.request.Request(base + "/api/collections/plush-pepe", headers=headers)) as response:
    detail = json.load(response)
body = json.dumps(
    {
        "collection_id": "plush-pepe",
        "pool_version_id": detail["pool"]["id"],
        "idempotency_key": "jaeger-tracing-smoke-v1",
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
print(bet["id"])
PY
)

python3 - "$backend_url" "$bet_id" <<'PY'
import json
import sys
import time
import urllib.request

base, bet_id = sys.argv[1:]
headers = {"X-Dev-Telegram-User-Id": "1001", "X-Dev-Username": "tracing-smoke"}
url = base + "/api/bets/" + bet_id
for _ in range(120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=3) as response:
        bet = json.load(response)
    if bet["state"] == "COMPLETED":
        assert bet["gift"] is not None and bet["beacon"] is not None
        break
    assert bet["state"] != "CANCELLED", bet
    time.sleep(1)
else:
    raise SystemExit("Traced demo bet did not complete")
PY

python3 - "$jaeger_url" "$bet_id" <<'PY'
import json
import sys
import time
import urllib.parse
import urllib.request

jaeger, bet_id = sys.argv[1:]


def traces(service):
    query = urllib.parse.urlencode({"service": service, "limit": 100})
    with urllib.request.urlopen(f"{jaeger}/api/traces?{query}", timeout=3) as response:
        payload = json.load(response)
    return [span for trace in payload.get("data", []) for span in trace.get("spans", [])]


def tags(span):
    return {tag["key"]: tag["value"] for tag in span.get("tags", [])}


def verify():
    with urllib.request.urlopen(jaeger + "/api/services", timeout=3) as response:
        services = set(json.load(response).get("data", []))
    assert {"gwengift-api", "gwengift-worker"} <= services
    api_spans = traces("gwengift-api")
    worker_spans = traces("gwengift-worker")
    created = next(span for span in api_spans if span.get("operationName") == "bet.create")
    resolved = next(span for span in worker_spans if span.get("operationName") == "draw.resolve")
    created_tags = tags(created)
    resolved_tags = tags(resolved)
    assert created_tags["gwengift.bet_id"] == resolved_tags["gwengift.bet_id"] == bet_id
    assert created_tags["gwengift.round_id"] == resolved_tags["gwengift.round_id"]
    assert resolved_tags["gwengift.outcome"] == "COMPLETED"
    all_spans = api_spans + worker_spans
    assert any(tags(span).get("db.system") == "sqlite" for span in all_spans)
    assert any(
        "/public/" in str(tags(span).get("url.full", tags(span).get("http.url", "")))
        for span in worker_spans
    )
    assert any(span.get("operationName") == "worker.pass" for span in worker_spans)
    return created_tags["gwengift.round_id"]


for _ in range(90):
    try:
        round_id = verify()
        break
    except (AssertionError, StopIteration, OSError):
        time.sleep(1)
else:
    raise SystemExit("Expected API, worker, database, and drand spans were not found in Jaeger")

print(json.dumps({"bet_id": bet_id, "round_id": round_id, "jaeger": "verified", "correlation": "ok"}, sort_keys=True))
PY
