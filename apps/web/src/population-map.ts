import type { Municipality, PopulationMapData } from './population-api';

export type TerritoryLevel = 'region' | 'province' | 'municipality';
export const territoryLabels = {
  region: {
    plural: 'Regioni',
    singular: 'regione',
    search: 'Cerca una regione',
    empty: 'Nessuna regione trovata.',
  },
  province: {
    plural: 'Province',
    singular: 'provincia',
    search: 'Cerca una provincia',
    empty: 'Nessuna provincia trovata.',
  },
  municipality: {
    plural: 'Comuni',
    singular: 'comune',
    search: 'Cerca un comune',
    empty: 'Nessun comune trovato.',
  },
};
export type MapTerritory = Omit<Municipality, 'location_kind'> & {
  level: TerritoryLevel;
};

export function aggregateTerritories(
  data: PopulationMapData | null,
  level: TerritoryLevel,
): MapTerritory[] {
  const municipalities = data?.municipalities ?? [];
  if (level === 'municipality') return municipalities.map((m) => ({ ...m, level }));
  const groups = new Map<string, typeof municipalities>();
  for (const municipality of municipalities) {
    const code = level === 'region' ? municipality.region_code : municipality.province_code;
    const group = groups.get(code) ?? [];
    group.push(municipality);
    groups.set(code, group);
  }
  return Array.from(groups, ([code, members]) => {
    const first = members[0];
    const located = members.filter((m) => m.latitude !== null && m.longitude !== null);
    // Keep the marker inside a member municipality, even for islands or concave territories.
    const weight = located.reduce((total, m) => total + Math.max(1, m.persons), 0);
    const x =
      located.reduce((total, m) => total + m.longitude! * Math.max(1, m.persons), 0) / weight;
    const y =
      located.reduce((total, m) => total + m.latitude! * Math.max(1, m.persons), 0) / weight;
    const anchor = located.reduce<(typeof located)[number] | undefined>(
      (nearest, m) =>
        !nearest ||
        Math.hypot(m.longitude! - x, m.latitude! - y) <
          Math.hypot(nearest.longitude! - x, nearest.latitude! - y)
          ? m
          : nearest,
      undefined,
    );
    return {
      code,
      name: level === 'region' ? first.region_name : first.province_name,
      level,
      region_code: first.region_code,
      region_name: first.region_name,
      province_code: level === 'province' ? code : '',
      province_name: level === 'province' ? first.province_name : '',
      persons: members.reduce((total, m) => total + m.persons, 0),
      households: members.reduce((total, m) => total + m.households, 0),
      latitude: anchor?.latitude ?? null,
      longitude: anchor?.longitude ?? null,
    };
  });
}

export type Point = [number, number];
export function populationRadius(persons: number, zoom: number): number {
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
