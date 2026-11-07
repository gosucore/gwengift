import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Catalog } from '../api/client';
import { AvailabilityNotice } from '../components/AvailabilityNotice';
import { CollectionArtwork } from '../components/CollectionArtwork';
import { CollectionStats } from '../components/CollectionStats';

export function CatalogPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCatalog(await api.getCatalog());
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Unable to load collections',
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
      <p className="eyebrow">TEN FINITE POOLS · VERIFIABLE OUTCOMES</p>
      <h1>Collections</h1>
      <p className="muted">
        Compare simulated prices and odds before choosing a demo draw.
      </p>
      {loading && (
        <p role="status" className="loading-panel">
          Loading collections…
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
      {!loading && catalog?.collections.length === 0 && (
        <p className="empty-state">No collections are configured.</p>
      )}
      <div className="collection-grid">
        {catalog?.collections.map((collection) => (
          <article className="collection-card" key={collection.id}>
            <CollectionArtwork collectionId={collection.id} compact />
            <div className="card-heading">
              <h2>
                <Link to={`/collections/${collection.id}`}>
                  {collection.name}
                </Link>
              </h2>
              <span className="status-chip">{collection.status}</span>
            </div>
            <p className="muted">{collection.description}</p>
            {collection.pool && <CollectionStats pool={collection.pool} />}
            <AvailabilityNotice collection={collection} />
            <Link className="text-link" to={`/collections/${collection.id}`}>
              View statistics & fairness
            </Link>
          </article>
        ))}
      </div>
    </main>
  );
}
