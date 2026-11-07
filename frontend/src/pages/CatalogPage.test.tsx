import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type Catalog, type CollectionDetail } from '../api/client';
import type { components } from '../api/schema';
import { CatalogPage } from '../pages/CatalogPage';
import { CollectionPage } from '../pages/CollectionPage';

vi.mock('../api/client', () => ({
  api: {
    getCatalog: vi.fn(),
    getCollection: vi.fn(),
  },
}));

vi.mock('../appContext', () => ({
  useAppContext: () => ({
    account: { demo_balance: 10000 },
    refreshAccount: vi.fn(),
  }),
}));

type Summary = components['schemas']['CollectionSummary'];

const pool: components['schemas']['PublicPoolVersion'] = {
  id: 'pool-2',
  version: 2,
  commitment: 'a'.repeat(64),
  price: 144,
  expected_value: '128.75000000',
  actual_rtp: '0.89409722',
  rounding_premium_stars: '0.94444444',
  operator_margin: '9.25000000',
  remaining_count: 3,
  value_distribution: {
    minimum: '90',
    median: '110',
    maximum: '180',
    below_ticket_count: 2,
    at_or_above_ticket_count: 1,
  },
  commitment_algorithm: 'SHA-256/gift-pool-v1',
  draw_algorithm: 'gift-draw-v1',
};

const valuation: components['schemas']['PublicValuation'] = {
  primary_source: 'manual Stars-floor evidence',
  external_source: 'Data: TG Gifts (https://tggifts.com)',
  external_attribution: 'Data: TG Gifts (https://tggifts.com)',
  external_license: 'CC BY 4.0',
  source_currency: 'STARS; external cross-check GRAM',
  conversion_rule: {
    formula: 'external_stars = floor_gram * stars_per_gram',
    stars_per_gram: '1',
  },
  liquidity_discount: '0',
  observed_at: '2026-01-01T00:00:00',
  expires_at: '2026-01-02T00:00:00',
  stale: false,
  cross_check_discrepancy: '0.1',
  discrepancy_threshold: '0.35',
  discrepancy_action: 'pause',
};

function collection(id: string, overrides: Partial<Summary> = {}): Summary {
  return {
    id,
    name: `Collection ${id}`,
    description: 'A finite pool of pre-minted virtual gifts.',
    status: 'OPEN',
    asset_mode: 'simulated',
    available: true,
    pool,
    valuation,
    ...overrides,
  };
}

function detail(overrides: Partial<Summary> = {}): CollectionDetail {
  return {
    ...collection('plush-pepe', overrides),
    round: {
      id: 'round-1',
      status: 'OPEN',
      opens_at: '2026-01-01T00:00:00',
      closes_at: '2026-01-08T00:00:00',
      disclosure_deadline: '2026-01-08T00:00:00',
    },
  };
}

function renderCatalog() {
  return render(
    <MemoryRouter>
      <CatalogPage />
    </MemoryRouter>,
  );
}

describe('collection catalog', () => {
  beforeEach(() => {
    vi.mocked(api.getCatalog).mockResolvedValue({
      collections: [],
      asset_mode: 'simulated',
    });
  });

  afterEach(cleanup);

  it('renders ten comparable collections with price, RTP, value, and quantity', async () => {
    vi.mocked(api.getCatalog).mockResolvedValue({
      collections: Array.from({ length: 10 }, (_, index) =>
        collection(`c${index + 1}`),
      ),
      asset_mode: 'simulated',
    });
    renderCatalog();

    expect(await screen.findAllByRole('article')).toHaveLength(10);
    expect(screen.getAllByText('144 ★')).toHaveLength(10);
    expect(screen.getAllByText('89.41%')).toHaveLength(10);
    expect(screen.getAllByText('128.75 ★')).toHaveLength(10);
    expect(screen.getAllByText('3')).toHaveLength(10);
  });

  it('shows loading and empty states', async () => {
    let resolve: (value: Catalog) => void = () => undefined;
    vi.mocked(api.getCatalog).mockReturnValue(
      new Promise<Catalog>((next) => {
        resolve = next;
      }),
    );
    renderCatalog();
    expect(screen.getByRole('status')).toHaveTextContent('Loading collections');

    resolve({ collections: [], asset_mode: 'simulated' });
    expect(
      await screen.findByText('No collections are configured.'),
    ).toBeVisible();
  });

  it('explains paused, stale, and market discrepancy states', async () => {
    vi.mocked(api.getCatalog).mockResolvedValue({
      collections: [
        collection('paused', { status: 'PAUSED', available: false }),
        collection('stale', {
          status: 'PAUSED',
          available: false,
          valuation: { ...valuation, stale: true },
        }),
        collection('discrepancy', {
          status: 'PAUSED',
          available: false,
          valuation: { ...valuation, cross_check_discrepancy: '0.50' },
        }),
      ],
      asset_mode: 'simulated',
    });
    renderCatalog();

    expect(
      await screen.findByText(
        'Collection paused — new attempts are unavailable.',
      ),
    ).toBeVisible();
    expect(screen.getByText(/Valuation is stale/)).toBeVisible();
    expect(screen.getByText(/Market sources disagree \(50.0%/)).toBeVisible();
    expect(screen.getByText(/policy: pause/)).toBeVisible();
  });

  it('supports retry after a catalog request failure', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getCatalog)
      .mockRejectedValueOnce(new Error('Catalog offline'))
      .mockResolvedValueOnce({
        collections: [collection('one')],
        asset_mode: 'simulated',
      });
    renderCatalog();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Catalog offline',
    );
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('article')).toHaveTextContent(
      'Collection one',
    );
  });
});

describe('collection detail', () => {
  afterEach(cleanup);

  it('shows aggregate economics, commitment, round deadline, and provenance', async () => {
    vi.mocked(api.getCollection).mockResolvedValue(detail());
    render(
      <MemoryRouter initialEntries={['/collections/plush-pepe']}>
        <CollectionPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('heading', { name: 'Collection plush-pepe' }),
    ).toBeVisible();
    expect(screen.getByText('Current pool · version 2')).toBeVisible();
    expect(screen.getByText('0.94 ★')).toBeVisible();
    expect(screen.getByText('9.25 ★')).toBeVisible();
    expect(screen.getByText('a'.repeat(64))).toBeVisible();
    expect(screen.getByText('manual Stars-floor evidence')).toBeVisible();
    expect(screen.getByText(/external_stars = floor_gram/)).toBeVisible();
    expect(screen.getByText(/CC BY 4.0/)).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Fairness & round audit' }),
    ).toHaveAttribute('href', '/rounds/round-1/audit');
  });

  it('renders an empty unpriced collection without invented economics', async () => {
    vi.mocked(api.getCollection).mockResolvedValue(
      detail({
        pool: null,
        valuation: null,
        status: 'PAUSED',
        available: false,
      }),
    );
    render(
      <MemoryRouter initialEntries={['/collections/plush-pepe']}>
        <CollectionPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText('No priced pool is available yet.'),
    ).toBeVisible();
    expect(
      screen.getByText(/No committed pool or aggregate statistics/),
    ).toBeVisible();
  });
});
