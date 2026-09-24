import type { Boundary } from '../api';

type Point = [number, number];

// Project the published WGS84 boundary to a north-up Mercator viewport.
// Rings stay in their polygon so even-odd filling preserves holes and islands.
export function projectBoundary(geometry: Boundary['geometry']): string[] {
  const polygons =
    geometry.type === 'Polygon'
      ? [geometry.coordinates]
      : geometry.type === 'MultiPolygon'
        ? geometry.coordinates
        : null;
  const invalid = () => new Error('Il confine non contiene una geometria consultabile.');
  if (!Array.isArray(polygons) || polygons.length === 0) throw invalid();
  let count = 0;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const projected: Point[][][] = polygons.map((polygon: unknown) => {
    if (!Array.isArray(polygon) || polygon.length === 0) throw invalid();
    return polygon.map((ring: unknown) => {
      if (!Array.isArray(ring) || ring.length < 4) throw invalid();
      const points = ring.map((position: unknown): Point => {
        if (
          !Array.isArray(position) ||
          typeof position[0] !== 'number' ||
          typeof position[1] !== 'number' ||
          !Number.isFinite(position[0]) ||
          !Number.isFinite(position[1]) ||
          Math.abs(position[0]) > 180 ||
          Math.abs(position[1]) > 85 ||
          ++count > 20000
        )
          throw invalid();
        const x = (position[0] * Math.PI) / 180;
        const y = -Math.log(Math.tan(Math.PI / 4 + (position[1] * Math.PI) / 360));
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
        return [x, y];
      });
      const first = points[0];
      const last = points[points.length - 1];
      if (first[0] !== last[0] || first[1] !== last[1]) throw invalid();
      return points;
    });
  });
  if (maxX <= minX || maxY <= minY) throw invalid();
  const scale = Math.min(592 / (maxX - minX), 392 / (maxY - minY));
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  return projected.map((polygon) =>
    polygon
      .map(
        (ring) =>
          ring
            .map(
              ([x, y], index) =>
                `${index === 0 ? 'M' : 'L'}${(320 + (x - centerX) * scale).toFixed(2)},${(220 + (y - centerY) * scale).toFixed(2)}`,
            )
            .join(' ') + ' Z',
      )
      .join(' '),
  );
}
