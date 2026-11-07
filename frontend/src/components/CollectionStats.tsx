import type { components } from '../api/schema';
import { formatPercent, formatStars } from '../format';

type Pool = components['schemas']['PublicPoolVersion'];

export function CollectionStats({ pool }: { pool: Pool }) {
  return (
    <dl className="stats-grid">
      <div>
        <dt>Demo ticket</dt>
        <dd>{formatStars(pool.price)}</dd>
      </div>
      <div>
        <dt>Calculated RTP</dt>
        <dd>{formatPercent(pool.actual_rtp)}</dd>
      </div>
      <div>
        <dt>Expected value</dt>
        <dd>{formatStars(pool.expected_value)}</dd>
      </div>
      <div>
        <dt>Gifts remaining</dt>
        <dd>{pool.remaining_count}</dd>
      </div>
    </dl>
  );
}
