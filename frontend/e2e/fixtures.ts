import type { Page, Route } from '@playwright/test';

const account = {
  telegram_user_id: 1001,
  username: 'mobile-player',
  demo_balance: 9856,
  active_epoch: 1,
  asset_mode: 'simulated',
};

const pool = {
  id: 'pool-1',
  version: 1,
  commitment: 'ab'.repeat(32),
  price: 144,
  expected_value: '128.75',
  actual_rtp: '0.89409722',
  rounding_premium_stars: '0.94',
  operator_margin: '9.25',
  remaining_count: 24,
  value_distribution: {
    minimum: '90',
    median: '122.5',
    maximum: '180',
    below_ticket_count: 14,
    at_or_above_ticket_count: 10,
  },
  commitment_algorithm: 'SHA-256/gift-pool-v1',
  draw_algorithm: 'gift-draw-v1',
};

const valuation = {
  primary_source: 'manual Stars-floor evidence',
  external_source: 'Data: TG Gifts (https://tggifts.com)',
  external_attribution: 'Data: TG Gifts (https://tggifts.com)',
  external_license: 'CC BY 4.0',
  source_currency: 'STARS',
  conversion_rule: {
    formula: 'external_stars = floor_gram',
    stars_per_gram: '1',
  },
  liquidity_discount: '0.05',
  observed_at: '2026-01-01T00:00:00',
  expires_at: '2026-01-02T00:00:00',
  stale: false,
  cross_check_discrepancy: '0.1',
  discrepancy_threshold: '0.35',
  discrepancy_action: 'pause',
};

const collectionNames = [
  'Plush Pepe',
  'Durov’s Cap',
  'Astral Shard',
  'Vintage Cigar',
  'Hypno Lollipop',
  'Jelly Bunny',
  'Sakura Flower',
  'Loot Bag',
  'Magic Potion',
  'Crystal Ball',
];

const collections = collectionNames.map((name, index) => ({
  id: index === 0 ? 'plush-pepe' : `collection-${index + 1}`,
  name,
  description: 'A finite pool of pre-minted virtual gifts with published odds.',
  status: 'OPEN',
  available: true,
  pool,
  valuation,
  asset_mode: 'simulated',
}));

const gift = {
  id: 'gift-1',
  model: 'Plush Pepe',
  backdrop: 'Midnight',
  symbol: 'Star',
  rarity: 'Rare',
  number: 2,
  player_sale_estimate: 180,
  ticket_price: 144,
  value_minus_ticket: 36,
};

const completedBet = {
  id: 'bet-complete',
  collection_id: 'plush-pepe',
  round_id: 'round-complete',
  pool_version_id: 'pool-1',
  pool_version_hash: pool.commitment,
  state: 'COMPLETED',
  price: 144,
  remaining_count: 24,
  future_beacon_round: 12345,
  acceptance_cutoff: '2026-01-01T00:00:02',
  resolution_deadline: '2026-01-01T00:01:03',
  created_at: '2026-01-01T00:00:00',
  resolved_at: '2026-01-01T00:00:03',
  cancellation_reason: null,
  gift,
  beacon: {
    network: 'quicknet',
    round: 12345,
    signature: 'ab'.repeat(48),
    randomness: 'cd'.repeat(32),
    verified_at: '2026-01-01T00:00:03',
  },
  asset_mode: 'simulated',
};

const pendingBet = {
  ...completedBet,
  id: 'bet-pending',
  round_id: 'round-current',
  state: 'PENDING_RANDOMNESS',
  resolved_at: null,
  gift: null,
  beacon: null,
};

const round = {
  id: 'round-current',
  status: 'OPEN',
  opens_at: '2026-01-01T00:00:00',
  closes_at: '2026-01-08T00:00:00',
  disclosure_deadline: '2026-01-08T00:00:00',
};

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

export async function mockApi(page: Page) {
  await page.route('**/api/account', (route) => fulfillJson(route, account));
  await page.route('**/api/collections', (route) =>
    fulfillJson(route, { collections, asset_mode: 'simulated' }),
  );
  await page.route('**/api/collections/plush-pepe', (route) =>
    fulfillJson(route, { ...collections[0], round }),
  );
  await page.route('**/api/bets/*', (route) =>
    fulfillJson(
      route,
      route.request().url().endsWith('bet-pending') ? pendingBet : completedBet,
    ),
  );
  await page.route('**/api/account/inventory', (route) =>
    fulfillJson(route, {
      gifts: [
        {
          ...gift,
          bet_id: 'bet-complete',
          round_id: 'round-complete',
          awarded_at: completedBet.resolved_at,
        },
      ],
      asset_mode: 'simulated',
    }),
  );
  await page.route('**/api/account/attempts', (route) =>
    fulfillJson(route, { attempts: [completedBet], asset_mode: 'simulated' }),
  );
  await page.route('**/api/rounds/*/audit', (route) => {
    const disclosed = route.request().url().includes('round-complete');
    return fulfillJson(route, {
      round: {
        ...round,
        id: disclosed ? 'round-complete' : 'round-current',
        status: disclosed ? 'DISCLOSED' : 'OPEN',
        disclosed_at: disclosed ? '2026-01-08T00:00:00' : null,
      },
      collection: {
        ...collections[0],
        status: disclosed ? 'PAUSED' : 'OPEN',
        available: !disclosed,
      },
      disclosure: disclosed
        ? {
            sha256: 'ef'.repeat(32),
            created_at: '2026-01-08T00:00:00',
            download_url: '/api/rounds/round-complete/disclosure',
          }
        : null,
      asset_mode: 'simulated',
    });
  });
  await page.route('**/api/rounds/round-complete/disclosure', (route) =>
    fulfillJson(route, {
      schema_version: 1,
      asset_mode: 'simulated',
      round: {
        ...round,
        id: 'round-complete',
        collection_id: 'plush-pepe',
        status: 'DISCLOSED',
      },
      algorithms: {
        pool_commitment: 'gift-pool-v1-sha256',
        selection: 'gift-draw-v1-sha256-rejection-v1',
        beacon: 'drand-quicknet-bls-unchained-g1-rfc9380',
        canonical_json: 'utf8-sorted-keys-compact',
      },
      pool_versions: [],
      market_snapshots: [],
      bets: [],
      gifts: [],
    }),
  );
}

export { account, collections, completedBet, gift, pendingBet, pool, round };
