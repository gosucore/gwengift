# GwenGift

A portfolio demo of a Telegram Mini App for provably fair virtual gift draws. **All Stars, gifts, balances, valuations, and winnings are simulated.** The application has no purchases, withdrawals, wallets, real NFT transfers, or real-money functionality.

## Requirements

- Python 3.11+
- Node.js 18+ and npm
- Or Docker with Docker Compose

## Local development

Start the backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

In another terminal, start the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to http://127.0.0.1:8000; the health endpoint is http://localhost:8000/api/health. The API schema is available at http://localhost:8000/docs.

Development defaults do not enable the development identity adapter. Set `GWENGIFT_DEV_IDENTITY_ENABLED=true` explicitly in `backend/.env` when local browser testing is needed. Production requires `GWENGIFT_TELEGRAM_BOT_TOKEN` and rejects the development identity adapter.

## Docker Compose

From the repository root:

```bash
docker compose up --build
```

Open http://localhost:5173. Compose enables the development identity adapter only in this development configuration and stores the SQLite database in the `gwengift-data` volume. Stop the services with `docker compose down`; add `--volumes` only when you intend to delete demo data.

## Single-container deployment

`Dockerfile` builds the React application, installs the backend, and runs migrations, catalog seeding, the recovery/disclosure worker, and Uvicorn in one image. FastAPI serves the compiled SPA and API from the same origin. SQLite and the market cache use the persistent `/data` volume.

For production, provide the Telegram bot token through the environment and terminate HTTPS at a trusted reverse proxy:

```bash
export GWENGIFT_TELEGRAM_BOT_TOKEN='your-bot-token'
docker compose -f compose.production.yaml up --build -d
```

The production configuration rejects missing bot credentials and the development identity adapter. For an explicitly local, non-production container demo only:

```bash
GWENGIFT_ENVIRONMENT=development GWENGIFT_DEV_IDENTITY_ENABLED=true \
  docker compose -f compose.production.yaml up --build
```

Open http://localhost:8000. Telegram Mini Apps must use the HTTPS deployment URL; plain HTTP is suitable only for local testing. Do not publish a deployment with the development identity adapter enabled.

Verify image startup and persistent restart recovery with the self-cleaning smoke test:

```bash
scripts/smoke-container.sh
```

The script builds the image, creates a demo bet and disclosed round, restarts the container on the same volume, then checks the persisted bet, exact disclosure hash, and compiled SPA response. It removes only its own temporary container and volume.

## Quality checks

Backend:

```bash
cd backend
.venv/bin/python -m ruff format --check app tests
.venv/bin/python -m ruff check app tests
.venv/bin/python -m mypy app tests
.venv/bin/python -m pytest
```

Frontend:

```bash
cd frontend
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

Use `ruff format app tests` and `npm run format` to apply formatting.

## Market data attribution

The optional external cross-check uses the free TG Gifts daily floor dataset. Data: [TG Gifts](https://tggifts.com) ([daily floors](https://tggifts.com/data/floors-daily.json)), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Manual Stars-floor snapshots remain the primary valuation source. External prices are reference data only, not executable offers.

## Economic risk report

After seeding a collection and importing its market snapshot, run a reproducible report:

```bash
cd backend
.venv/bin/python -m app.services.risk --collection-id plush-pepe --seed review-1 --volume 1000 --simulations 1000
```

The JSON report includes theoretical expected margin, simulated final outcomes, maximum drawdown, and p95/max reserve requirements. Expected margin is not a short-term profit guarantee; the simulation uses replacement costs, ticket price, and configured fees for virtual assets only.

## Verified randomness

The draw protocol uses drand quicknet and verifies every BLS signature locally with `blspy`. See [drand verification protocol](docs/drand-verification.md) for the selected network, signature scheme, official vectors, and offline test command. Relay failures must not fall back to local randomness. The [deterministic selection protocol](docs/draw-selection.md) documents domain separation, rejection sampling, and replay vectors.

Run the self-cleaning live container smoke test to resolve one real quicknet-backed demo draw and verify invalid launch data cannot reset the account:

```bash
scripts/smoke-live.sh
```

The [Telegram Mini App checklist](docs/telegram-mini-app-checklist.md) separates these local checks from hosted HTTPS/BotFather checks that require a real deployment.

## Independent round audit

After sell-out or deadline disclosure, download `/api/rounds/{round_id}/disclosure` and verify the complete package offline:

```bash
cd backend
.venv/bin/python -m app.verify_disclosure ./disclosure.json
```

The [disclosure schema and verification guide](docs/disclosure-verification.md) explains canonicalization, economic recomputation, beacon checks, selection replay, and failure behavior.

## Configuration

Environment variables use the `GWENGIFT_` prefix. See `backend/.env.example` for development settings. `.env` files and local data are ignored by Git; never commit production credentials.
