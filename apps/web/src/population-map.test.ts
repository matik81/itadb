import { describe, expect, it } from 'vitest';
import { geometryPath, mercator } from './population-map';

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
