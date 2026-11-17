/** Geometry shared by the charts. */

export interface XY {
  x: number;
  y: number;
}

/** Scale values into a box: x across `width`, y inverted so larger is higher. */
export function project(values: number[], width: number, height: number, pad = 0.08): XY[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.abs(max) || 1;
  const lo = min - span * pad;
  const hi = max + span * pad;
  const n = values.length;
  return values.map((v, i) => ({
    x: n === 1 ? width / 2 : (i / (n - 1)) * width,
    y: height - ((v - lo) / (hi - lo)) * height,
  }));
}

/** A smooth curve through the points (Catmull-Rom as cubic Béziers, slightly tensioned). */
export function smoothPath(points: XY[], tension = 0.18): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M${points[0].x},${points[0].y}`;
  let d = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1x = p1.x + (p2.x - p0.x) * tension;
    const c1y = p1.y + (p2.y - p0.y) * tension;
    const c2x = p2.x - (p3.x - p1.x) * tension;
    const c2y = p2.y - (p3.y - p1.y) * tension;
    d += ` C${c1x.toFixed(2)},${c1y.toFixed(2)} ${c2x.toFixed(2)},${c2y.toFixed(2)} ${p2.x.toFixed(2)},${p2.y.toFixed(2)}`;
  }
  return d;
}

export function areaPath(points: XY[], height: number): string {
  if (points.length === 0) return "";
  const line = smoothPath(points);
  return `${line} L${points[points.length - 1].x},${height} L${points[0].x},${height} Z`;
}
