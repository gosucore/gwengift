import { useRef, useState } from 'react';
import { api } from '../api/client';
import { useAppContext } from '../appContext';

export function ResetDemoAccount({
  onReset,
}: {
  onReset: () => Promise<void>;
}) {
  const { account, refreshAccount } = useAppContext();
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  async function reset() {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await api.resetAccount();
      await refreshAccount();
      await onReset();
      setConfirming(false);
      setMessage(
        'Demo account reset. Active inventory and history are now empty.',
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to reset the demo account',
      );
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  return (
    <section className="panel reset-panel" aria-labelledby="reset-heading">
      <h2 id="reset-heading">Reset demo progress</h2>
      <p className="muted">
        Start a new demo epoch with the starting balance. Global round audit
        records remain available.
      </p>
      {message && <p role="status">{message}</p>}
      {error && (
        <p className="status-message warning" role="alert">
          {error}
        </p>
      )}
      {!confirming ? (
        <button
          type="button"
          className="secondary-action"
          onClick={() => {
            setMessage(null);
            setConfirming(true);
          }}
          disabled={!account}
        >
          Reset demo progress
        </button>
      ) : (
        <div
          className="confirmation"
          role="group"
          aria-label="Confirm demo reset"
        >
          <p>
            Clear this epoch&apos;s virtual inventory and history and restore
            the starting demo balance?
          </p>
          <div className="button-row">
            <button
              type="button"
              onClick={() => void reset()}
              disabled={submitting}
            >
              {submitting ? 'Resetting…' : 'Yes, reset demo'}
            </button>
            <button
              type="button"
              className="secondary-action"
              onClick={() => setConfirming(false)}
              disabled={submitting}
            >
              Keep progress
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
