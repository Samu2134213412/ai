function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

const round2 = (n) => Math.round(n * 100) / 100;

// Median-based, with a first pass that drops prices far from the rough
// median: accessories, bundles and the 1-€-Lockpreise that every search has.
export function priceStats(prices) {
  const sorted = prices.filter((p) => Number.isFinite(p) && p > 0).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const rough = quantile(sorted, 0.5);
  const kept = sorted.filter((p) => p >= rough * 0.35 && p <= rough * 2);
  return {
    count: kept.length,
    excluded: sorted.length - kept.length,
    median: round2(quantile(kept, 0.5)),
    p25: round2(quantile(kept, 0.25)),
    p75: round2(quantile(kept, 0.75)),
    min: kept[0],
    max: kept.at(-1),
  };
}
