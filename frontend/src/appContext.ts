import { useOutletContext } from 'react-router-dom';
import type { Account } from './api/client';

export interface AppContext {
  account: Account | null;
  refreshAccount: () => Promise<Account | null>;
}

export function useAppContext() {
  return useOutletContext<AppContext>();
}
