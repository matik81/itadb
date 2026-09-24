import { describe, expect, it } from 'vitest';
import { aggregateTerritories, geometryPath, mercator, populationRadius } from './population-map';
import { mapFixture } from './test-fixtures/population';

describe('Mappa radar', () => {
  it('proietta a nord in alto e mantiene la relazione est/ovest', () => {
    const rome = mercator(12.5, 41.9);
    expect(mercator(12.5, 45)[1]).toBeLessThan(rome[1]);
    expect(mercator(14, 41.9)[0]).toBeGreaterThan(rome[0]);
  });
  it('mantiene più anelli per isole e buchi e rifiuta coordinate non finite', () => {
    const shape = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [10, 40],
            [11, 40],
            [11, 41],
            [10, 40],
          ],
        ],
        [
          [
            [12, 40],
            [13, 40],
            [13, 41],
            [12, 40],
          ],
        ],
      ],
    };
    expect(geometryPath(shape).split('Z')).toHaveLength(3);
    expect(geometryPath(null)).toBe('');
    expect(() => geometryPath({ type: 'Polygon', coordinates: [[[NaN, 40]]] })).toThrow();
  });
});

describe('Aggregazioni territoriali', () => {
  it('raggruppa per codice e conserva i totali anche senza coordinate', () => {
    const provinces = aggregateTerritories(mapFixture, 'province');
    expect(provinces.map((p) => [p.code, p.persons, p.households])).toEqual([
      ['900', 300, 30],
      ['901', 300, 30],
      ['910', 400, 40],
    ]);
    const regions = aggregateTerritories(mapFixture, 'region');
    expect(regions.map((r) => [r.code, r.persons, r.households])).toEqual([
      ['90', 600, 60],
      ['91', 400, 40],
    ]);
    expect(provinces[0]).toMatchObject({ latitude: 42, longitude: 12.5 });
    expect(aggregateTerritories(mapFixture, 'municipality')).toHaveLength(4);
    for (const level of ['region', 'province', 'municipality'] as const) {
      const territories = aggregateTerritories(mapFixture, level);
      expect(territories.reduce((total, t) => total + t.persons, 0)).toBe(1000);
      expect(territories.reduce((total, t) => total + t.households, 0)).toBe(100);
    }
  });
  it('non inventa punti quando tutte le coordinate sono assenti', () => {
    const data = {
      ...mapFixture,
      municipalities: [mapFixture.municipalities[1]],
      provinces: [],
      regions: [],
    };
    expect(aggregateTerritories(data, 'province')[0]).toMatchObject({
      persons: 200,
      households: 20,
      longitude: null,
      latitude: null,
    });
    expect(aggregateTerritories(null, 'region')).toEqual([]);
  });
  it('ancora il territorio a un punto comunale vicino al baricentro pesato', () => {
    const data = {
      ...mapFixture,
      municipalities: [
        { ...mapFixture.municipalities[0], persons: 1, longitude: 10 },
        { ...mapFixture.municipalities[1], persons: 99, latitude: 42, longitude: 14 },
      ],
    };
    expect(aggregateTerritories(data, 'province')[0].longitude).toBe(14);
  });
  it('mantiene la proporzione tra area e individui anche cambiando zoom', () => {
    for (const zoom of [1, 3, 10]) {
      expect(populationRadius(400, zoom) ** 2 / populationRadius(100, zoom) ** 2).toBeCloseTo(4);
    }
    expect(populationRadius(0, 1)).toBe(0);
  });
});
