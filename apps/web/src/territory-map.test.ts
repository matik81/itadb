import { expect, it } from 'vitest';
import { projectBoundary } from './territory-map';

const ring = [
  [7, 44],
  [9, 44],
  [9, 46],
  [7, 46],
  [7, 44],
];

it('fits a geographic polygon with north above south and east to the right', () => {
  const [path] = projectBoundary({ type: 'Polygon', coordinates: [ring] });
  const points = [...path.matchAll(/[ML]([\d.]+),([\d.]+)/g)].map((match) => [
    Number(match[1]),
    Number(match[2]),
  ]);
  expect(points[1][0]).toBeGreaterThan(points[0][0]);
  expect(points[2][1]).toBeLessThan(points[1][1]);
  for (const [x, y] of points) {
    expect(x).toBeGreaterThanOrEqual(24);
    expect(x).toBeLessThanOrEqual(616);
    expect(y).toBeGreaterThanOrEqual(24);
    expect(y).toBeLessThanOrEqual(416);
  }
});

it('preserves islands and interior rings without modifying source coordinates', () => {
  const geometry = {
    type: 'MultiPolygon',
    coordinates: [
      [
        ring,
        [
          [7.5, 44.5],
          [8, 44.5],
          [8, 45],
          [7.5, 44.5],
        ],
      ],
      [
        [
          [10, 40],
          [11, 40],
          [11, 41],
          [10, 40],
        ],
      ],
    ],
  };
  const original = JSON.stringify(geometry);
  const paths = projectBoundary(geometry);
  expect(paths).toHaveLength(2);
  expect(paths[0].match(/M/g)).toHaveLength(2);
  expect(paths[0].match(/Z/g)).toHaveLength(2);
  expect(JSON.stringify(geometry)).toBe(original);
});

it.each([
  { type: 'Point', coordinates: [7, 44] },
  { type: 'MultiPolygon', coordinates: [] },
  {
    type: 'Polygon',
    coordinates: [
      [
        [7, 44],
        [8, 45],
        [7, 44],
      ],
    ],
  },
  {
    type: 'Polygon',
    coordinates: [
      [
        [7, 44],
        [8, 44],
        [8, 45],
        [9, 44],
      ],
    ],
  },
  {
    type: 'Polygon',
    coordinates: [
      [
        [7, 90],
        [8, 44],
        [8, 45],
        [7, 90],
      ],
    ],
  },
  {
    type: 'Polygon',
    coordinates: [
      [
        [NaN, 44],
        [8, 44],
        [8, 45],
        [NaN, 44],
      ],
    ],
  },
])('rejects unavailable or unusable geometry: %j', (geometry) => {
  expect(() => projectBoundary(geometry)).toThrow('geometria consultabile');
});
