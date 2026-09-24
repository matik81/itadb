import type { Municipality, PopulationMapData } from '../population-api';

// Invented territories and counts, used only by tests.
const town = (code: string, province: string, region: string, persons: number): Municipality => ({
  code,
  name: `Comune ${code}`,
  province_code: province,
  province_name: `Provincia ${province}`,
  region_code: region,
  region_name: `Regione ${region}`,
  persons,
  households: persons / 10,
  longitude: 12.5,
  latitude: 42,
  location_kind: 'municipality_representative_point',
});
const geometry = {
  type: 'Polygon',
  coordinates: [
    [
      [12, 41],
      [13, 41],
      [13, 43],
      [12, 43],
      [12, 41],
    ],
  ],
};
export const mapFixture: PopulationMapData = {
  municipalities: [
    town('900001', '900', '90', 100),
    { ...town('900002', '900', '90', 200), longitude: null, latitude: null },
    town('901001', '901', '90', 300),
    town('910001', '910', '91', 400),
  ],
  regions: [
    { code: '90', name: 'Regione 90', persons: 600, households: 60, geometry },
    { code: '91', name: 'Regione 91', persons: 400, households: 40, geometry },
  ],
  provinces: ['900', '901', '910'].map((code) => ({ code, geometry })),
  municipality_boundaries: ['900001', '900002', '901001', '910001'].map((code) => ({
    code,
    geometry,
  })),
  representation: 'municipality_aggregates',
  individual_coordinates_available: false,
};
