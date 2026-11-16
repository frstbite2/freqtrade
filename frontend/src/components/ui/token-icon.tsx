/**
 * A token or stock mark: a glowing gradient disc with the ticker's initials. Deliberately not a
 * company logo, so no brand is reproduced.
 */
export function TokenIcon({ symbol, color, size = 36 }: { symbol: string; color: string; size?: number }) {
  const letters = symbol.length > 3 ? symbol.slice(0, 2) : symbol.slice(0, 3);
  return (
    <span
      aria-hidden
      className="relative inline-flex shrink-0 items-center justify-center rounded-full font-display font-bold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * (letters.length > 2 ? 0.28 : 0.34),
        background: `radial-gradient(circle at 30% 25%, ${color}ee, ${color}55 55%, #160f27 100%)`,
        boxShadow: `0 0 0 1px ${color}55 inset, 0 6px 22px -6px ${color}aa`,
      }}
    >
      {letters}
    </span>
  );
}
