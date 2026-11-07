import { Link } from 'react-router-dom';
import type { Bet } from '../api/client';
import { formatStars } from '../format';

export function GiftReveal({ bet }: { bet: Bet }) {
  const gift = bet.gift;
  if (!gift) return null;
  const difference = gift.value_minus_ticket;
  const comparison =
    difference > 0
      ? `${formatStars(difference)} above the ticket`
      : difference < 0
        ? `${formatStars(Math.abs(difference))} below the ticket`
        : 'Equal to the ticket price';

  return (
    <section className="gift-reveal" aria-labelledby="gift-reveal-heading">
      <p className="eyebrow">VERIFIED VIRTUAL GIFT</p>
      <div className="gift-orb" aria-hidden="true">
        ◆
      </div>
      <h2 id="gift-reveal-heading">{gift.model}</h2>
      <p className="gift-number">#{gift.number}</p>
      <dl className="detail-list">
        <div>
          <dt>Collection</dt>
          <dd>{bet.collection_id}</dd>
        </div>
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
          <dt>Demo ticket paid</dt>
          <dd>{formatStars(gift.ticket_price)}</dd>
        </div>
      </dl>
      <p className={`value-comparison ${difference < 0 ? 'below' : 'above'}`}>
        {comparison}
      </p>
      <Link className="text-link" to={`/rounds/${bet.round_id}/audit`}>
        Inspect round evidence
      </Link>
    </section>
  );
}
