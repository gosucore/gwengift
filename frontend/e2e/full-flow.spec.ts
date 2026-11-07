import { expect, test } from '@playwright/test';
import {
  collections,
  completedBet,
  gift,
  mockApi,
  pendingBet,
  pool,
  round,
} from './fixtures';

const launchData = 'signed-e2e-launch-data';

const disclosure = {
  schema_version: 1,
  asset_mode: 'simulated',
  round: {
    ...round,
    id: 'round-complete',
    collection_id: 'plush-pepe',
    status: 'DISCLOSED',
    disclosed_at: '2026-01-08T00:00:00',
  },
  algorithms: {
    pool_commitment: 'gift-pool-v1-sha256',
    selection: 'gift-draw-v1-sha256-rejection-v1',
    beacon: 'drand-quicknet-bls-unchained-g1-rfc9380',
    canonical_json: 'utf8-sorted-keys-compact',
  },
  pool_versions: [
    {
      ...pool,
      remaining_count: 1,
      manifest: {
        schema_version: 1,
        gifts: [
          {
            id: gift.id,
            model: gift.model,
            backdrop: gift.backdrop,
            symbol: gift.symbol,
            rarity: gift.rarity,
            number: gift.number,
            player_sale_estimate: gift.player_sale_estimate,
            replacement_cost: 185,
          },
        ],
      },
      market_snapshot_id: 'snapshot-1',
      created_at: '2026-01-01T00:00:00',
    },
  ],
  market_snapshots: [
    {
      id: 'snapshot-1',
      collection_id: 'plush-pepe',
      primary_source: 'manual Stars-floor evidence',
      external_source: 'Data: TG Gifts',
      source_currency: 'STARS',
      conversion_rule: '{}',
      liquidity_discount: '0.05',
      source_payload: { manual: { evidence: 'deterministic-e2e-fixture' } },
      provenance: {},
      cross_check_discrepancy: '0.1',
      observed_at: '2026-01-01T00:00:00',
      expires_at: '2026-01-02T00:00:00',
      created_at: '2026-01-01T00:00:00',
    },
  ],
  bets: [
    {
      id: completedBet.id,
      user_epoch: 1,
      pool_version_id: pool.id,
      pool_version_hash: pool.commitment,
      idempotency_key: 'deterministic-e2e-attempt',
      future_beacon_round: completedBet.future_beacon_round,
      acceptance_cutoff: completedBet.acceptance_cutoff,
      resolution_deadline: completedBet.resolution_deadline,
      state: 'COMPLETED',
      price: completedBet.price,
      remaining_count: 1,
      selected_gift_id: gift.id,
      cancellation_reason: null,
      created_at: completedBet.created_at,
      resolved_at: completedBet.resolved_at,
      ledger_entries: [
        {
          id: 'ledger-1',
          kind: 'DEBIT',
          amount: -144,
          balance_after: 9856,
          created_at: completedBet.created_at,
        },
      ],
      beacon_proof: {
        network: completedBet.beacon.network,
        round: completedBet.beacon.round,
        signature: completedBet.beacon.signature,
        randomness: completedBet.beacon.randomness,
        verification_result: true,
        response: {},
        verified_at: completedBet.beacon.verified_at,
      },
    },
  ],
  gifts: [
    {
      id: gift.id,
      model: gift.model,
      backdrop: gift.backdrop,
      symbol: gift.symbol,
      rarity: gift.rarity,
      number: gift.number,
      player_sale_estimate: gift.player_sale_estimate,
      replacement_cost: 185,
      lifecycle: 'AWARDED',
      owner_epoch: 1,
    },
  ],
};

test('complete Telegram mobile demo flow with deterministic randomness', async ({
  page,
}) => {
  let balance = 10000;
  let epoch = 1;
  let betCreated = false;
  let betReads = 0;
  let signedAccountRequest = false;
  let signedBetRequest = false;
  let betRequestBody: Record<string, unknown> | null = null;

  await mockApi(page);
  await page.addInitScript((initData) => {
    window.Telegram = {
      WebApp: {
        initData,
        colorScheme: 'light',
        themeParams: {},
        ready: () => undefined,
        expand: () => undefined,
        onEvent: () => undefined,
        offEvent: () => undefined,
      },
    };
  }, launchData);

  await page.route('**/api/account', (route) => {
    signedAccountRequest =
      route.request().headers()['x-telegram-init-data'] === launchData;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        telegram_user_id: 1001,
        username: 'mobile-player',
        demo_balance: balance,
        active_epoch: epoch,
        asset_mode: 'simulated',
      }),
    });
  });
  await page.route('**/api/bets', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    signedBetRequest =
      route.request().headers()['x-telegram-init-data'] === launchData;
    betRequestBody = route.request().postDataJSON() as Record<string, unknown>;
    betCreated = true;
    balance = 9856;
    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ ...pendingBet, id: completedBet.id }),
    });
  });
  await page.route('**/api/bets/bet-complete', (route) => {
    betReads += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        betReads === 1 ? { ...pendingBet, id: completedBet.id } : completedBet,
      ),
    });
  });
  await page.route('**/api/account/inventory', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        gifts:
          betCreated && epoch === 1
            ? [
                {
                  ...gift,
                  bet_id: completedBet.id,
                  round_id: 'round-complete',
                  awarded_at: completedBet.resolved_at,
                },
              ]
            : [],
        asset_mode: 'simulated',
      }),
    }),
  );
  await page.route('**/api/account/attempts', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        attempts: betCreated && epoch === 1 ? [completedBet] : [],
        asset_mode: 'simulated',
      }),
    }),
  );
  await page.route('**/api/account/reset', (route) => {
    epoch = 2;
    balance = 10000;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        telegram_user_id: 1001,
        username: 'mobile-player',
        demo_balance: balance,
        active_epoch: epoch,
        asset_mode: 'simulated',
      }),
    });
  });
  await page.route('**/api/rounds/round-complete/audit', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        round: disclosure.round,
        collection: {
          ...collections[0],
          status: 'PAUSED',
          available: false,
        },
        disclosure: {
          sha256: 'ef'.repeat(32),
          created_at: '2026-01-08T00:00:00',
          download_url: '/api/rounds/round-complete/disclosure',
        },
        asset_mode: 'simulated',
      }),
    }),
  );
  await page.unroute('**/api/rounds/round-complete/disclosure');
  await page
    .context()
    .route('**/api/rounds/round-complete/disclosure', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Content-Disposition':
            'attachment; filename="round-complete-disclosure.json"',
        },
        body: JSON.stringify(disclosure),
      }),
    );

  await page.goto('/');
  await expect(page.getByText('10,000')).toBeVisible();
  await expect(page.getByRole('article')).toHaveCount(10);
  expect(signedAccountRequest).toBe(true);
  await expect(page.getByText('SIMULATION · DEMO ASSETS ONLY')).toBeVisible();

  await page.getByRole('link', { name: 'Plush Pepe', exact: true }).click();
  await page.getByRole('button', { name: 'Review 144 ★ demo ticket' }).click();
  await page.getByRole('button', { name: 'Confirm 144 ★' }).click();
  await expect(page).toHaveURL(/\/bets\/bet-complete$/);
  expect(signedBetRequest).toBe(true);
  expect(betRequestBody).toEqual({
    collection_id: 'plush-pepe',
    pool_version_id: 'pool-1',
    idempotency_key: expect.any(String),
  });
  await expect(
    page.getByRole('heading', { name: 'Waiting for verified randomness' }),
  ).toBeVisible();
  await expect(page.getByText('Committed to drand round 12345')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Gift revealed' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Plush Pepe #2' }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Plush Pepe', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('36 ★ above the ticket')).toBeVisible();
  await expect(page.getByText(/randomness: cdcd/)).toBeVisible();

  await page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('link', { name: 'Inventory' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Plush Pepe #2' }),
  ).toBeVisible();
  await expect(page.getByText('Midnight')).toBeVisible();

  await page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('link', { name: 'History' })
    .click();
  await expect(page.getByText('Completed', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reset demo progress' }).click();
  await page.getByRole('button', { name: 'Yes, reset demo' }).click();
  await expect(
    page.getByRole('heading', { name: 'No attempts in this demo epoch' }),
  ).toBeVisible();
  await expect(page.getByText('10,000')).toBeVisible();

  await page.goto('/inventory');
  await expect(
    page.getByRole('heading', { name: 'No virtual gifts yet' }),
  ).toBeVisible();

  await page.goto('/rounds/round-complete/audit');
  await expect(
    page.getByRole('heading', { name: 'Complete disclosure' }),
  ).toBeVisible();
  await page.getByText('Version 1 · 1 gifts · 144 ★').click();
  await page.getByText('snapshot-1', { exact: true }).click();
  await expect(page.getByText('deterministic-e2e-fixture')).toBeVisible();
  await page.locator('summary').filter({ hasText: 'bet-comp' }).click();
  await expect(page.getByText(/signature: abab/)).toBeVisible();
  await expect(page.getByText(/python -m app.verify_disclosure/)).toBeVisible();

  const downloadLink = page.getByRole('link', {
    name: 'Download disclosure JSON',
  });
  await expect(downloadLink).toHaveAttribute(
    'href',
    '/api/rounds/round-complete/disclosure',
  );
  await expect(downloadLink).toHaveAttribute(
    'download',
    'round-complete-disclosure.json',
  );
});
