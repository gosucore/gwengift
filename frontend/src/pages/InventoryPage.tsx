import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Inventory } from '../api/client';
import { formatDate, formatStars } from '../format';

export function InventoryPage() {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setInventory(await api.getInventory());
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load virtual inventory',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="page">
      <p className="eyebrow">ACTIVE DEMO EPOCH · SIMULATED ASSETS</p>
      <h1>Virtual inventory</h1>
      {loading && (
        <p className="loading-panel" role="status">
          Loading virtual gifts…
        </p>
      )}
      {error && (
        <div className="notice error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      )}
      {!loading && inventory?.gifts.length === 0 && (
        <section className="empty-state">
          <h2>No virtual gifts yet</h2>
          <p>
            Completed demo draws will appear here. These items cannot be sold or
            transferred.
          </p>
          <Link className="text-link" to="/">
            Browse collections
          </Link>
        </section>
      )}
      <div className="inventory-list">
        {inventory?.gifts.map((gift) => (
          <article className="collection-card inventory-card" key={gift.id}>
            <div className="inventory-gem" aria-hidden="true">
              ◆
            </div>
            <p className="eyebrow">{gift.collection_id}</p>
            <h2>
              {gift.model} <span className="muted">#{gift.number}</span>
            </h2>
            <dl className="detail-list">
              <div>
                <dt>Backdrop</dt>
                <dd>{gift.backdrop}</dd>
              </div>
              <div>
                <dt>Symbol</dt>
                <dd>{gift.symbol}</dd>
              </div>
              <div>
                <dt>Rarity</dt>
                <dd>{gift.rarity}</dd>
              </div>
              <div>
                <dt>Estimated simulated value</dt>
                <dd>{formatStars(gift.player_sale_estimate)}</dd>
              </div>
              <div>
                <dt>Ticket paid</dt>
                <dd>{formatStars(gift.ticket_price)}</dd>
              </div>
              <div>
                <dt>Value minus ticket</dt>
                <dd>{formatStars(gift.value_minus_ticket)}</dd>
              </div>
            </dl>
            <p className="fine-print">
              Awarded {formatDate(gift.awarded_at)} UTC
            </p>
            <div className="link-row">
              <Link className="text-link" to={`/bets/${gift.bet_id}`}>
                View associated draw
              </Link>
              <Link className="text-link" to={`/rounds/${gift.round_id}/audit`}>
                View round
              </Link>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
