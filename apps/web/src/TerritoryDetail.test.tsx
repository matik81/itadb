import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { Boundary, Coverage, Observation, Release } from './api';
import { TerritoryDetail } from './TerritoryDetail';

// Native modal focus trapping and Escape behavior are verified in Playwright.
beforeEach(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      },
    },
    close: {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      },
    },
  });
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = vi.fn(() => 'blob:boundary-fixture');
      static revokeObjectURL = vi.fn();
    },
  );
});
afterEach(() => {
  cleanup();
  Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal');
  Reflect.deleteProperty(HTMLDialogElement.prototype, 'close');
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const observation = {
  territory_id: 8,
  territory_code: '01',
  territory_name: 'Regione inventata',
  level: 'region',
  value: '12000',
  status: 'unflagged_upstream',
} as Observation;
const coverage = {
  title: 'Popolazione di test',
  unit: 'persons',
  period: '2024-01-01',
  territory_snapshot: '2024-01-01',
} as Coverage;
const release = {
  id: 'release-fixture',
  upstream_url: 'https://example.org/source',
  license_url: 'https://example.org/license',
  limitations: 'Dati inventati per i test.',
} as Release;
const boundary: Boundary = {
  release_id: release.id,
  territory_id: observation.territory_id,
  simplification_degrees: 0.001,
  geometry: {
    type: 'Polygon',
    coordinates: [
      [
        [7, 44],
        [9, 44],
        [9, 46],
        [7, 44],
      ],
    ],
  },
};
const props = { observation, coverage, release, sourceName: 'Fonte di test', onClose: vi.fn() };

it('renders the selected evidence and map with an explicit downloadable GeoJSON', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => boundary }));
  render(<TerritoryDetail {...props} />);
  expect(
    await screen.findByRole('img', { name: /Confine di Regione inventata/ }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText('Dato selezionato')).toHaveTextContent('12.000');
  expect(screen.getByLabelText('Dato selezionato')).toHaveTextContent('persone');
  expect(screen.getByText('Senza flag ISTAT')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Scarica il confine/ })).toHaveAttribute(
    'download',
    'itadb-01-2024-01-01.geojson',
  );
  fireEvent.click(screen.getByRole('button', { name: 'Ingrandisci +' }));
  expect(screen.getByText('Zoom 2×')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Vista completa' }));
  expect(screen.getByText('Zoom 1×')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Chiudi scheda' }));
  expect(props.onClose).toHaveBeenCalled();
});

it('keeps evidence readable after a boundary failure and supports retry', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 503 })
    .mockResolvedValue({ ok: true, json: async () => boundary });
  vi.stubGlobal('fetch', fetchMock);
  render(<TerritoryDetail {...props} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Mappa non disponibile');
  expect(screen.getByLabelText('Dato selezionato')).toHaveTextContent('12.000');
  expect(screen.queryByRole('link', { name: /Scarica il confine/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Riprova mappa' }));
  expect(await screen.findByRole('img')).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
});

it('does not draw a boundary for another territory or turn a missing value into zero', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...boundary, territory_id: 9 }) }),
  );
  render(
    <TerritoryDetail {...props} observation={{ ...observation, value: null, status: 'missing' }} />,
  );
  expect(await screen.findByRole('alert')).toHaveTextContent('non corrisponde');
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Dato selezionato')).toHaveTextContent('Non disponibile');
});
