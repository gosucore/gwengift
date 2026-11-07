import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type DisclosurePackage, type RoundAudit } from '../api/client';
import { CollectionStats } from '../components/CollectionStats';
import { formatDate, formatPercent, formatStars } from '../format';

function DisclosedEvidence({ disclosure }: { disclosure: DisclosurePackage }) {
  return (
    <>
      <section className="panel" aria-labelledby="versions-heading">
        <h2 id="versions-heading">Disclosed pool versions</h2>
        {disclosure.pool_versions.map((pool) => (
          <details className="audit-details" key={pool.id}>
            <summary>
              Version {pool.version} · {pool.remaining_count} gifts ·{' '}
              {formatStars(pool.price)}
            </summary>
            <code className="hash">{pool.commitment}</code>
            <p className="fine-print">
              EV {formatStars(pool.expected_value)} · RTP{' '}
              {formatPercent(pool.actual_rtp)} · margin{' '}
              {formatStars(pool.operator_margin)}
            </p>
            <div className="table-scroll">
              <table>
                <caption>Ordered remaining manifest</caption>
                <thead>
                  <tr>
                    <th>Gift ID</th>
                    <th>Model / attributes</th>
                    <th>Estimate</th>
                  </tr>
                </thead>
                <tbody>
                  {pool.manifest.gifts.map((gift) => (
                    <tr key={gift.id}>
                      <td>
                        <code>{gift.id}</code>
                      </td>
                      <td>
                        {gift.model} #{gift.number}; {gift.backdrop};{' '}
                        {gift.symbol}; {gift.rarity}
                      </td>
                      <td>{formatStars(gift.player_sale_estimate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
      </section>

      <section className="panel" aria-labelledby="outcomes-heading">
        <h2 id="outcomes-heading">Bet bindings and outcomes</h2>
        {disclosure.bets.length === 0 && (
          <p className="muted">No attempts were made.</p>
        )}
        {disclosure.bets.map((bet) => (
          <details className="audit-details" key={bet.id}>
            <summary>
              {bet.id.slice(0, 8)} · {bet.state} · {formatStars(bet.price)}
            </summary>
            <dl className="detail-list">
              <div>
                <dt>Pool version</dt>
                <dd>{bet.pool_version_id}</dd>
              </div>
              <div>
                <dt>Future beacon round</dt>
                <dd>{bet.future_beacon_round}</dd>
              </div>
              <div>
                <dt>Selected gift</dt>
                <dd>{bet.selected_gift_id ?? 'None — debit restored'}</dd>
              </div>
              <div>
                <dt>Ledger</dt>
                <dd>
                  {bet.ledger_entries
                    .map((entry) => `${entry.kind} ${entry.amount}`)
                    .join(' · ')}
                </dd>
              </div>
            </dl>
            {bet.beacon_proof && (
              <>
                <code className="hash">
                  randomness: {bet.beacon_proof.randomness}
                </code>
                <code className="hash">
                  signature: {bet.beacon_proof.signature}
                </code>
              </>
            )}
          </details>
        ))}
      </section>

      <section className="panel" aria-labelledby="final-gifts-heading">
        <h2 id="final-gifts-heading">Final gift inventory</h2>
        <p className="muted">
          {
            disclosure.gifts.filter((gift) => gift.lifecycle === 'AWARDED')
              .length
          }{' '}
          awarded ·{' '}
          {
            disclosure.gifts.filter((gift) => gift.lifecycle === 'AVAILABLE')
              .length
          }{' '}
          remaining
        </p>
        <details className="audit-details">
          <summary>Inspect all final gift states</summary>
          <ul className="audit-gift-list">
            {disclosure.gifts.map((gift) => (
              <li key={gift.id}>
                <code>{gift.id}</code> · {gift.model} #{gift.number} ·{' '}
                {gift.lifecycle}
              </li>
            ))}
          </ul>
        </details>
      </section>

      <section className="panel" aria-labelledby="snapshots-heading">
        <h2 id="snapshots-heading">Valuation evidence</h2>
        {disclosure.market_snapshots.map((snapshot) => (
          <details className="audit-details" key={snapshot.id}>
            <summary>{snapshot.id}</summary>
            <p>
              {snapshot.primary_source} · {snapshot.external_source}
            </p>
            <p className="fine-print">
              Observed {formatDate(snapshot.observed_at)} UTC · discount{' '}
              {formatPercent(snapshot.liquidity_discount)}
            </p>
            <pre className="evidence-json">
              {JSON.stringify(snapshot.source_payload, null, 2)}
            </pre>
          </details>
        ))}
      </section>
    </>
  );
}

export function RoundAuditPage() {
  const { roundId = '' } = useParams();
  const [audit, setAudit] = useState<RoundAudit | null>(null);
  const [disclosure, setDisclosure] = useState<DisclosurePackage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.getRoundAudit(roundId);
      setAudit(next);
      setDisclosure(next.disclosure ? await api.getDisclosure(roundId) : null);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load round evidence',
      );
    } finally {
      setLoading(false);
    }
  }, [roundId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <main className="page">
        <p className="loading-panel" role="status">
          Loading round evidence…
        </p>
      </main>
    );
  }
  if (error || !audit) {
    return (
      <main className="page">
        <div className="notice error" role="alert">
          {error ?? 'Round not found'}
        </div>
        <button type="button" onClick={() => void load()}>
          Retry
        </button>
      </main>
    );
  }

  const pool = audit.collection.pool;
  return (
    <main className="page">
      <Link className="back-link" to={`/collections/${audit.collection.id}`}>
        ← {audit.collection.name}
      </Link>
      <p className="eyebrow">PUBLIC FAIRNESS EVIDENCE · DEMO ROUND</p>
      <h1>Round audit</h1>
      <p className="muted">
        {audit.round.status} · disclosure deadline{' '}
        {formatDate(audit.round.disclosure_deadline)} UTC
      </p>

      {pool && (
        <section className="panel" aria-labelledby="current-commitment-heading">
          <h2 id="current-commitment-heading">
            Current committed pool · v{pool.version}
          </h2>
          <CollectionStats pool={pool} />
          <code className="hash">{pool.commitment}</code>
          <p className="fine-print">
            {pool.commitment_algorithm} · {pool.draw_algorithm}
          </p>
          {!disclosure && (
            <p className="status-message">
              The ordered manifest stays hidden until disclosure.
            </p>
          )}
        </section>
      )}

      {audit.disclosure && (
        <section
          className="panel disclosure-download"
          aria-labelledby="download-heading"
        >
          <h2 id="download-heading">Complete disclosure</h2>
          <p>
            Published {formatDate(audit.disclosure.created_at)} UTC. The
            canonical package contains all versions, valuations, bets, proofs,
            and gift states.
          </p>
          <code className="hash">SHA-256: {audit.disclosure.sha256}</code>
          <a
            className="download-action"
            href={audit.disclosure.download_url}
            download={`${roundId}-disclosure.json`}
          >
            Download disclosure JSON
          </a>
          <h3>Verify locally</h3>
          <p className="fine-print">
            Install backend dependencies, save the downloaded file as
            disclosure.json, then run:
          </p>
          <code className="command">
            cd backend &amp;&amp; .venv/bin/python -m app.verify_disclosure
            ./disclosure.json
          </code>
          <p className="fine-print">
            Verification is offline and recomputes commitments, economics, drand
            signatures, and every outcome.
          </p>
        </section>
      )}

      {disclosure && <DisclosedEvidence disclosure={disclosure} />}
    </main>
  );
}
