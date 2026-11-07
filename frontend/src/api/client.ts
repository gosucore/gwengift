import createClient from 'openapi-fetch';
import type { components, paths } from './schema';
import { getTelegramWebApp } from '../telegram';

export type Account = components['schemas']['AccountResponse'];
export type Catalog = components['schemas']['CatalogResponse'];
export type CollectionDetail = components['schemas']['CollectionDetail'];
export type Bet = components['schemas']['BetResponse'];
export type CreateBetRequest = components['schemas']['CreateBetRequest'];
export type Inventory = components['schemas']['InventoryResponse'];
export type AttemptHistory = components['schemas']['AttemptHistoryResponse'];
export type RoundAudit = components['schemas']['RoundAuditResponse'];
export type DisclosurePackage = components['schemas']['DisclosurePackage'];

interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const client = createClient<paths>({ baseUrl: '/' });
client.use({
  onRequest({ request }) {
    const initData = getTelegramWebApp()?.initData;
    if (initData) {
      request.headers.set('X-Telegram-Init-Data', initData);
    } else if (import.meta.env.DEV) {
      const configuredId = import.meta.env.VITE_DEV_TELEGRAM_USER_ID || '1001';
      const userId = /^\d+$/.test(configuredId) ? configuredId : '1001';
      request.headers.set('X-Dev-Telegram-User-Id', userId);
      request.headers.set('X-Dev-Username', 'local-demo');
    }
    return request;
  },
});

function errorMessage(error: unknown, status: number): string {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = error.detail;
    if (typeof detail === 'string') return detail;
  }
  return `Request failed (${status})`;
}

async function unwrap<T>(result: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await result;
  if (!response.ok || data === undefined) {
    throw new ApiError(errorMessage(error, response.status), response.status);
  }
  return data;
}

export const api = {
  getAccount: () => unwrap<Account>(client.GET('/api/account')),
  resetAccount: () => unwrap<Account>(client.POST('/api/account/reset')),
  getCatalog: () => unwrap<Catalog>(client.GET('/api/collections')),
  getCollection: (id: string) =>
    unwrap<CollectionDetail>(
      client.GET('/api/collections/{collection_id}', {
        params: { path: { collection_id: id } },
      }),
    ),
  createBet: (body: CreateBetRequest) =>
    unwrap<Bet>(client.POST('/api/bets', { body })),
  getBet: (id: string) =>
    unwrap<Bet>(
      client.GET('/api/bets/{bet_id}', { params: { path: { bet_id: id } } }),
    ),
  getInventory: () => unwrap<Inventory>(client.GET('/api/account/inventory')),
  getAttempts: () =>
    unwrap<AttemptHistory>(client.GET('/api/account/attempts')),
  getRoundAudit: (roundId: string) =>
    unwrap<RoundAudit>(
      client.GET('/api/rounds/{round_id}/audit', {
        params: { path: { round_id: roundId } },
      }),
    ),
  getDisclosure: (roundId: string) =>
    unwrap<DisclosurePackage>(
      client.GET('/api/rounds/{round_id}/disclosure', {
        params: { path: { round_id: roundId } },
        parseAs: 'json',
      }),
    ),
  disclosureUrl: (roundId: string) =>
    `/api/rounds/${encodeURIComponent(roundId)}/disclosure`,
};
