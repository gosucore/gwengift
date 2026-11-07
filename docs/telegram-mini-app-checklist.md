# Telegram Mini App and live deployment checklist

This checklist separates locally reproducible verification from checks that require a public HTTPS deployment and real Telegram bot credentials.

## Locally verified

- Production settings require a nonempty `GWENGIFT_TELEGRAM_BOT_TOKEN` and reject `GWENGIFT_DEV_IDENTITY_ENABLED=true`.
- Telegram launch data is verified with the bot-token HMAC, freshness window, and authenticated user payload. Client-supplied user IDs are not used as Telegram identities.
- When launch data is present, invalid data returns HTTP 401 even if development identity headers are also supplied; reset and bet mutations do not run.
- The browser sends `X-Telegram-Init-Data`, calls `ready()` and `expand()`, follows Telegram light/dark mode, and offers an explicit theme switch.
- The persistent `SIMULATION · DEMO ASSETS ONLY` label remains visible. No purchase, wallet, withdrawal, transfer, or real-NFT action exists.
- The single container serves the compiled SPA and API from one origin and runs the recovery/disclosure worker with persistent SQLite storage.
- `scripts/smoke-live.sh` resolves a real demo bet against drand quicknet, compares its proof with the official relay, checks the awarded inventory item, and verifies invalid-launch-data mutation rejection.

## Hosted deployment checks

Complete these with the actual bot and public deployment; they cannot be certified by localhost tests alone.

- [ ] Serve the application at a public HTTPS URL with a valid certificate and redirect or disallow plain HTTP.
- [ ] Set the same HTTPS URL as the Telegram Mini App URL in BotFather and open it through the bot's launch button.
- [ ] Confirm a real Telegram `initData` launch loads the correct demo account and survives navigation/reload.
- [ ] Confirm malformed, expired, and modified real launch data return HTTP 401 without balance, inventory, or history changes.
- [ ] Check light/dark Telegram themes, safe areas, keyboard/focus behavior, and bottom navigation on at least one iOS and one Android device.
- [ ] Complete one demo draw and verify pending → reveal, inventory, history, and round-audit navigation.
- [ ] Restart the hosted container and verify the same bet, ledger, and disclosure evidence remain available.
- [ ] Confirm drand/relay outages leave attempts pending until deadline and then restore the full demo debit; no local RNG fallback is permitted.
- [ ] Confirm production logs and responses contain no bot token, complete launch credentials, hidden manifests, or user identity data in public disclosures.

The hosted checklist must not be represented as completed until those external checks have actually run.
