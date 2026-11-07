import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, api, type CollectionDetail } from '../api/client';
import { useAppContext } from '../appContext';
import { formatStars } from '../format';

export function DrawControls({
  collection,
  onPoolChanged,
}: {
  collection: CollectionDetail;
  onPoolChanged: () => Promise<void>;
}) {
  const { account, refreshAccount } = useAppContext();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);
  const idempotencyKey = useRef(crypto.randomUUID());
  const pool = collection.pool;

  if (!collection.available || !pool) return null;
  const insufficient = account !== null && account.demo_balance < pool.price;

  async function confirmDraw() {
    if (submittingRef.current || !pool) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const bet = await api.createBet({
        collection_id: collection.id,
        pool_version_id: pool.id,
        idempotency_key: idempotencyKey.current,
      });
      await refreshAccount();
      navigate(`/bets/${bet.id}`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to start the demo draw',
      );
      if (reason instanceof ApiError && reason.status === 409)
        await onPoolChanged();
      if (reason instanceof ApiError && reason.status === 400)
        await refreshAccount();
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  return (
    <section className="panel draw-controls" aria-labelledby="draw-heading">
      <h2 id="draw-heading">Demo draw</h2>
      {!confirming ? (
        <>
          {insufficient && (
            <p className="status-message warning">
              Insufficient demo Stars for this ticket.
            </p>
          )}
          <button
            type="button"
            className="primary-action"
            onClick={() => setConfirming(true)}
            disabled={!account || insufficient}
          >
            Review {formatStars(pool.price)} demo ticket
          </button>
        </>
      ) : (
        <div
          className="confirmation"
          role="group"
          aria-labelledby="confirm-heading"
        >
          <h3 id="confirm-heading">Confirm this exact demo price</h3>
          <p>
            <strong>{formatStars(pool.price)}</strong> from your simulated
            balance. One gift will be selected from {pool.remaining_count}{' '}
            remaining virtual gifts using future drand randomness.
          </p>
          <p className="fine-print">No real asset or payment is involved.</p>
          {error && (
            <p className="status-message warning" role="alert">
              {error}
            </p>
          )}
          <div className="button-row">
            <button
              type="button"
              className="primary-action"
              onClick={() => void confirmDraw()}
              disabled={submitting || insufficient}
            >
              {submitting
                ? 'Starting draw…'
                : `Confirm ${formatStars(pool.price)}`}
            </button>
            <button
              type="button"
              className="secondary-action"
              onClick={() => setConfirming(false)}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
