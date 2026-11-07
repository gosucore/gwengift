import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type CollectionDetail } from '../api/client';
import { AvailabilityNotice } from '../components/AvailabilityNotice';
import { CollectionArtwork } from '../components/CollectionArtwork';
import { CollectionStats } from '../components/CollectionStats';
import { DrawControls } from '../components/DrawControls';
import { formatDate, formatPercent, formatStars } from '../format';

export function CollectionPage() {
  const { collectionId = '' } = useParams();
  const [collection, setCollection] = useState<CollectionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCollection(await api.getCollection(collectionId));
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load this collection',
      );
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <main className="page">
        <p className="loading-panel" role="status">
          Loading collection statistics…
        </p>
      </main>
    );
  }
  if (error || !collection) {
    return (
      <main className="page">
        <div className="notice error" role="alert">
          <p>{error ?? 'Collection not found'}</p>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
        <Link to="/">Back to collections</Link>
      </main>
    );
  }

  const { pool, valuation, round } = collection;
  return (
    <main className="page">
      <Link className="back-link" to="/">
        ← Collections
      </Link>
      <p className="eyebrow">FINITE VIRTUAL GIFT POOL</p>
      <h1>{collection.name}</h1>
      <p className="muted">{collection.description}</p>
      <CollectionArtwork collectionId={collection.id} />
      <AvailabilityNotice collection={collection} />

      {pool ? (
        <>
          <section className="panel" aria-labelledby="current-pool-heading">
            <h2 id="current-pool-heading">
              Current pool · version {pool.version}
            </h2>
            <CollectionStats pool={pool} />
            <dl className="detail-list">
              <div>
                <dt>Rounding premium</dt>
                <dd>{formatStars(pool.rounding_premium_stars)}</dd>
              </div>
              <div>
                <dt>Demo operator margin</dt>
                <dd>{formatStars(pool.operator_margin)}</dd>
              </div>
              <div>
                <dt>Estimated range</dt>
                <dd>
                  {formatStars(pool.value_distribution.minimum)}–
                  {formatStars(pool.value_distribution.maximum)}
                </dd>
              </div>
              <div>
                <dt>Median estimate</dt>
                <dd>{formatStars(pool.value_distribution.median)}</dd>
              </div>
              <div>
                <dt>Below / at or above ticket</dt>
                <dd>
                  {pool.value_distribution.below_ticket_count} /{' '}
                  {pool.value_distribution.at_or_above_ticket_count}
                </dd>
              </div>
            </dl>
            <p className="fine-print">
              RTP is calculated from simulated estimates; it is not a short-term
              return guarantee.
            </p>
          </section>

          <DrawControls collection={collection} onPoolChanged={load} />

          <section className="panel" aria-labelledby="commitment-heading">
            <h2 id="commitment-heading">Pool commitment</h2>
            <code className="hash">{pool.commitment}</code>
            <p className="muted">
              {pool.commitment_algorithm} · {pool.draw_algorithm}. Gift
              identities stay hidden until disclosure.
            </p>
            {round && (
              <Link className="text-link" to={`/rounds/${round.id}/audit`}>
                Fairness & round audit
              </Link>
            )}
          </section>
        </>
      ) : (
        <p className="empty-state">
          No committed pool or aggregate statistics are available.
        </p>
      )}

      {valuation && (
        <section className="panel" aria-labelledby="valuation-heading">
          <h2 id="valuation-heading">Valuation provenance</h2>
          <dl className="detail-list">
            <div>
              <dt>Primary source</dt>
              <dd>{valuation.primary_source}</dd>
            </div>
            <div>
              <dt>External cross-check</dt>
              <dd>{valuation.external_source}</dd>
            </div>
            <div>
              <dt>Observed (UTC)</dt>
              <dd>{formatDate(valuation.observed_at)}</dd>
            </div>
            <div>
              <dt>Expires (UTC)</dt>
              <dd>{formatDate(valuation.expires_at)}</dd>
            </div>
            <div>
              <dt>Liquidity discount</dt>
              <dd>{formatPercent(valuation.liquidity_discount)}</dd>
            </div>
            <div>
              <dt>Conversion</dt>
              <dd>{valuation.conversion_rule.formula}</dd>
            </div>
          </dl>
          <p className="fine-print">
            {valuation.external_attribution} · {valuation.external_license}.
            Reference estimates, not executable offers.
          </p>
        </section>
      )}

      {round && (
        <p className="fine-print">
          Disclosure deadline: {formatDate(round.disclosure_deadline)} UTC ·
          Round {round.status}
        </p>
      )}
    </main>
  );
}
