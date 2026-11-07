export function formatStars(value: number | string): string {
  const numeric = Number(value);
  return `${Number.isInteger(numeric) ? numeric.toLocaleString() : numeric.toFixed(2)} ★`;
}

export function formatPercent(value: string): string {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

export function formatDate(value: string): string {
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(normalized));
}

export function hasDiscrepancy(
  discrepancy: string | null,
  threshold: string | null,
): boolean {
  return (
    discrepancy !== null &&
    threshold !== null &&
    Number(discrepancy) > Number(threshold)
  );
}
