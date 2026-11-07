import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { CatalogPage } from './pages/CatalogPage';
import { CollectionPage } from './pages/CollectionPage';
import { DrawPage } from './pages/DrawPage';
import { HistoryPage } from './pages/HistoryPage';
import { InventoryPage } from './pages/InventoryPage';
import { RoundAuditPage } from './pages/RoundAuditPage';

function Placeholder({ title }: { title: string }) {
  return (
    <main className="page">
      <p className="eyebrow">PROVABLY FAIR · VIRTUAL GIFTS</p>
      <h1>{title}</h1>
      <p className="muted">
        Every balance, gift, valuation, and result is simulated.
      </p>
    </main>
  );
}

export default function App() {
  return (
    <BrowserRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<CatalogPage />} />
          <Route
            path="collections/:collectionId"
            element={<CollectionPage />}
          />
          <Route path="bets/:betId" element={<DrawPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="rounds/:roundId/audit" element={<RoundAuditPage />} />
          <Route path="*" element={<Placeholder title="Page not found" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
