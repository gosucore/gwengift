const symbols = ['✦', '◆', '✺', '◇', '✧'];

export function CollectionArtwork({
  collectionId,
  compact = false,
}: {
  collectionId: string;
  compact?: boolean;
}) {
  const tone =
    Array.from(collectionId).reduce(
      (total, character) => total + character.charCodeAt(0),
      0,
    ) % symbols.length;

  return (
    <div
      className={`collection-art tone-${tone}${compact ? ' compact' : ''}`}
      aria-hidden="true"
    >
      <span className="art-orbit" />
      <span className="art-gem">{symbols[tone]}</span>
      <span className="art-caption">FINITE VIRTUAL POOL</span>
    </div>
  );
}
