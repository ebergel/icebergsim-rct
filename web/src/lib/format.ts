// Presentation-only number formatting. No statistics here.

export function fmt(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtCi(
  ci: [number | null, number | null] | undefined,
  digits = 3,
): string {
  if (!ci || ci[0] === null || ci[1] === null) return "—";
  return `[${ci[0].toFixed(digits)}, ${ci[1].toFixed(digits)}]`;
}
