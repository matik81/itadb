export type Point = [number, number];
export function municipalityRadius(persons: number, zoom: number): number {
  // A common scale preserves area ratios at every zoom: 100,000 people = radius 6 px.
  return 6 * Math.sqrt(Math.max(0, persons) / 100000) * Math.min(1.6, Math.sqrt(zoom));
}
export function mercator(lon: number, lat: number): Point {
  return [
    (lon * Math.PI) / 180,
    -Math.log(Math.tan(Math.PI / 4 + (Math.max(-85, Math.min(85, lat)) * Math.PI) / 360)),
  ];
}
export function geometryPath(geometry: Record<string, unknown> | null): string {
  if (!geometry) return '';
  const polygons =
    geometry.type === 'Polygon'
      ? [geometry.coordinates]
      : geometry.type === 'MultiPolygon'
        ? geometry.coordinates
        : [];
  if (!Array.isArray(polygons)) return '';
  let points = 0;
  return polygons
    .flatMap((polygon: unknown) =>
      Array.isArray(polygon)
        ? polygon.map((ring: unknown) => {
            if (!Array.isArray(ring)) return '';
            return (
              ring
                .map((p: unknown, i: number) => {
                  if (
                    !Array.isArray(p) ||
                    typeof p[0] !== 'number' ||
                    typeof p[1] !== 'number' ||
                    !Number.isFinite(p[0]) ||
                    !Number.isFinite(p[1]) ||
                    ++points > 200000
                  )
                    throw new Error('Geometria non valida');
                  const [x, y] = mercator(p[0], p[1]);
                  return `${i ? 'L' : 'M'}${x},${y}`;
                })
                .join(' ') + 'Z'
            );
          })
        : [],
    )
    .join(' ');
}
