import type { components } from '../api/schema';
import { hasDiscrepancy } from '../format';

type Collection = components['schemas']['CollectionSummary'];

export function AvailabilityNotice({ collection }: { collection: Collection }) {
  const valuation = collection.valuation;
  const discrepancy =
    valuation &&
    hasDiscrepancy(
      valuation.cross_check_discrepancy,
      valuation.discrepancy_threshold,
    );

  if (!collection.pool) {
    return <p className="status-message">No priced pool is available yet.</p>;
  }
  return (
    <div className="availability" aria-label="Collection availability">
      {collection.available && (
        <p className="status-message success">Open for demo draws</p>
      )}
      {!collection.available && !valuation?.stale && !discrepancy && (
        <p className="status-message">
          Collection paused — new attempts are unavailable.
        </p>
      )}
      {valuation?.stale && (
        <p className="status-message warning">
          Valuation is stale. New attempts are paused.
        </p>
      )}
      {discrepancy && valuation && (
        <p className="status-message warning">
          Market sources disagree (
          {(Number(valuation.cross_check_discrepancy) * 100).toFixed(1)}%
          discrepancy); policy: {valuation.discrepancy_action}.
        </p>
      )}
    </div>
  );
}
