import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type Bet } from '../api/client';
import { GiftReveal } from '../components/GiftReveal';
import { formatDate, formatStars } from '../format';

const POLL_INTERVAL_MS = 1000;

export function DrawPage() {
  const { betId = '' } = useParams();
  const [bet, setBet] = useState<Bet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryCounter, setRetryCounter] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const next = await api.getBet(betId);
        if (!active) return;
        setBet(next);
        setError(null);
        if (next.state === 'PENDING_RANDOMNESS' || next.state === 'RESOLVING') {
          timer = setTimeout(() => void poll(), POLL_INTERVAL_MS);
        }
      } catch (reason) {
        if (!active) return;
        setError(
          reason instanceof Error ? reason.message : 'Unable to load the draw',
        );
      }
    }

    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [betId, retryCounter]);

  if (!bet) {
    return (
      <main className="page">
        <p role="status" className="loading-panel">
          {error ?? 'Loading committed draw…'}
        </p>
        {error && (
          <button
            type="button"
            onClick={() => setRetryCounter((value) => value + 1)}
          >
            Retry
          </button>
        )}
      </main>
    );
  }

  const pending =
    bet.state === 'PENDING_RANDOMNESS' || bet.state === 'RESOLVING';
  return (
    <main className="page">
      <p className="eyebrow">IMMUTABLE ATTEMPT · {bet.id.slice(0, 8)}</p>
      <h1>
        {pending
          ? 'Waiting for verified randomness'
          : bet.state === 'COMPLETED'
            ? 'Gift revealed'
            : 'Draw cancelled'}
      </h1>
      {error && (
        <div className="notice error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => setRetryCounter((value) => value + 1)}
          >
            Retry now
          </button>
        </div>
      )}

      {pending && (
        <section className="panel pending-draw" role="status">
          <div className="pending-spinner" aria-hidden="true" />
          <h2>Committed to drand round {bet.future_beacon_round}</h2>
          <p>
            {formatStars(bet.price)} debited once. No outcome can be selected
            until the beacon signature is verified locally.
          </p>
          <p className="fine-print">
            Acceptance cutoff: {formatDate(bet.acceptance_cutoff)} UTC
            <br />
            Resolution deadline: {formatDate(bet.resolution_deadline)} UTC
          </p>
        </section>
      )}

      {bet.state === 'CANCELLED' && (
        <section className="panel cancellation" role="status">
          <h2>
            {bet.cancellation_reason === 'demo_account_reset'
              ? 'Demo account reset'
              : 'Network failure'}
          </h2>
          <p>
            No gift was awarded. The full {formatStars(bet.price)} demo debit
            was restored.
          </p>
          <p className="fine-print">{bet.cancellation_reason}</p>
          <Link className="text-link" to={`/collections/${bet.collection_id}`}>
            Return to collection
          </Link>
        </section>
      )}

      {bet.state === 'COMPLETED' && <GiftReveal bet={bet} />}

      {bet.beacon && (
        <section className="panel" aria-labelledby="beacon-heading">
          <h2 id="beacon-heading">Verified beacon evidence</h2>
          <p>
            Round {bet.beacon.round} · verified{' '}
            {formatDate(bet.beacon.verified_at)} UTC
          </p>
          <code className="hash">randomness: {bet.beacon.randomness}</code>
          <code className="hash">signature: {bet.beacon.signature}</code>
        </section>
      )}
    </main>
  );
}
